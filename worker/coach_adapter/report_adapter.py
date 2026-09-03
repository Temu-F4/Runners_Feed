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
        output.append(
            {
                "id": feature_id,
                "label": presentation["label"],
                "value": feature["value"],
                "unit": feature["unit"],
                "description": presentation["description"],
                "measurement_basis": presentation["measurement_basis"],
                "evidence_query": presentation["evidence_query"],
            }
        )
    return output


def _narrative(output_dir: Path) -> dict[str, Any]:
    report_path = output_dir / "running_report.md"
    if not report_path.is_file():
        return {
            "status": "disabled",
            "message": "AI 코칭은 설정되지 않았지만 측정 결과는 정상 생성됐습니다.",
        }

    report = report_path.read_text(encoding="utf-8").strip()
    if not report:
        return {
            "status": "unavailable",
            "message": "AI 코칭 결과가 비어 있습니다.",
            "error_code": "empty_coach_report",
        }

    return {
        "status": "success",
        "model": "gpt-5-nano",
        "overall_summary": report,
        "findings": [],
        "coaching_points": [],
        "disclaimer": (
            "이 내용은 러닝 동작 참고용이며 의료 진단이나 부상 예측이 아닙니다."
        ),
    }


def build_report(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    details = _load_json(output_dir / "details.json")
    predictions = _load_json(output_dir / "pose_predictions.json")
    features = _json_safe(
        _load_json(output_dir / "feature_results.json")
    )
    video = details.get("video", {})

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
        "evidence": [],
        "narrative": _narrative(output_dir),
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
