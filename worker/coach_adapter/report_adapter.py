from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEATURE_PRESENTATION = {
    "feature1": {
        "label": "키 대비 골반 수직진동",
        "description": (
            "지면 접촉 구간의 골반 수직 이동량을 사용자의 키로 "
            "정규화한 값입니다."
        ),
        "measurement_basis": "Coach feature1 output without recalculation",
        "evidence_query": ["pelvis vertical oscillation", "body height ratio"],
    },
    "feature2": {
        "label": "팔꿈치 각도",
        "description": "러닝 중 팔꿈치 각도의 평균값입니다.",
        "measurement_basis": "Coach elbow-angle mean without recalculation",
        "evidence_query": ["running elbow angle", "running economy"],
    },
    "feature3": {
        "label": "몸통 굽힘 각도",
        "description": "지지 구간에서 계산한 몸통 굽힘 각도입니다.",
        "measurement_basis": "Coach trunk-flexion output without recalculation",
        "evidence_query": ["running trunk flexion"],
    },
    "feature4": {
        "label": "상체 기울기",
        "description": "지지 구간에서 계산한 상체 기울기 각도입니다.",
        "measurement_basis": "Coach postural-lean output without recalculation",
        "evidence_query": ["running postural lean"],
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 2)


def _metric_value(raw: object, expected_unit: str) -> float | None:
    if isinstance(raw, dict):
        if raw.get("unit") != expected_unit:
            return None
        raw = raw.get("value")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    value = float(raw)
    return value if math.isfinite(value) and value > 0 else None


def _format_pace(decimal_minutes: float) -> str:
    total_seconds = round(decimal_minutes * 60)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d} /km"


def _run_metrics(output_dir: Path, details: dict) -> dict[str, Any] | None:
    configured = details.get("run_metrics")
    if isinstance(configured, dict):
        return configured
    raw_path = output_dir / "feature_results.json"
    if not raw_path.is_file():
        return None
    raw = _load_json(raw_path)
    cadence = _metric_value(raw.get("cadence"), "spm")
    pace = _metric_value(raw.get("pace"), "min_per_km")
    if cadence is None and pace is None:
        return None
    return {
        "cadence_spm": round(cadence, 1) if cadence is not None else None,
        "pace_per_km": _format_pace(pace) if pace is not None else None,
        "stride_length_m": None,
        "estimation_basis": "model cadence/pace estimate from two detected gait events",
    }


def _tracking_summary(details: dict, predictions: dict) -> dict[str, Any]:
    frames = predictions.get("frames", [])
    if not isinstance(frames, list):
        raise ValueError("pose_predictions.json frames must be a list")

    tracked_frames = 0
    observed_count = 0
    keypoint_count = 0
    score_total = 0.0
    score_count = 0

    for frame in frames:
        people = frame.get("people", []) if isinstance(frame, dict) else []
        primary = next(
            (
                person
                for person in people
                if isinstance(person, dict) and person.get("track_id") == 0
            ),
            None,
        )
        if primary is None:
            continue

        tracked_frames += 1
        scores = primary.get("keypoint_scores", [])
        observed = primary.get("observed", [])
        if isinstance(scores, list):
            for score in scores:
                if isinstance(score, (int, float)) and math.isfinite(score):
                    score_total += float(score)
                    score_count += 1
        if isinstance(observed, list):
            observed_count += sum(bool(value) for value in observed)
            keypoint_count += len(observed)

    video = details.get("video", {})
    source_frames = video.get("frame_count", len(frames))
    total_frames = source_frames if isinstance(source_frames, int) else len(frames)

    return {
        "tracked_frames": tracked_frames,
        "total_frames": total_frames,
        "coverage_pct": _percentage(tracked_frames, total_frames),
        "observed_keypoints_pct": _percentage(observed_count, keypoint_count),
        "average_keypoint_score_pct": (
            round(score_total / score_count * 100, 2)
            if score_count
            else None
        ),
    }


