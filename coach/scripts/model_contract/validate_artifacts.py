#!/usr/bin/env python3
"""Validate the model artifacts before report generation.

This validator deliberately depends only on the Python standard library so it
can run in the worker image and in a lightweight CI contract test.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any


REQUIRED_OUTPUTS = (
    "details.json",
    "pose_predictions.json",
    "feature_results.json",
)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"missing model artifact: {path.name}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON model artifact: {path.name}") from error


def _assert_finite(value: Any, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite numeric value in {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]")


def validate_run(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    artifacts = {
        name: _load_json(output_dir / name)
        for name in REQUIRED_OUTPUTS
    }

    for name, payload in artifacts.items():
        if not isinstance(payload, dict):
            raise ValueError(f"{name} must contain a JSON object")
        _assert_finite(payload, name)

    details = artifacts["details.json"]
    video = details.get("video")
    if not isinstance(video, dict):
        raise ValueError("details.json.video must be an object")
    for key in ("width", "height", "fps", "frame_count"):
        if key not in video:
            raise ValueError(f"details.json.video.{key} is required")

    predictions = artifacts["pose_predictions.json"]
    frames = predictions.get("frames")
    if not isinstance(frames, list):
        raise ValueError("pose_predictions.json.frames must be a list")
    if not frames:
        raise ValueError("pose_predictions.json.frames must not be empty")

    features = artifacts["feature_results.json"]
    for feature_id, feature in features.items():
        if not isinstance(feature, dict):
            raise ValueError(f"feature {feature_id} must be an object")
        if "value" not in feature or "unit" not in feature:
            raise ValueError(
                f"feature {feature_id} requires value and unit"
            )
        if not isinstance(feature["unit"], str) or not feature["unit"]:
            raise ValueError(f"feature {feature_id}.unit must be non-empty")

    return {
        "contract_version": "coach-model-1.0",
        "artifact_names": list(REQUIRED_OUTPUTS),
        "frame_count": len(frames),
        "feature_ids": list(features),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_artifacts.py RUN_DIR", file=sys.stderr)
        return 2
    try:
        summary = validate_run(Path(sys.argv[1]))
    except (OSError, TypeError, ValueError) as error:
        print(f"MODEL_CONTRACT_INVALID={error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
