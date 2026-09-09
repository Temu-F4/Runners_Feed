#!/usr/bin/env python3
"""Verify that golden HPE artifacts came from the declared CUDA release."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
ARTIFACTS = {
    "predictions": ("pose_predictions.json", "application/json"),
    "details": ("details.json", "application/json"),
    "video": ("rendered.mp4", "video/mp4"),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name} must contain an object")
    return value


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate(plugin_dir: Path, run_dir: Path) -> dict[str, Any]:
    plugin = _load(plugin_dir / "model_manifest.json")
    output_dir = run_dir / "outputs"
    evidence = _load(output_dir / "pose_manifest.json")
    model_id = plugin.get("model_id")
    _require(evidence.get("schema_version") == "video-analysis-manifest-2.0", "manifest schema mismatch")
    _require(evidence.get("status") == "complete", "RunPod manifest is incomplete")
    _require(evidence.get("model_id") == model_id, "RunPod model ID mismatch")
    _require(isinstance(evidence.get("job_id"), str) and ID.fullmatch(evidence["job_id"]), "invalid job ID")
    _require(isinstance(evidence.get("attempt_id"), str) and ID.fullmatch(evidence["attempt_id"]), "invalid attempt ID")

    source_files = plugin.get("source_files")
    _require(isinstance(source_files, list) and source_files, "plugin source_files are missing")
    expected_sources = {
        relative: _sha256(plugin_dir / relative)
        for relative in source_files
    }
    _require(evidence.get("source_sha256") == expected_sources, "RunPod source hashes mismatch")

    weights = plugin.get("weights")
    _require(isinstance(weights, list) and weights, "plugin weights are missing")
    expected_weights = {item["path"]: item["sha256"] for item in weights}
    _require(
        all(isinstance(value, str) and SHA256.fullmatch(value) for value in expected_weights.values()),
        "plugin weight hash is invalid",
    )
    _require(evidence.get("model_sha256") == expected_weights, "RunPod weight hashes mismatch")

    execution = evidence.get("execution")
    _require(isinstance(execution, dict), "RunPod execution evidence is missing")
    _require(execution.get("device") == "cuda", "golden run did not use CUDA")
    _require(execution.get("provider") == "CUDAExecutionProvider", "golden run used the wrong provider")
    _require(isinstance(execution.get("gpu_name"), str) and execution["gpu_name"], "GPU name is missing")

    prefix = f"jobs/{evidence['job_id']}/video-analysis/{evidence['attempt_id']}"
    objects = evidence.get("objects")
    _require(isinstance(objects, dict) and set(objects) == set(ARTIFACTS), "RunPod artifact set mismatch")
    for role, (filename, content_type) in ARTIFACTS.items():
        metadata = objects[role]
        path = output_dir / filename
        _require(isinstance(metadata, dict), f"invalid metadata: {role}")
        _require(metadata.get("object_name") == f"{prefix}/{filename}", f"object path mismatch: {role}")
        _require(metadata.get("content_type") == content_type, f"content type mismatch: {role}")
        _require(path.is_file(), f"golden artifact is missing: {filename}")
        _require(metadata.get("bytes") == path.stat().st_size, f"artifact size mismatch: {role}")
        _require(metadata.get("sha256") == _sha256(path), f"artifact hash mismatch: {role}")

    timings = evidence.get("timings_seconds")
    _require(isinstance(timings, dict), "RunPod timings are missing")
    for key in ("download", "analysis", "encode", "upload", "worker_total"):
        value = timings.get(key)
        _require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f"invalid timing: {key}")

    return {
        "status": "ok",
        "model_id": model_id,
        "gpu_name": execution["gpu_name"],
        "attempt_id": evidence["attempt_id"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.plugin_dir, args.run_dir)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"MODEL_CONTRACT_INVALID={error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
