#!/usr/bin/env python3
"""Normalize model-owned feature output without changing the raw artifact."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


CRITERION_VERSION = "sehyeon-e2fe43e"

FEATURES = {
    "Amplitude of pelvis oscillation": {
        "id": "feature1",
        "unit": "ratio",
        "value_path": "value",
        "aggregation": "mean across detected ground-contact phases",
    },
    "Elbow angle": {
        "id": "feature2",
        "unit": "degree",
        "value_path": "range.mean",
        "aggregation": "mean across valid frames",
        "reference_range": (70.0, 90.0),
    },
    "Trunk flexion angle": {
        "id": "feature3",
        "unit": "degree",
        "value_path": "value",
        "aggregation": "mean across detected ground-contact phases",
        "reference_range": (10.9, 18.9),
    },
    "Postural lean angle": {
        "id": "feature4",
        "unit": "degree",
        "value_path": "value",
        "aggregation": "mean across detected ground-contact phases",
        "reference_range": (1.7, 4.3),
    },
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


def _verdict(feature: dict[str, Any]) -> str:
    instruction = feature.get("instruction")
    if isinstance(instruction, str) and (
        instruction.lower().startswith("good") or "유지" in instruction
    ):
        return "maintain"
    return "improve"


def _series(values: object, fps: float | None) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    points = []
    for frame_index, value in enumerate(values):
        try:
            number = _finite_number(value, f"Elbow angle.value[{frame_index}]")
        except ValueError:
            continue
        points.append({
            "frame_index": frame_index,
            "timestamp_ms": (
                round(frame_index / fps * 1000)
                if isinstance(fps, (int, float)) and fps > 0
                else None
            ),
            "value": number,
            "confidence_pct": None,
        })
    return points


def _score(item: dict[str, Any]) -> tuple[float | None, str | None]:
    reference = item.get("reference_range")
    if not isinstance(reference, dict):
        return None, None
    minimum = reference["min"]
    maximum = reference["max"]
    series = item.get("series")
    if isinstance(series, list) and series:
        values = [point["value"] for point in series]
        passing = sum(minimum <= value <= maximum for value in values)
        return round(passing / len(values) * 100, 2), "reference-band frame compliance"
    value = item["value"]
    return (100.0 if minimum <= value <= maximum else 0.0), "reference-band representative value"


def normalize(raw: dict[str, Any], *, fps: float | None = None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_name, definition in FEATURES.items():
        feature = raw.get(raw_name)
        if not isinstance(feature, dict):
            raise ValueError(f"raw feature is missing or invalid: {raw_name}")
        feature_id = definition["id"]
        unit = definition["unit"]
        item = {
            "value": _value_at(feature, definition["value_path"], raw_name),
            "unit": unit,
            "representative_value": _value_at(
                feature, definition["value_path"], raw_name
            ),
            "aggregation": definition["aggregation"],
            "measurement_source": "2d_pose",
            "source_feature": raw_name,
            "verdict": _verdict(feature),
        }
        for source_key, target_key in (
            ("range", "source_range"),
            ("boundary", "source_boundary"),
            ("instruction", "coaching_action"),
            ("outcome", "interpretation"),
            ("description", "description"),
        ):
            if source_key in feature:
                item[target_key] = feature[source_key]
        reference_range = definition.get("reference_range")
        if reference_range is not None:
            item["reference_range"] = {
                "kind": "reference",
                "min": reference_range[0],
                "max": reference_range[1],
                "unit": unit,
                "criterion_version": CRITERION_VERSION,
                "evidence_ids": [],
            }
        if feature_id == "feature2" and isinstance(feature.get("value"), list):
            item["series"] = _series(feature["value"], fps)
        score, score_method = _score(item)
        item["score"] = score
        item["score_method"] = score_method
        normalized[feature_id] = item
    return normalized


def write_normalized(run_dir: Path) -> Path:
    output_dir = run_dir / "outputs"
    raw_path = output_dir / "feature_results.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("feature_results.json must contain an object")
    fps = None
    details_path = output_dir / "details.json"
    if details_path.is_file():
        details = json.loads(details_path.read_text(encoding="utf-8"))
        if isinstance(details, dict) and isinstance(details.get("video"), dict):
            value = details["video"].get("fps")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                fps = float(value)
    output_path = output_dir / "feature_results.service.json"
    output_path.write_text(
        json.dumps(
            normalize(raw, fps=fps),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
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
