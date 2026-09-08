#!/usr/bin/env python3
"""Normalize model-owned feature output without changing the raw artifact."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


FEATURES = {
    "Amplitude of pelvis oscillation": ("feature1", "ratio", "value"),
    "Elbow angle": ("feature2", "degree", "range.mean"),
    "Trunk flexion angle": ("feature3", "degree", "value"),
    "Postural lean angle": ("feature4", "degree", "value"),
}


def _finite_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _value_at(feature: dict[str, Any], path: str, label: str) -> float:
    value: Any = feature
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"{label} is missing {path}")
        value = value[part]
    return _finite_number(value, f"{label}.{path}")


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_name, (feature_id, unit, value_path) in FEATURES.items():
        feature = raw.get(raw_name)
        if not isinstance(feature, dict):
            raise ValueError(f"raw feature is missing or invalid: {raw_name}")
        item = {
            "value": _value_at(feature, value_path, raw_name),
            "unit": unit,
            "measurement_source": "2d_pose",
            "source_feature": raw_name,
        }
        for source_key, target_key in (
            ("range", "reference_range"),
            ("boundary", "reference_range"),
            ("instruction", "coaching_action"),
            ("outcome", "interpretation"),
            ("description", "description"),
        ):
            if source_key in feature:
                item[target_key] = feature[source_key]
        if feature_id == "feature2" and isinstance(feature.get("value"), list):
            item["series"] = feature["value"]
        normalized[feature_id] = item
    return normalized


def write_normalized(run_dir: Path) -> Path:
    output_dir = run_dir / "outputs"
    raw_path = output_dir / "feature_results.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("feature_results.json must contain an object")
    output_path = output_dir / "feature_results.service.json"
    output_path.write_text(
        json.dumps(normalize(raw), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        print(write_normalized(args.run_dir))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"MODEL_CONTRACT_INVALID={error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
