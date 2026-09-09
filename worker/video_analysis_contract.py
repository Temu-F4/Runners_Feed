from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REQUEST_SCHEMA = "video-analysis-request-2.0"
MANIFEST_SCHEMA = "video-analysis-manifest-2.0"
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ARTIFACTS = {
    "predictions": ("pose_predictions.json", "application/json"),
    "details": ("details.json", "application/json"),
    "video": ("rendered.mp4", "video/mp4"),
}
UPLOAD_ROLES = (*ARTIFACTS.keys(), "manifest")
def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _valid_object_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def release_hashes(coach_root: Path, model_id: str) -> tuple[dict[str, str], dict[str, str]]:
    plugin_root = coach_root / "model_plugins" / model_id
    manifest = json.loads((plugin_root / "model_manifest.json").read_text(encoding="utf-8"))
    source_files = manifest.get("source_files")
    _require(
        isinstance(source_files, list) and bool(source_files),
        "model manifest contains no source files",
    )
    source_hashes = {
        relative: _sha256(plugin_root / relative)
        for relative in source_files
    }
    model_hashes = {
        item["path"]: item["sha256"]
        for item in manifest.get("weights", [])
    }
    _require(bool(model_hashes), "model manifest contains no weights")
    _require(
        all(SHA256_PATTERN.fullmatch(value) for value in model_hashes.values()),
        "model manifest contains an invalid weight hash",
    )
    return source_hashes, model_hashes


def build_request(
    snapshot: dict[str, Any],
    attempt_id: str,
    coach_root: Path,
    transfer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_hashes, model_hashes = release_hashes(coach_root, snapshot["model_id"])
    job_id = str(snapshot["job_id"])
    attempt_id = str(attempt_id)
    request = {
        "schema_version": REQUEST_SCHEMA,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "model_id": snapshot["model_id"],
        "model_release": snapshot["model_release"],
        "source_sha256": source_hashes,
        "model_sha256": model_hashes,
        "input": {
            "object_name": snapshot["input_object_name"],
            "etag": snapshot["input_etag"],
            "bytes": snapshot["input_size_bytes"],
        },
        "result_prefix": f"jobs/{job_id}/video-analysis/{attempt_id}",
    }
    if transfer is not None:
        request["transfer"] = transfer
    return request


def validate_request(request: dict[str, Any]) -> str:
    _require(request.get("schema_version") == REQUEST_SCHEMA, "request schema mismatch")
    for key in ("job_id", "attempt_id", "model_id"):
        _require(isinstance(request.get(key), str) and ID_PATTERN.fullmatch(request[key]), f"invalid {key}")
    _require(isinstance(request.get("model_release"), str) and bool(request["model_release"]), "invalid model_release")
    for key in ("source_sha256", "model_sha256"):
        values = request.get(key)
        _require(isinstance(values, dict) and bool(values), f"invalid {key}")
        _require(all(isinstance(name, str) and isinstance(value, str) and SHA256_PATTERN.fullmatch(value) for name, value in values.items()), f"invalid {key}")
    input_meta = request.get("input")
    _require(isinstance(input_meta, dict), "invalid input")
    _require(_valid_object_name(input_meta.get("object_name")), "invalid input object_name")
    _require(isinstance(input_meta.get("etag"), str) and bool(input_meta["etag"]), "invalid input etag")
    _require(type(input_meta.get("bytes")) is int and input_meta["bytes"] > 0, "invalid input bytes")
    prefix = f"jobs/{request['job_id']}/video-analysis/{request['attempt_id']}"
    _require(request.get("result_prefix") == prefix, "result prefix mismatch")
    if "transfer" in request:
        validate_transfer(request["transfer"])
    return prefix


def validate_transfer(transfer: dict[str, Any]) -> None:
    _require(isinstance(transfer, dict), "transfer must be an object")
    upload_urls = transfer.get("upload_urls")
    _require(_https_url(transfer.get("input_url")), "invalid signed input URL")
    _require(isinstance(upload_urls, dict) and set(upload_urls) == set(UPLOAD_ROLES), "invalid signed upload URL set")
    _require(all(_https_url(url) for url in upload_urls.values()), "invalid signed upload URL")


def _https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and hostname.endswith(".oraclecloud.com") and not parsed.username


def validate_manifest(manifest: dict[str, Any], request: dict[str, Any]) -> str:
    prefix = validate_request(request)
    _require(manifest.get("schema_version") == MANIFEST_SCHEMA, "manifest schema mismatch")
    _require(manifest.get("status") == "complete", "manifest is incomplete")
    for key in ("job_id", "attempt_id", "model_id", "model_release", "source_sha256", "model_sha256", "input"):
        _require(manifest.get(key) == request[key], f"request mismatch: {key}")
    _require(isinstance(manifest.get("input_sha256"), str) and SHA256_PATTERN.fullmatch(manifest["input_sha256"]), "invalid input_sha256")
    objects = manifest.get("objects")
    _require(isinstance(objects, dict) and set(objects) == set(ARTIFACTS), "artifact set mismatch")
    for role, (filename, content_type) in ARTIFACTS.items():
        metadata = objects[role]
        _require(isinstance(metadata, dict), f"invalid artifact metadata: {role}")
        _require(metadata.get("object_name") == f"{prefix}/{filename}", f"artifact path mismatch: {role}")
        _require(metadata.get("content_type") == content_type, f"artifact content type mismatch: {role}")
        _require(isinstance(metadata.get("sha256"), str) and SHA256_PATTERN.fullmatch(metadata["sha256"]), f"invalid artifact sha256: {role}")
        _require(type(metadata.get("bytes")) is int and metadata["bytes"] > 0, f"invalid artifact bytes: {role}")
    execution = manifest.get("execution")
    _require(isinstance(execution, dict), "missing execution evidence")
    _require(execution.get("device") == "cuda" and execution.get("provider") == "CUDAExecutionProvider" and isinstance(execution.get("gpu_name"), str) and bool(execution["gpu_name"]), "invalid GPU evidence")
    timings = manifest.get("timings_seconds")
    _require(isinstance(timings, dict), "missing timings")
    for key in ("download", "analysis", "encode", "upload", "worker_total"):
        value = timings.get(key)
        _require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f"invalid timing: {key}")
    return f"{prefix}/pose_manifest.json"


