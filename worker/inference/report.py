from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from inference.evidence import retrieve_evidence
from inference.narrative import generate_narrative_safe


KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "head",
    "neck",
    "hip_center",
    "left_big_toe",
    "right_big_toe",
    "left_small_toe",
    "right_small_toe",
    "left_heel",
    "right_heel",
)


def _mean(values: Iterable[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return statistics.fmean(finite) if finite else None


def _percentile(values: Iterable[float], quantile: float) -> float | None:
    finite = sorted(value for value in values if math.isfinite(value))
    if not finite:
        return None
    position = (len(finite) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return finite[lower]
    weight = position - lower
    return finite[lower] * (1 - weight) + finite[upper] * weight


def _point_average(*points: list[float]) -> list[float] | None:
    if not points or any(len(point) != 2 for point in points):
        return None
    if any(not all(math.isfinite(value) for value in point) for point in points):
        return None
    return [
        statistics.fmean(point[0] for point in points),
        statistics.fmean(point[1] for point in points),
    ]


def _angle(first: list[float], vertex: list[float], third: list[float]) -> float | None:
    first_vector = [first[0] - vertex[0], first[1] - vertex[1]]
    third_vector = [third[0] - vertex[0], third[1] - vertex[1]]
    first_norm = math.hypot(*first_vector)
    third_norm = math.hypot(*third_vector)
    if first_norm <= 1e-9 or third_norm <= 1e-9:
        return None
    cosine = sum(a * b for a, b in zip(first_vector, third_vector)) / (
        first_norm * third_norm
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _flexion(first: list[float], vertex: list[float], third: list[float]) -> float | None:
    internal_angle = _angle(first, vertex, third)
    return 180.0 - internal_angle if internal_angle is not None else None


def _angle_from_vertical(lower: list[float], upper: list[float]) -> float | None:
    """Return the unsigned 2-D angle between a body segment and vertical."""
    dx = upper[0] - lower[0]
    dy = upper[1] - lower[1]
    if math.hypot(dx, dy) <= 1e-9:
        return None
    return math.degrees(math.atan2(abs(dx), abs(dy)))


def _support_side(points: list[list[float] | None]) -> str | None:
    """Choose the lower foot as a per-frame stance-side approximation."""
    foot_indices = {
        "left": (15, 20, 22, 24),
        "right": (16, 21, 23, 25),
    }
    foot_heights: dict[str, float] = {}
    for side, indices in foot_indices.items():
        available = [points[index] for index in indices if points[index] is not None]
        if available:
            foot_heights[side] = statistics.fmean(point[1] for point in available)
    return max(foot_heights, key=foot_heights.get) if foot_heights else None


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None and math.isfinite(value) else None


def _metric(
    metric_id: str,
    label: str,
    value: float | None,
    unit: str,
    description: str,
    measurement_basis: str,
    evidence_query: list[str],
) -> dict[str, object]:
    return {
        "id": metric_id,
        "label": label,
        "value": _round(value),
        "unit": unit,
        "description": description,
        "measurement_basis": measurement_basis,
        "evidence_query": evidence_query,
    }


def generate_report(details: dict, predictions: dict) -> dict:
    frames = predictions.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("pose_predictions.json must contain non-empty frames")

    tracked_frames = 0
    observed_count = 0
    keypoint_count = 0
    score_values: list[float] = []
    joint_scores: list[list[float]] = [[] for _ in KEYPOINT_NAMES]
    postural_lean_values: list[float] = []
    torso_flexion_values: list[float] = []
    stance_hip_flexion_values: list[float] = []
    stance_knee_flexion_values: list[float] = []
    stance_side_counts = {"left": 0, "right": 0}

    for frame in frames:
        people = frame.get("people", []) if isinstance(frame, dict) else []
        person = next(
            (item for item in people if item.get("track_id") == 0),
            None,
        )
        if person is None:
            continue

        raw_points = person.get("keypoints", [])
        observed = person.get("observed", [])
        imputed = person.get("imputed_keypoints", [])
        scores = person.get("keypoint_scores", [])
        if not (
            len(raw_points) == len(observed) == len(imputed) == len(scores) == 26
        ):
            continue

        points: list[list[float] | None] = []
        for index, raw_point in enumerate(raw_points):
            selected = raw_point if observed[index] else imputed[index]
            if (
                isinstance(selected, list)
                and len(selected) == 2
                and all(isinstance(value, (int, float)) for value in selected)
            ):
                points.append([float(selected[0]), float(selected[1])])
            else:
                points.append(None)

            score = float(scores[index])
            if math.isfinite(score):
                score_values.append(score)
                joint_scores[index].append(score)
            keypoint_count += 1
            observed_count += int(bool(observed[index]))

        tracked_frames += 1
        pelvis = (
            _point_average(points[11], points[12])
            if points[11] is not None and points[12] is not None
            else None
        )
        neck = points[18]
        if neck is not None and pelvis is not None:
            value = _angle_from_vertical(pelvis, neck)
            if value is not None:
                torso_flexion_values.append(value)

        support_side = _support_side(points)
        if support_side is None:
            continue
        stance_side_counts[support_side] += 1

        side_indices = {
            "left": (11, 13, 15),
            "right": (12, 14, 16),
        }
        hip, knee, ankle = side_indices[support_side]

        if neck is not None and points[ankle] is not None:
            value = _angle_from_vertical(points[ankle], neck)
            if value is not None:
                postural_lean_values.append(value)

        if neck is not None and points[hip] is not None and points[knee] is not None:
            value = _flexion(neck, points[hip], points[knee])
            if value is not None:
                stance_hip_flexion_values.append(value)

        if all(points[index] is not None for index in (hip, knee, ankle)):
            value = _flexion(points[hip], points[knee], points[ankle])
            if value is not None:
                stance_knee_flexion_values.append(value)

    if tracked_frames == 0:
        raise ValueError("No primary runner track was found")

    video = details.get("video", {}) if isinstance(details, dict) else {}
    low_confidence = sorted(
        (
            {
                "keypoint": KEYPOINT_NAMES[index],
                "average_score": _round(_mean(values)),
            }
            for index, values in enumerate(joint_scores)
            if values
        ),
        key=lambda item: item["average_score"],
    )[:5]

    metrics = [
        _metric(
            "postural_lean_angle_deg",
            "전신 전경사",
            _mean(postural_lean_values),
            "°",
            "지지측 후보 발목에서 목으로 향하는 선과 수직선의 평균 절대각입니다.",
            "Halpe26 stance ankle-to-neck proxy for the paper's ankle-to-C7 angle",
            ["postural lean angle", "upright moderate large lean"],
        ),
        _metric(
            "torso_flexion_angle_deg",
            "몸통 굴곡",
            _mean(torso_flexion_values),
            "°",
            "골반 중심에서 목으로 향하는 선과 수직선의 평균 절대각입니다.",
            "Halpe26 hip-center-to-neck proxy for the paper's sacrum-to-C7 angle",
            ["torso flexion angle", "ankle versus torso lean strategy"],
        ),
        _metric(
            "peak_hip_flexion_stance_deg",
            "지지 구간 고관절 최대 굴곡",
            _percentile(stance_hip_flexion_values, 0.95),
            "°",
            "지지측 후보 프레임에서 몸통과 대퇴 사이 굴곡각의 95백분위입니다.",
            "2-D neck-hip-knee proxy during per-frame stance-side approximation",
            ["peak hip flexion", "stance phase", "postural lean"],
        ),
        _metric(
            "peak_knee_flexion_stance_deg",
            "지지 구간 무릎 최대 굴곡",
            _percentile(stance_knee_flexion_values, 0.95),
            "°",
            "지지측 후보 프레임에서 무릎 굴곡각의 95백분위입니다.",
            "2-D hip-knee-ankle angle during per-frame stance-side approximation",
            ["peak knee flexion", "stance phase", "postural lean"],
        ),
    ]

    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video": {
            "duration_seconds": video.get("duration_seconds"),
            "fps": video.get("fps"),
            "frame_count": video.get("frame_count", len(frames)),
            "width": video.get("width"),
            "height": video.get("height"),
        },
        "tracking": {
            "tracked_frames": tracked_frames,
            "total_frames": len(frames),
            "coverage_pct": _round(tracked_frames / len(frames) * 100),
            "observed_keypoints_pct": _round(
                observed_count / keypoint_count * 100 if keypoint_count else None
            ),
            "average_keypoint_score_pct": _round(
                _mean(score_values) * 100 if score_values else None
            ),
            "lowest_confidence_keypoints": low_confidence,
            "stance_candidate_frames": sum(stance_side_counts.values()),
            "stance_side_counts": stance_side_counts,
        },
        "metrics": metrics,
        "notice": (
            "이 리포트는 2D 자세 추정 결과를 요약한 기술적 참고 자료입니다. "
            "촬영 각도와 가림에 영향을 받으며 의료 진단이나 부상 예측이 아닙니다."
        ),
    }


def generate_report_file(
    details_path: Path,
    predictions_path: Path,
    output_path: Path,
) -> dict:
    details = json.loads(details_path.read_text(encoding="utf-8"))
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    report = generate_report(details, predictions)
    report["evidence"] = retrieve_evidence(report["metrics"])
    report["narrative"] = generate_narrative_safe(report, report["evidence"])
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("details", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate_report_file(args.details, args.predictions, args.output)
    print(f"ANALYSIS_REPORT=PASS {args.output}")


if __name__ == "__main__":
    main()
