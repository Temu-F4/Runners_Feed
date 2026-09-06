#!/usr/bin/env python3
"""Run deterministic model quality checks on a golden pipeline run.

The production model can be too heavy for pull-request runners, so this gate
accepts either a real golden run directory or the checked-in contract fixture.
The same checks are used before report generation by the worker contract
validator and during release verification.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

try:
    from .validate_artifacts import validate_run
except ImportError:
    from validate_artifacts import validate_run


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"quality baseline must be an object: {path}")
    return value


def evaluate_run(run_dir: Path, baseline_path: Path) -> dict[str, Any]:
    contract = validate_run(run_dir)
    baseline = _load_json(baseline_path)
    outputs = run_dir / "outputs"
    details = _load_json(outputs / "details.json")
    predictions = _load_json(outputs / "pose_predictions.json")
    features = _load_json(outputs / "feature_results.json")

    required_features = baseline.get("required_feature_ids", [])
    missing = [feature_id for feature_id in required_features if feature_id not in features]
    if missing:
        raise ValueError(f"missing required features: {', '.join(missing)}")

    frame_count = len(predictions["frames"])
    tracked_count = 0
    for frame in predictions["frames"]:
        people = frame.get("people", []) if isinstance(frame, dict) else []
        if any(
            isinstance(person, dict) and person.get("track_id") == 0
            for person in people
        ):
            tracked_count += 1
    tracking_coverage = tracked_count / frame_count if frame_count else 0.0
    minimum_coverage = float(baseline.get("min_tracking_coverage", 0.0))
    if tracking_coverage < minimum_coverage:
        raise ValueError(
            f"tracking coverage {tracking_coverage:.4f} is below "
            f"{minimum_coverage:.4f}"
        )

    bounds = baseline.get("feature_bounds", {})
    if not isinstance(bounds, dict):
        raise ValueError("feature_bounds must be an object")
    for feature_id, rule in bounds.items():
        feature = features.get(feature_id)
        if not isinstance(feature, dict) or not isinstance(rule, dict):
            raise ValueError(f"invalid quality rule for feature: {feature_id}")
        value = feature.get("value")
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"feature value is not finite: {feature_id}")
        minimum = rule.get("min")
        maximum = rule.get("max")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise ValueError(f"feature below minimum: {feature_id}")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise ValueError(f"feature above maximum: {feature_id}")
        if feature.get("unit") != rule.get("unit"):
            raise ValueError(f"feature unit changed: {feature_id}")

    runtime_seconds = details.get("runtime_seconds")
    if runtime_seconds is None and isinstance(details.get("video"), dict):
        runtime_seconds = details["video"].get("runtime_seconds")
    max_runtime = baseline.get("max_runtime_seconds")
    if isinstance(max_runtime, (int, float)) and runtime_seconds is not None:
        if not isinstance(runtime_seconds, (int, float)) or runtime_seconds > max_runtime:
            raise ValueError("model runtime exceeded the quality budget")

    return {
        "status": "ok",
        "contract": contract,
        "tracking_coverage": round(tracking_coverage, 4),
        "feature_ids": sorted(features),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: quality_gate.py RUN_DIR BASELINE_JSON", file=sys.stderr)
        return 2
    try:
        result = evaluate_run(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"MODEL_QUALITY_GATE_FAILED={error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
