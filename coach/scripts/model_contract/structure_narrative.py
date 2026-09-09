#!/usr/bin/env python3
"""Convert the model-owned narrative into the service report contract."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _action(feature_id: str, feature: dict[str, Any]) -> dict[str, Any] | None:
    text = feature.get("coaching_action")
    if not isinstance(text, str) or not text.strip():
        return None
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
        "text": text.strip(),
        "measurement_reference": measurement,
    }


def build_structured_narrative(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    summary = (output_dir / "running_report.md").read_text(encoding="utf-8").strip()
    if not summary:
        raise ValueError("running_report.md is empty")
    features = _load_object(output_dir / "feature_results.service.json")
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
    return {
        "status": "success",
        "model": os.getenv("COACH_LLM_MODEL", "gpt-5.6-luna"),
        "prompt_version": "sehyeon-narrative-v1",
        "overall_summary": summary,
        "priority_actions": priority,
        "maintain_actions": maintain,
        "disclaimer": "러닝 동작 참고용이며 의료 진단이나 부상 예측이 아닙니다.",
        "validator_version": "service-narrative-1",
    }


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
