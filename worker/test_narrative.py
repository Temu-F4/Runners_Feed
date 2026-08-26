import json
import os
import unittest
from unittest.mock import patch

from inference.evidence import retrieve_evidence
from inference.narrative import generate_narrative, generate_narrative_safe


def _measurement_report() -> dict:
    metrics = [
        {
            "id": "postural_lean_angle_deg",
            "label": "전신 전경사",
            "value": 5.2,
            "unit": "°",
            "measurement_basis": "2-D proxy",
            "evidence_query": ["postural lean angle"],
        },
        {
            "id": "torso_flexion_angle_deg",
            "label": "몸통 굴곡",
            "value": 12.1,
            "unit": "°",
            "measurement_basis": "2-D proxy",
            "evidence_query": ["torso flexion angle"],
        },
    ]
    return {"metrics": metrics, "tracking": {"coverage_pct": 98.0}}


class FakeStructuredModel:
    def __init__(self, findings: list[dict]):
        self.findings = findings

    def invoke(self, _messages):
        return {
            "overall_summary": "측정값을 논문의 실험 조건과 참고 비교했습니다.",
            "findings": self.findings,
            "coaching_points": ["과도한 변화보다 편안한 자세를 유지해 보세요."],
            "disclaimer": "2D 추정 결과이며 의료 진단이 아닙니다.",
        }


class FakeRawMessage:
    def __init__(self, content: str):
        self.content = content


class FakeRawModel(FakeStructuredModel):
    def invoke(self, messages):
        content = super().invoke(messages)
        return FakeRawMessage(json.dumps(content, ensure_ascii=False))


class NarrativeHarnessTest(unittest.TestCase):
    def test_parses_cloud_json_text_before_harness_validation(self) -> None:
        report = _measurement_report()
        evidence = retrieve_evidence(report["metrics"])
        result = generate_narrative(
            report,
            evidence,
            structured_model=FakeRawModel(
                [
                    {
                        "feature_id": metric["id"],
                        "interpretation": "실험 조건의 참고값과 비교할 수 있습니다.",
                        "evidence_ids": [
                            next(
                                item["evidence_id"]
                                for item in evidence
                                if metric["id"] in item["feature_ids"]
                            )
                        ],
                        "limitation": "Halpe26 2D proxy 측정입니다.",
                    }
                    for metric in report["metrics"]
                ]
            ),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["findings"]), 2)

    def test_preserves_server_measurements_and_validates_evidence(self) -> None:
        report = _measurement_report()
        evidence = retrieve_evidence(report["metrics"])
        result = generate_narrative(
            report,
            evidence,
            structured_model=FakeStructuredModel(
                [
                    {
                        "feature_id": metric["id"],
                        "interpretation": "실험 조건의 참고값과 비교할 수 있습니다.",
                        "evidence_ids": [
                            next(
                                item["evidence_id"]
                                for item in evidence
                                if metric["id"] in item["feature_ids"]
                            )
                        ],
                        "limitation": "Halpe26 2D proxy 측정입니다.",
                    }
                    for metric in report["metrics"]
                ]
            ),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            [finding["measured_value"] for finding in result["findings"]],
            [5.2, 12.1],
        )

    def test_rejects_unretrieved_evidence(self) -> None:
        report = _measurement_report()
        evidence = retrieve_evidence(report["metrics"])
        findings = [
            {
                "feature_id": metric["id"],
                "interpretation": "해석",
                "evidence_ids": ["invented-paper"],
                "limitation": "한계",
            }
            for metric in report["metrics"]
        ]

        with self.assertRaisesRegex(ValueError, "not retrieved"):
            generate_narrative(
                report,
                evidence,
                structured_model=FakeStructuredModel(findings),
            )

    def test_safe_mode_does_not_require_cloud_configuration(self) -> None:
        with patch.dict(os.environ, {"LLM_REPORT_ENABLED": "false"}, clear=True):
            result = generate_narrative_safe(_measurement_report(), [])

        self.assertEqual(result["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
