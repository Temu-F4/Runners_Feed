"""Send one video-analysis stage to RunPod and validate its artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from coach_video_analysis_contract import (
    CONTRACT_VERSION,
    RESULT_FILES,
    model_hashes,
    sha256_file,
    source_hashes,
)


RUN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _token() -> str:
    token_file = os.getenv("RUNPOD_SHARED_TOKEN_FILE")
    value = (
        Path(token_file).read_text(encoding="utf-8").strip()
        if token_file
        else os.getenv("RUNPOD_SHARED_TOKEN", "")
    )
    if len(value) < 24:
        raise ValueError("RunPod shared token is missing or too short")
    return value


def _base_url() -> str:
    value = os.getenv("RUNPOD_GPU_BASE_URL", "")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("RUNPOD_GPU_BASE_URL must be an HTTPS origin")
    return value.rstrip("/")


def _validate_archive(
    archive_path: Path,
    *,
    contract: dict,
    run_id: str,
) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if sorted(names) != sorted(RESULT_FILES):
            raise ValueError(f"Unexpected RunPod result files: {names}")
        if any(Path(name).name != name for name in names):
            raise ValueError("Nested or unsafe result path")
        evidence = json.loads(archive.read("evidence.json"))
        if evidence.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("RunPod contract version mismatch")
        if evidence.get("run_id") != run_id:
            raise ValueError("RunPod result belongs to another run")
        for key in ("input_sha256", "source_sha256", "model_sha256"):
            if evidence.get(key) != contract[key]:
                raise ValueError(f"RunPod contract mismatch: {key}")
        providers = evidence.get("providers", [])
        if "CUDAExecutionProvider" not in providers:
            raise ValueError("RunPod did not report CUDAExecutionProvider")
        for name in RESULT_FILES[:-1]:
            with archive.open(name) as source, tempfile.NamedTemporaryFile() as temp:
                shutil.copyfileobj(source, temp)
                temp.flush()
                if sha256_file(Path(temp.name)) != evidence.get("result_sha256", {}).get(name):
                    raise ValueError(f"RunPod result checksum mismatch: {name}")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("video", type=Path)
    parser.add_argument("--code-root", required=True, type=Path)
    args = parser.parse_args()

    if not RUN_PATTERN.fullmatch(args.run_id):
        raise ValueError("Invalid run_id")
    output_dir = args.workspace / "run" / args.run_id / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    destinations = [output_dir / name for name in RESULT_FILES[:-1]]
    if any(path.exists() for path in destinations):
        raise FileExistsError("RunPod results would overwrite existing artifacts")

    contract = {
        "contract_version": CONTRACT_VERSION,
        "run_id": args.run_id,
        "input_sha256": sha256_file(args.video),
        "source_sha256": source_hashes(args.code_root),
        "model_sha256": model_hashes(args.workspace / "models"),
    }
    timeout = float(os.getenv("RUNPOD_REQUEST_TIMEOUT", "3600"))
    max_result_bytes = int(os.getenv("RUNPOD_MAX_RESULT_BYTES", str(500 * 1024 * 1024)))
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="coach-runpod-result-") as temp_dir:
        archive_path = Path(temp_dir) / "result.zip"
        with args.video.open("rb") as video:
            response = requests.post(
                f"{_base_url()}/v3/video-analysis",
                headers={"Authorization": f"Bearer {_token()}"},
                data={"run_id": args.run_id, "contract": json.dumps(contract)},
                files={"video": (args.video.name, video, "video/mp4")},
                timeout=(10, timeout),
                allow_redirects=False,
                stream=True,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"RunPod HTTP {response.status_code}; CPU fallback was not attempted"
            )
        total = 0
        with archive_path.open("xb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_result_bytes:
                    raise RuntimeError("RunPod result is larger than configured limit")
                stream.write(chunk)
        evidence = _validate_archive(
            archive_path,
            contract=contract,
            run_id=args.run_id,
        )
        with tempfile.TemporaryDirectory(dir=output_dir, prefix=".runpod-") as staging:
            staging_path = Path(staging)
            with zipfile.ZipFile(archive_path) as archive:
                for name in RESULT_FILES[:-1]:
                    with archive.open(name) as source, (staging_path / name).open("xb") as target:
                        shutil.copyfileobj(source, target)
            for name in RESULT_FILES[:-1]:
                os.replace(staging_path / name, output_dir / name)

    evidence["oci_roundtrip_seconds"] = time.perf_counter() - started
    evidence_path = output_dir / "runpod_video_analysis_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    evidence_root = os.getenv("GPU_AB_EVIDENCE_DIR")
    if evidence_root:
        archive_path = Path(evidence_root)
        archive_path.mkdir(parents=True, exist_ok=True)
        archived_evidence = archive_path / f"{args.run_id}.json"
        with archived_evidence.open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"RunPod video analysis completed in {evidence['oci_roundtrip_seconds']:.3f}s")


if __name__ == "__main__":
    main()
