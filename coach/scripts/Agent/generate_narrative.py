#!/usr/bin/env python3
"""Generate only the free-text portion of the service-owned coaching narrative."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


ALLOWED_FIELDS = (
    "representative_value", "unit", "reference_range", "score",
    "good_frame_count", "evaluated_frame_count", "source_frame_count",
    "denominator_policy", "coaching_action", "interpretation", "verdict",
)


def narrative_input(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    features = json.loads((output_dir / "feature_results.service.json").read_text(encoding="utf-8"))
    selected = {
        feature_id: {key: value for key, value in feature.items() if key in ALLOWED_FIELDS}
        for feature_id, feature in features.items()
        if feature_id in {"feature2", "feature3", "feature4"} and isinstance(feature, dict)
    }
    raw_path = output_dir / "feature_results.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.is_file() else {}
    run_metrics = {
        key: raw.get(key) for key in ("cadence", "pace") if key in raw
    }
    return {"features": selected, "run_metrics": run_metrics}


def generate(run_dir: Path) -> Path:
    model_name = os.getenv("COACH_LLM_MODEL", "gpt-5.6-luna").strip()
    if not model_name:
        raise ValueError("COACH_LLM_MODEL must not be empty")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 러닝 자세 결과를 쉽게 설명하는 한국어 코치입니다.
입력의 판정과 행동만 요약하세요. 숫자, 점수, 단위, 피처 ID를 문장에 쓰지 마세요.
의료 진단이나 부상 예측을 하지 마세요. Markdown, HTML, 목록, 제목 없이
짧은 한국어 문장 세 개에서 다섯 개만 출력하세요."""),
        ("human", "검증된 측정 요약:\n{payload}"),
    ])
    report = (prompt | ChatOpenAI(model=model_name, temperature=0) | StrOutputParser()).invoke({
        "payload": json.dumps(narrative_input(run_dir), ensure_ascii=False),
    })
    path = run_dir / "outputs" / "running_report.md"
    path.write_text(report.strip(), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(generate(args.run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
