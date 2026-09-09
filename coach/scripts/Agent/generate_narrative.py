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
팔꿈치, 몸통 굽힘, 전신 기울기를 모두 검토하고 가장 필요한 교정 한두 개를 담은
한국어 한줄평 한 문장만 작성하세요. 최대 250자이며 제목, 목록, JSON, Markdown,
HTML, 영상 추천, 숫자, 점수, 단위, 피처 ID를 출력하지 마세요.
입력의 판정과 행동을 바꾸거나 새 조언을 만들지 마세요. 몸통 굽힘과 전신 기울기는
서로 다른 측정이므로 혼동하거나 교정 방향을 임의로 합치지 마세요.
coaching_action은 앞으로의 조언이고 interpretation은 규칙 판정이지 심박수, 운동자각도,
무릎 부하, 대사비용 또는 부상의 실측·진단이 아닙니다. 연구의 집단 결과를 개인에게
확정된 효과나 인과관계로 표현하지 마세요. cadence와 pace를 자세 피처와 연관 짓지 마세요.
중학생이 이해할 수 있는 짧고 자연스러운 '~해요', '~하세요' 말투를 사용하세요."""),
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