def _metrics(features: dict) -> list[dict[str, Any]]:
    output = []
    for feature_id, feature in features.items():
        if not isinstance(feature, dict):
            raise ValueError(f"Feature must be a JSON object: {feature_id}")
        if "value" not in feature or "unit" not in feature:
            raise ValueError(f"Feature is missing value or unit: {feature_id}")

        presentation = FEATURE_PRESENTATION.get(
            feature_id,
            {
                "label": feature_id,
                "description": "Coach 파이프라인이 계산한 러닝 자세 지표입니다.",
                "measurement_basis": "Coach feature output without recalculation",
                "evidence_query": [],
            },
        )
        metric = {
                "id": feature_id,
                "label": presentation["label"],
                "value": feature["value"],
                "unit": feature["unit"],
                "description": presentation["description"],
                "measurement_basis": presentation["measurement_basis"],
                "evidence_query": presentation["evidence_query"],
        }
        for key in (
            "reference_range",
            "coaching_action",
            "interpretation",
            "score",
            "score_method",
            "denominator_policy",
            "good_frame_count",
            "evaluated_frame_count",
            "source_frame_count",
            "evaluation_coverage_pct",
            "confidence_level",
            "confidence_pct",
            "confidence_assumed",
            "limitation",
            "series",
            "visualization",
        ):
            if key in feature:
                metric[key] = feature[key]
        output.append(metric)
    return output


def _narrative(output_dir: Path) -> dict[str, Any]:
    structured_path = output_dir / "running_report.json"
    if structured_path.is_file():
        structured = _load_json(structured_path)
        status = structured.get("status")
        if status not in {"success", "unavailable", "disabled"}:
            raise ValueError(
                "running_report.json status must be success, unavailable, or disabled"
            )
        return {
            "status": status,
            "model": structured.get("model"),
            "overall_summary": structured.get(
                "overall_summary", structured.get("summary")
            ),
            "priority_actions": structured.get(
                "priority_actions", structured.get("priorityActions", [])
            ),
            "maintain_actions": structured.get(
                "maintain_actions", structured.get("maintainActions", [])
            ),
            "disclaimer": structured.get(
                "disclaimer",
                "이 내용은 러닝 동작 참고용이며 의료 진단이나 부상 예측이 아닙니다.",
            ),
            "validator_version": structured.get(
                "validator_version", structured.get("validatorVersion", "unvalidated")
            ),
            "prompt_version": structured.get("prompt_version"),
            "error_code": structured.get("error_code"),
        }
    return {
        "status": "disabled",
        "message": "검증된 AI 코칭은 없지만 측정 결과는 정상 생성됐습니다.",
    }


def build_report(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    details = _load_json(output_dir / "details.json")
    predictions = _load_json(output_dir / "pose_predictions.json")
    features = _json_safe(
        _load_json(output_dir / "feature_results.service.json")
    )
    video = details.get("video", {})
    run_metrics = _run_metrics(output_dir, details)
    scored = [
        feature.get("score") for feature_id, feature in features.items()
        if feature_id in {"feature2", "feature3", "feature4"}
        and isinstance(feature, dict)
        and isinstance(feature.get("score"), (int, float))
    ]
    narrative = _narrative(output_dir)

    return {
        "schema_version": "coach-1.0",
        "source": "coach",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video": {
            "duration_seconds": video.get("duration_seconds"),
            "fps": video.get("fps"),
            "frame_count": video.get("frame_count", 0),
            "width": video.get("width"),
            "height": video.get("height"),
        },
        "tracking": _tracking_summary(details, predictions),
        "metrics": _metrics(features),
        "features": features,
        "posture_score": round(sum(scored) / 3, 2) if len(scored) == 3 else None,
        # These values are supplied by the analysis pipeline when available. The
        # adapter intentionally does not invent pace or cadence from video length.
        "run_metrics": run_metrics,
        "evidence": [],
        "narrative": narrative,
        "runtime_metadata": {
            "prompt_version": narrative.get("prompt_version"),
            "model": narrative.get("model"),
            "validator_version": narrative.get("validator_version"),
            "input_tokens": None,
            "output_tokens": None,
        },
        "notice": (
            "Coach 계산 결과를 서비스 형식으로 표시합니다. 촬영 각도와 가림에 "
            "영향을 받으며 의료 진단이나 부상 예측이 아닙니다."
        ),
    }


def write_report(run_dir: Path) -> Path:
    output_path = run_dir / "outputs" / "report.json"
    output_path.write_text(
        json.dumps(
            build_report(run_dir),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(write_report(args.run_dir))


if __name__ == "__main__":
    main()
