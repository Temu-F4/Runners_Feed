#!/usr/bin/env python3
"""Convert the model-owned narrative into the service report contract."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from coach.scripts.model_contract.exercise_video_tool import recommend_exercise_videos
except ModuleNotFoundError:  # Direct execution inside the coach container.
    from scripts.model_contract.exercise_video_tool import recommend_exercise_videos

MAX_SUMMARY_CHARS = 250
MAX_ACTIONS = 3
BLOCKED_MARKUP = ("```", "<script", "<table", "</", "|---", "# ")
BLOCKED_MEDICAL = ("진단", "부상 확정", "부상이 발생", "질환", "치료가 필요")


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _action(feature_id: str, feature: dict[str, Any]) -> dict[str, Any] | None:
    text = feature.get("coaching_action")
    if not isinstance(text, str) or not text.strip():
        return None
    text = " ".join(text.split())
    if len(text) > 240 or any(token in text.lower() for token in BLOCKED_MARKUP):
        raise ValueError(f"invalid action text for {feature_id}")
    if any(token in text for token in BLOCKED_MEDICAL):
        raise ValueError(f"medical claim in action text for {feature_id}")
    reference = feature.get("reference_range")
    measurement = None
    if isinstance(reference, dict):
        measurement = {
            "value": feature.get("representative_value"),
            "unit": feature.get("unit", ""),
            "reference_min": reference.get("min"),
            "reference_max": reference.get("max"),
        }
    return {
        "feature_id": feature_id,
        "text": text,
        "measurement_reference": measurement,
    }


def _validate_summary(summary: str) -> str:
    summary = " ".join(summary.split())
    if not summary or len(summary) > MAX_SUMMARY_CHARS:
        raise ValueError("overall_summary is empty or too long")
    lowered = summary.lower()
    if any(token in lowered for token in BLOCKED_MARKUP):
        raise ValueError("overall_summary contains markup")
    if any(token in summary for token in BLOCKED_MEDICAL):
        raise ValueError("overall_summary contains a medical claim")
    if re.search(r"\d", summary):
        raise ValueError("overall_summary must not contain unverifiable numbers")
    sentences = [part for part in re.split(r"(?<=[.!?。])\s*", summary) if part.strip()]
    if len(sentences) != 1:
        raise ValueError("overall_summary must contain exactly one sentence")
    return summary


def build_structured_narrative(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    summary = _validate_summary(
        (output_dir / "running_report.md").read_text(encoding="utf-8")
    )
    features = _load_object(output_dir / "feature_results.service.json")
    raw_features = _load_object(output_dir / "feature_results.json")
    priority: list[dict[str, Any]] = []
    maintain: list[dict[str, Any]] = []
    for feature_id in ("feature2", "feature3", "feature4"):
        feature = features.get(feature_id)
        if not isinstance(feature, dict):
            continue
        action = _action(feature_id, feature)
        if action is None:
            continue
        (maintain if feature.get("verdict") == "maintain" else priority).append(action)
    result = {
        "status": "success",
        "model": os.getenv("COACH_LLM_MODEL", "gpt-5.6-luna"),
        "prompt_version": "sehyeon-5ccb8bc-narrative-v3",
        "overall_summary": summary,
        "priority_actions": priority,
        "maintain_actions": maintain,
        "disclaimer": "러닝 동작 참고용이며 의료 진단이나 부상 예측이 아닙니다.",
        "exercise_videos": recommend_exercise_videos(raw_features),
        "validator_version": "service-narrative-3",
    }
    actions = priority + maintain
    if len(actions) > MAX_ACTIONS or len({item["feature_id"] for item in actions}) != len(actions):
        raise ValueError("narrative actions are duplicated or exceed the limit")
    return result


def write_structured_narrative(run_dir: Path) -> Path:
    output_path = run_dir / "outputs" / "running_report.json"
    output_path.write_text(
        json.dumps(build_structured_narrative(run_dir), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        print(write_structured_narrative(args.run_dir))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"NARRATIVE_CONTRACT_INVALID={error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
