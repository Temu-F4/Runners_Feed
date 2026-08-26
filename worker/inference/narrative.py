from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field


class NarrativeFinding(BaseModel):
    feature_id: str
    interpretation: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    limitation: str = Field(min_length=1, max_length=800)


class NarrativeDraft(BaseModel):
    overall_summary: str = Field(min_length=1, max_length=1600)
    findings: list[NarrativeFinding] = Field(min_length=1, max_length=8)
    coaching_points: list[str] = Field(min_length=1, max_length=5)
    disclaimer: str = Field(min_length=1, max_length=800)


SYSTEM_PROMPT = """
당신은 2D 러닝 자세 측정 결과를 논문 근거와 함께 설명하는 리포트 작성기입니다.

반드시 다음 규칙을 지키세요.
1. 입력에 제공된 feature와 evidence만 사용합니다.
2. 입력된 모든 feature_id마다 finding을 정확히 하나씩 작성하며 누락하거나 중복하지 않습니다.
3. 모든 evidence_ids는 입력 evidence_id 중 하나만 사용합니다.
4. 측정값을 계산하거나 변경하지 않습니다.
5. 논문 표의 값은 실험 조건의 집단 평균이지 정상/비정상 기준이 아닙니다.
6. Halpe26 2D proxy와 Vicon 측정값이 동일하다고 표현하지 않습니다.
7. 영상만으로 러닝 경제성, 대사량, 근활성, 부상 위험을 측정했다고 말하지 않습니다.
8. 의학적 진단이나 치료 지시를 하지 않습니다.
9. 근거가 부족하면 한계에 명시합니다.
10. 한국어로 간결하고 실행 가능한 리포트를 작성합니다.
""".strip()


def _build_report_model():
    from langchain_ollama import ChatOllama

    api_key = os.environ["OLLAMA_API_KEY"]
    model = ChatOllama(
        model=os.getenv("OLLAMA_REPORT_MODEL", "gemma4:31b"),
        base_url=os.getenv("OLLAMA_BASE_URL", "https://ollama.com"),
        client_kwargs={
            "headers": {
                "Authorization": f"Bearer {api_key}",
            },
            "timeout": float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90")),
        },
        temperature=0.0,
    )
    return model


def _parse_draft(raw_draft: Any) -> NarrativeDraft:
    if isinstance(raw_draft, NarrativeDraft):
        return raw_draft
    if isinstance(raw_draft, dict):
        return NarrativeDraft.model_validate(raw_draft)

    content = getattr(raw_draft, "content", None)
    if not isinstance(content, str):
        raise ValueError("LLM response did not contain text content")

    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        if first_newline == -1:
            raise ValueError("LLM response contained an empty code block")
        stripped = stripped[first_newline + 1:-3].strip()
    return NarrativeDraft.model_validate_json(stripped)


def _validate_draft(
    draft: NarrativeDraft,
    metrics: list[dict],
    evidence: list[dict],
) -> None:
    metric_ids = {str(metric["id"]) for metric in metrics}
    finding_ids = [finding.feature_id for finding in draft.findings]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("LLM returned duplicate feature findings")
    if set(finding_ids) != metric_ids:
        raise ValueError("LLM findings must cover exactly the supplied features")

    evidence_by_id = {
        str(item["evidence_id"]): item
        for item in evidence
    }
    for finding in draft.findings:
        for evidence_id in finding.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                raise ValueError("LLM cited evidence that was not retrieved")
            allowed_features = set(item.get("feature_ids", []))
            if finding.feature_id not in allowed_features:
                raise ValueError("LLM cited evidence unrelated to the feature")


def generate_narrative(
    measurement_report: dict,
    evidence: list[dict],
    *,
    structured_model: Any | None = None,
) -> dict:
    metrics = measurement_report.get("metrics", [])
    if not metrics:
        raise ValueError("Measurement report must contain metrics")
    if not evidence:
        raise ValueError("Retrieved evidence must not be empty")

    model = structured_model or _build_report_model()
    request = {
        "measurements": [
            {
                "feature_id": metric["id"],
                "label": metric["label"],
                "value": metric["value"],
                "unit": metric["unit"],
                "measurement_basis": metric["measurement_basis"],
            }
            for metric in metrics
        ],
        "tracking_quality": measurement_report.get("tracking", {}),
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "page": item["page"],
                "section": item["section"],
                "feature_ids": item["feature_ids"],
                "text": item["text"],
                "caveat": item["caveat"],
                "source": item["source"],
            }
            for item in evidence
        ],
    }
    required_feature_ids = [str(metric["id"]) for metric in metrics]
    messages = [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            "다음 입력 JSON만 근거로 리포트를 작성하세요. "
            "설명이나 Markdown 없이 아래 JSON Schema를 만족하는 JSON 객체만 "
            "응답하세요. findings에는 REQUIRED_FEATURE_IDS의 각 ID를 정확히 "
            "한 번씩 모두 포함하세요.\nREQUIRED_FEATURE_IDS:\n"
            + json.dumps(required_feature_ids, ensure_ascii=False)
            + "\nOUTPUT_JSON_SCHEMA:\n"
            + json.dumps(
                NarrativeDraft.model_json_schema(),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\nINPUT_JSON:\n"
            + json.dumps(request, ensure_ascii=False, allow_nan=False),
        ),
    ]

    draft = None
    last_validation_error: ValueError | None = None
    for attempt in range(2):
        attempt_messages = list(messages)
        if attempt:
            attempt_messages.append(
                (
                    "human",
                    "이전 응답은 서버 검증을 통과하지 못했습니다. 다른 설명은 "
                    "추가하지 말고, 다음 feature_id 각각에 대해 finding을 정확히 "
                    "하나씩 포함한 완전한 JSON 객체를 다시 작성하세요: "
                    + json.dumps(required_feature_ids, ensure_ascii=False),
                )
            )
        raw_draft = model.invoke(attempt_messages)
        try:
            candidate = _parse_draft(raw_draft)
            _validate_draft(candidate, metrics, evidence)
            draft = candidate
            break
        except ValueError as error:
            last_validation_error = error

    if draft is None:
        if last_validation_error is None:
            raise ValueError("LLM response validation failed")
        raise last_validation_error

    metric_by_id = {str(metric["id"]): metric for metric in metrics}
    output = draft.model_dump()
    output["findings"] = [
        {
            **finding,
            "label": metric_by_id[finding["feature_id"]]["label"],
            "measured_value": metric_by_id[finding["feature_id"]]["value"],
            "unit": metric_by_id[finding["feature_id"]]["unit"],
        }
        for finding in output["findings"]
    ]
    return {
        "status": "success",
        "model": os.getenv("OLLAMA_REPORT_MODEL", "gemma4:31b"),
        **output,
    }


def generate_narrative_safe(measurement_report: dict, evidence: list[dict]) -> dict:
    enabled = os.getenv("LLM_REPORT_ENABLED", "false").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return {
            "status": "disabled",
            "message": "AI narrative generation is disabled",
        }
    if not os.getenv("OLLAMA_API_KEY"):
        return {
            "status": "unavailable",
            "error_code": "missing_ollama_api_key",
            "message": "측정 리포트는 생성됐지만 AI 해설을 생성할 수 없습니다.",
        }

    try:
        return generate_narrative(measurement_report, evidence)
    except Exception as error:
        return {
            "status": "unavailable",
            "error_code": type(error).__name__,
            "message": "측정 리포트는 생성됐지만 AI 해설을 생성할 수 없습니다.",
        }
