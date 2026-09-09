#!/usr/bin/env python3
"""Build service-owned frame scores without modifying model artifacts."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

CRITERION_VERSION = "sehyeon-57e4938"
CONFIDENCE_LIMITATION = "초기 버전에서는 유효한 측정 결과를 신뢰 가능한 것으로 가정합니다."
FEATURES = {
    "Amplitude of pelvis oscillation": {"id": "feature1", "unit": "ratio", "value_path": "value", "aggregation": "mean across detected ground-contact phases", "reference_range": (0.028, 0.061), "research_reference": {"mean": 0.046, "standard_deviation": 0.007, "observed_min": 0.028, "observed_max": 0.061}, "visualization": {"kind": "range_bar", "x_axis": "aggregate_ratio", "placement": "summary_metrics"}},
    "Elbow angle": {"id": "feature2", "unit": "degree", "value_path": "range.mean", "aggregation": "mean across valid frames", "reference_range": (70.0, 110.0), "upper_inclusive": True, "denominator_policy": "evaluated_frames", "visualization": {"kind": "line", "x_axis": "measurable_frame", "placement": "feature_grid"}},
    "Trunk flexion angle": {"id": "feature3", "unit": "degree", "value_path": "value", "aggregation": "model GCT aggregate; score across all video frames", "reference_range": (10.9, 18.9), "upper_inclusive": False, "denominator_policy": "all_frames", "visualization": {"kind": "line", "x_axis": "video_frame", "placement": "feature_grid"}},
    "Postural lean angle": {"id": "feature4", "unit": "degree", "value_path": "value", "aggregation": "model GCT aggregate; score across all video frames", "reference_range": (1.7, 4.3), "upper_inclusive": False, "denominator_policy": "all_frames", "visualization": {"kind": "line", "x_axis": "video_frame", "placement": "feature_grid"}},
}

def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            return number
    return None

def _value_at(feature: dict[str, Any], path: str, label: str) -> float:
    value: Any = feature
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"{label} is missing {path}")
        value = value[part]
    number = _finite(value)
    if number is None:
        raise ValueError(f"{label}.{path} must be finite")
    return number

def _verdict(feature: dict[str, Any]) -> str:
    instruction = feature.get("instruction")
    return "maintain" if isinstance(instruction, str) and (instruction.lower().startswith("good") or "유지" in instruction) else "improve"

def _point(person: dict, index: int) -> tuple[float, float] | None:
    raw = person.get("keypoints")
    if not isinstance(raw, list) or index >= len(raw):
        return None
    observed = person.get("observed")
    imputed = person.get("imputed_keypoints")
    value = raw[index]
    if isinstance(observed, list) and index < len(observed) and not observed[index]:
        value = imputed[index] if isinstance(imputed, list) and index < len(imputed) else None
    if not isinstance(value, list) or len(value) != 2:
        return None
    x, y = _finite(value[0]), _finite(value[1])
    return (x, y) if x is not None and y is not None else None

def _angle(dx: float, dy: float) -> float | None:
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length <= 0:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, dy / length))))

def derive_pose_series(predictions: dict[str, Any], fps: float | None) -> dict[str, list[dict[str, Any]]]:
    output = {"feature3": [], "feature4": []}
    frames = predictions.get("frames")
    if not isinstance(frames, list):
        raise ValueError("pose_predictions.json frames must be a list")
    for fallback_index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            continue
        frame_index = frame.get("frame_num") if isinstance(frame.get("frame_num"), int) else fallback_index
        people = frame.get("people")
        primary = next((p for p in people if isinstance(p, dict) and p.get("track_id") == 0), None) if isinstance(people, list) else None
        if primary is None:
            continue
        left_shoulder, right_shoulder = _point(primary, 5), _point(primary, 6)
        left_hip, right_hip = _point(primary, 11), _point(primary, 12)
        neck, left_ankle = _point(primary, 18), _point(primary, 15)
        trunk = None
        if all(p is not None for p in (left_shoulder, right_shoulder, left_hip, right_hip)):
            shoulder = ((left_shoulder[0] + right_shoulder[0]) / 2, (left_shoulder[1] + right_shoulder[1]) / 2)
            hip = ((left_hip[0] + right_hip[0]) / 2, (left_hip[1] + right_hip[1]) / 2)
            trunk = _angle(shoulder[0] - hip[0], hip[1] - shoulder[1])
        lean = _angle(neck[0] - left_ankle[0], left_ankle[1] - neck[1]) if neck and left_ankle else None
        timestamp = round(frame_index / fps * 1000) if fps and fps > 0 else None
        for feature_id, value in (("feature3", trunk), ("feature4", lean)):
            if value is not None:
                output[feature_id].append({"frame_index": frame_index, "timestamp_ms": timestamp, "value": value, "confidence_pct": None})
    return output

def _elbow_series(values: object, fps: float | None, frame_indices: object = None) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    points = []
    indexed_frames = frame_indices if isinstance(frame_indices, list) else []
    for sample_index, value in enumerate(values):
        number = _finite(value)
        if number is not None:
            frame_index = indexed_frames[sample_index] if sample_index < len(indexed_frames) and isinstance(indexed_frames[sample_index], int) else sample_index
            points.append({"frame_index": frame_index, "timestamp_ms": round(frame_index / fps * 1000) if fps and fps > 0 else None, "value": number, "confidence_pct": None})
    return points

def _denominator_policy(definition: dict[str, Any], override: str | None = None) -> str:
    policy = override or definition.get("denominator_policy", "all_frames")
    if policy not in {"all_frames", "evaluated_frames"}:
        raise ValueError("denominator policy must be all_frames or evaluated_frames")
    return policy

def _score_item(item: dict[str, Any], definition: dict[str, Any], source_count: int, policy: str) -> None:
    series = item["series"]
    evaluated = len(series)
    item["source_frame_count"] = source_count
    item["evaluated_frame_count"] = evaluated
    item["evaluation_coverage_pct"] = round(evaluated / source_count * 100, 2) if source_count else None
    if definition["id"] == "feature1":
        item.update({"score": None, "score_method": "excluded from posture scoring", "denominator_policy": policy, "good_frame_count": 0})
        return
    low, high = definition["reference_range"]
    if definition["upper_inclusive"]:
        good = sum(low <= point["value"] <= high for point in series)
        interval = "inclusive"
    else:
        good = sum(low <= point["value"] < high for point in series)
        interval = "upper-exclusive"
    denominator = source_count if policy == "all_frames" else evaluated
    item.update({
        "good_frame_count": good,
        "denominator_policy": policy,
        "score": round(good / denominator * 100, 2) if denominator else None,
        "score_method": f"good frames / {'source frames' if policy == 'all_frames' else 'evaluated frames'} ({interval})",
    })
    if evaluated:
        series_mean = sum(point["value"] for point in series) / evaluated
        delta = abs(series_mean - item["representative_value"])
        item["representative_comparison"] = {"series_mean": round(series_mean, 6), "absolute_delta": round(delta, 6), "tolerance": 1.0, "matches": delta <= 1.0}

def normalize(raw: dict[str, Any], *, fps: float | None = None, source_frame_count: int | None = None, pose_series: dict[str, list[dict[str, Any]]] | None = None, denominator_policy: str | None = None) -> dict[str, Any]:
    explicit_source_count = isinstance(source_frame_count, int) and source_frame_count >= 0
    source_count = source_frame_count if explicit_source_count else 0
    pose_series = pose_series or {}
    normalized: dict[str, Any] = {}
    for raw_name, definition in FEATURES.items():
        feature = raw.get(raw_name)
        if not isinstance(feature, dict):
            raise ValueError(f"raw feature is missing or invalid: {raw_name}")
        feature_id = definition["id"]
        representative_value = (
            _finite(feature.get("value"))
            if feature_id == "feature1"
            else _value_at(feature, definition["value_path"], raw_name)
        )
        item = {
            "value": representative_value,
            "unit": definition["unit"],
            "representative_value": representative_value,
            "aggregation": definition["aggregation"], "measurement_source": "2d_pose",
            "source_feature": raw_name, "verdict": _verdict(feature),
            "confidence_level": "high", "confidence_pct": None,
            "confidence_assumed": True, "limitation": CONFIDENCE_LIMITATION,
            "visualization": definition["visualization"],
        }
        for source_key, target_key in (("range", "source_range"), ("boundary", "source_boundary"), ("instruction", "coaching_action"), ("outcome", "interpretation"), ("description", "description")):
            if source_key in feature:
                item[target_key] = feature[source_key]
        reference = definition.get("reference_range")
        if reference:
            item["reference_range"] = {"kind": "reference", "min": reference[0], "max": reference[1], "unit": definition["unit"], "criterion_version": CRITERION_VERSION, "evidence_ids": []}
        if feature_id == "feature1":
            low, high = definition["reference_range"]
            item["verdict"] = (
                "unavailable"
                if item["representative_value"] is None
                else "maintain" if low <= item["representative_value"] <= high
                else "improve"
            )
            item["research_reference"] = definition["research_reference"]
        item["series"] = _elbow_series(feature.get("value"), fps, feature.get("range", {}).get("frame_indices") if isinstance(feature.get("range"), dict) else None) if feature_id == "feature2" else list(pose_series.get(feature_id, []))
        policy = _denominator_policy(definition, denominator_policy)
        _score_item(item, definition, source_count if explicit_source_count else len(item["series"]), policy)
        normalized[feature_id] = item
    return normalized

def write_normalized(run_dir: Path) -> Path:
    output_dir = run_dir / "outputs"
    raw = json.loads((output_dir / "feature_results.json").read_text(encoding="utf-8"))
    details = json.loads((output_dir / "details.json").read_text(encoding="utf-8"))
    predictions_path = output_dir / "pose_predictions.json"
    predictions = json.loads(predictions_path.read_text(encoding="utf-8")) if predictions_path.is_file() else {"frames": []}
    video = details.get("video", {}) if isinstance(details, dict) else {}
    fps = _finite(video.get("fps"))
    frame_count = video.get("frame_count")
    if not isinstance(frame_count, int) or frame_count < 0:
        frames = predictions.get("frames", []) if isinstance(predictions, dict) else []
        frame_count = len(frames) if isinstance(frames, list) else 0
    result = normalize(raw, fps=fps, source_frame_count=frame_count, pose_series=derive_pose_series(predictions, fps))
    output_path = output_dir / "feature_results.service.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
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
