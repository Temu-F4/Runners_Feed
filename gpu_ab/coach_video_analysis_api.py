"""RunPod API for the model team's integrated video-analysis stage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from coach_video_analysis_contract import (
    CONTRACT_VERSION,
    RESULT_FILES,
    model_hashes,
    sha256_file,
    source_hashes,
)


RUN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
GPU_LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import torch
    import onnxruntime as ort

    token = os.environ["RUNPOD_SHARED_TOKEN"]
    if len(token) < 24:
        raise RuntimeError("RUNPOD_SHARED_TOKEN must contain at least 24 characters")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(f"CUDAExecutionProvider unavailable: {providers}")
    code_root = Path(os.environ["COACH_CODE_ROOT"]).resolve()
    model_root = Path(os.environ["COACH_MODEL_ROOT"]).resolve()
    app.state.runtime = SimpleNamespace(
        token=token,
        code_root=code_root,
        model_root=model_root,
        sources=source_hashes(code_root),
        models=model_hashes(model_root),
        providers=providers,
        gpu=torch.cuda.get_device_name(0),
        max_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
        timeout=float(os.getenv("VIDEO_ANALYSIS_TIMEOUT", "3600")),
    )
    yield


app = FastAPI(
    title="Coach integrated GPU video analysis",
    version=CONTRACT_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def authorize(request, call_next):
    if request.url.path != "/health":
        expected = f"Bearer {app.state.runtime.token}"
        if not secrets.compare_digest(request.headers.get("authorization", ""), expected):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    runtime = app.state.runtime
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "gpu": runtime.gpu,
        "providers": runtime.providers,
    }


@app.post("/v3/video-analysis")
def video_analysis(
    video: UploadFile = File(...),
    run_id: str = Form(...),
    contract: str = Form(...),
):
    runtime = app.state.runtime
    if not RUN_PATTERN.fullmatch(run_id):
        raise HTTPException(400, "Invalid run_id")
    try:
        expected = json.loads(contract)
    except ValueError as error:
        raise HTTPException(400, "Invalid contract JSON") from error
    actual_contract = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "source_sha256": runtime.sources,
        "model_sha256": runtime.models,
    }
    for key, value in actual_contract.items():
        if expected.get(key) != value:
            raise HTTPException(409, f"OCI/RunPod mismatch: {key}")
    if not GPU_LOCK.acquire(blocking=False):
        raise HTTPException(429, "GPU busy; CPU fallback is disabled")

    request_root = Path(tempfile.mkdtemp(prefix="coach-video-analysis-"))
    try:
        workspace = request_root / "workspace"
        run_dir = workspace / "run" / run_id
        output_dir = run_dir / "outputs"
        run_dir.mkdir(parents=True)
        (workspace / "models").symlink_to(runtime.model_root, target_is_directory=True)
        input_path = run_dir / "input.mp4"
        digest = hashlib.sha256()
        size = 0
        with input_path.open("xb") as target:
            while chunk := video.file.read(1024 * 1024):
                size += len(chunk)
                if size > runtime.max_bytes:
                    raise HTTPException(413, "Video too large")
                digest.update(chunk)
                target.write(chunk)
        if not size or digest.hexdigest() != expected.get("input_sha256"):
            raise HTTPException(409, "Video checksum mismatch or empty input")

        started = time.perf_counter()
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(runtime.code_root)
        result = subprocess.run(
            [
                sys.executable,
                str(runtime.code_root / "scripts/hpe/hpe.py"),
                str(workspace),
                run_id,
                str(input_path),
                "--device",
                "cuda",
            ],
            env=environment,
            text=True,
            capture_output=True,
            timeout=runtime.timeout,
        )
        if result.returncode:
            raise HTTPException(500, f"GPU analysis failed: {result.stderr[-1000:]}")
        required = [output_dir / name for name in RESULT_FILES[:-1]]
        if any(not path.is_file() for path in required):
            raise HTTPException(500, "GPU analysis did not create every required artifact")

        evidence = {
            **actual_contract,
            "input_sha256": digest.hexdigest(),
            "providers": runtime.providers,
            "gpu": runtime.gpu,
            "analysis_seconds": time.perf_counter() - started,
            "result_sha256": {
                path.name: sha256_file(path) for path in required
            },
            "log_tail": (result.stdout + result.stderr)[-2000:],
        }
        evidence_path = output_dir / "evidence.json"
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        archive_path = request_root / "result.zip"
        with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as archive:
            for name in RESULT_FILES:
                archive.write(output_dir / name, arcname=name)
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"{run_id}-video-analysis.zip",
            background=BackgroundTask(shutil.rmtree, request_root),
        )
    except subprocess.TimeoutExpired as error:
        shutil.rmtree(request_root, ignore_errors=True)
        raise HTTPException(504, "GPU analysis timed out") from error
    except HTTPException:
        shutil.rmtree(request_root, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(request_root, ignore_errors=True)
        raise
    finally:
        video.file.close()
        GPU_LOCK.release()