def verify_file(path: Path, metadata: dict[str, Any]) -> None:
    _require(path.stat().st_size == metadata["bytes"], f"artifact size mismatch: {path.name}")
    _require(_sha256(path) == metadata["sha256"], f"artifact checksum mismatch: {path.name}")


def validate_downloaded_artifacts(output_dir: Path) -> None:
    details = json.loads((output_dir / "details.json").read_text(encoding="utf-8"))
    predictions = json.loads((output_dir / "pose_predictions.json").read_text(encoding="utf-8"))
    video = details.get("video")
    _require(isinstance(video, dict), "details.video must be an object")
    for key in ("width", "height", "fps", "frame_count"):
        value = video.get(key)
        _require(type(value) in (int, float) and math.isfinite(value) and value > 0, f"invalid video {key}")
    frames = predictions.get("frames")
    _require(isinstance(frames, list) and bool(frames), "pose predictions must contain frames")
    _require(all(isinstance(frame, dict) and isinstance(frame.get("people"), list) for frame in frames), "invalid pose frame")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames",
         "-of", "json", str(output_dir / "rendered.mp4")],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    _require(len(streams) == 1, "rendered video must contain one video stream")
    stream = streams[0]
    _require(stream.get("codec_name") == "h264" and stream.get("pix_fmt") == "yuv420p", "unsupported rendered video encoding")
    _require(stream.get("width") == video["width"] and stream.get("height") == video["height"], "rendered video dimensions mismatch")
    _require(int(stream.get("nb_read_frames", 0)) == int(video["frame_count"]), "rendered video frame count mismatch")
