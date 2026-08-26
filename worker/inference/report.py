from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


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


def _std(values: Iterable[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return statistics.pstdev(finite) if len(finite) > 1 else 0.0 if finite else None


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


def _range_90(values: Iterable[float]) -> float | None:
    finite = list(values)
    low = _percentile(finite, 0.05)
    high = _percentile(finite, 0.95)
    return high - low if low is not None and high is not None else None


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


def _torso_lean(shoulder: list[float], pelvis: list[float]) -> float | None:
    dx = shoulder[0] - pelvis[0]
    dy = shoulder[1] - pelvis[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return None
    vertical_up = [0.0, -1.0]
    cosine = (dx * vertical_up[0] + dy * vertical_up[1]) / length
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None and math.isfinite(value) else None


def _metric(
    metric_id: str,
    label: str,
    value: float | None,
    unit: str,
    description: str,
) -> dict[str, object]:
    return {
        "id": metric_id,
        "label": label,
        "value": _round(value),
        "unit": unit,
        "description": description,
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
    torso_values: list[float] = []
    knee_values = {"left": [], "right": []}
    elbow_values = {"left": [], "right": []}

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
        shoulder = (
            _point_average(points[5], points[6])
            if points[5] is not None and points[6] is not None
            else None
        )
        pelvis = (
            _point_average(points[11], points[12])
            if points[11] is not None and points[12] is not None
            else None
        )
        if shoulder is not None and pelvis is not None:
            value = _torso_lean(shoulder, pelvis)
            if value is not None:
                torso_values.append(value)

        for side, indices in {
            "left": (11, 13, 15, 5, 7, 9),
            "right": (12, 14, 16, 6, 8, 10),
        }.items():
            hip, knee, ankle, shoulder_index, elbow, wrist = indices
            if all(points[index] is not None for index in (hip, knee, ankle)):
                value = _flexion(points[hip], points[knee], points[ankle])
                if value is not None:
                    knee_values[side].append(value)
            if all(
                points[index] is not None
                for index in (shoulder_index, elbow, wrist)
            ):
                value = _flexion(
                    points[shoulder_index],
                    points[elbow],
                    points[wrist],
                )
                if value is not None:
                    elbow_values[side].append(value)

    if tracked_frames == 0:
        raise ValueError("No primary runner track was found")

    left_knee_rom = _range_90(knee_values["left"])
    right_knee_rom = _range_90(knee_values["right"])
    rom_mean = _mean(
        value for value in (left_knee_rom, right_knee_rom) if value is not None
    )
    knee_asymmetry = (
        abs(left_knee_rom - right_knee_rom) / rom_mean * 100
        if left_knee_rom is not None
        and right_knee_rom is not None
        and rom_mean is not None
        and rom_mean > 1e-9
        else None
    )

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
            "torso_lean_mean_deg",
            "상체 기울기 평균",
            _mean(torso_values),
            "°",
            "골반 중심에서 어깨 중심으로 향하는 선과 수직선의 각도입니다.",
        ),
        _metric(
            "torso_lean_variability_deg",
            "상체 기울기 변동",
            _std(torso_values),
            "°",
            "전체 프레임에서 상체 기울기가 얼마나 달라졌는지 나타냅니다.",
        ),
        _metric(
            "left_knee_rom_deg",
            "왼쪽 무릎 가동범위",
            left_knee_rom,
            "°",
            "극단값 영향을 줄인 5~95 백분위 무릎 굽힘 범위입니다.",
        ),
        _metric(
            "right_knee_rom_deg",
            "오른쪽 무릎 가동범위",
            right_knee_rom,
            "°",
            "극단값 영향을 줄인 5~95 백분위 무릎 굽힘 범위입니다.",
        ),
        _metric(
            "knee_rom_asymmetry_pct",
            "무릎 가동범위 좌우 차이",
            knee_asymmetry,
            "%",
            "좌우 무릎 가동범위 차이를 두 값의 평균으로 나눈 참고값입니다.",
        ),
        _metric(
            "left_elbow_rom_deg",
            "왼쪽 팔꿈치 가동범위",
            _range_90(elbow_values["left"]),
            "°",
            "달리는 동안 왼쪽 팔꿈치 굽힘 각도의 5~95 백분위 범위입니다.",
        ),
        _metric(
            "right_elbow_rom_deg",
            "오른쪽 팔꿈치 가동범위",
            _range_90(elbow_values["right"]),
            "°",
            "달리는 동안 오른쪽 팔꿈치 굽힘 각도의 5~95 백분위 범위입니다.",
        ),
    ]

    return {
        "schema_version": "1.0",
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
