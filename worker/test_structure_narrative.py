import json
import tempfile
import unittest
from pathlib import Path

from coach.scripts.model_contract.structure_narrative import build_structured_narrative


class StructuredNarrativeTests(unittest.TestCase):
    def test_wraps_llm_summary_and_deterministic_feature_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            output_dir = run_dir / "outputs"
            output_dir.mkdir()
            summary = "팔 동작은 안정적입니다. 몸통 자세는 조정이 필요합니다. 다음 러닝에서 자연스럽게 연습해 보세요."
            (output_dir / "running_report.md").write_text(summary, encoding="utf-8")
            (output_dir / "feature_results.service.json").write_text(
                json.dumps({
                    "feature2": {
                        "verdict": "maintain",
                        "coaching_action": "팔 동작을 유지하세요.",
                        "representative_value": 90,
                        "unit": "degree",
                        "reference_range": {"min": 70, "max": 110},
                    },
                    "feature3": {
                        "verdict": "improve",
                        "coaching_action": "몸통을 조금 기울이세요.",
                        "representative_value": 8,
                        "unit": "degree",
                        "reference_range": {"min": 10.9, "max": 18.9},
                    },
                }),
                encoding="utf-8",
            )

            result = build_structured_narrative(run_dir)

            self.assertEqual(result["overall_summary"], summary)
            self.assertEqual(result["priority_actions"][0]["feature_id"], "feature3")
            self.assertEqual(result["maintain_actions"][0]["feature_id"], "feature2")
            self.assertEqual(result["validator_version"], "service-narrative-2")

    def test_rejects_numbers_markup_and_medical_claims(self) -> None:
        for summary in (
            "점수는 90점입니다. 자세가 좋습니다. 유지하세요.",
            "```코드```입니다. 자세가 좋습니다. 유지하세요.",
            "부상이 발생합니다. 자세를 바꾸세요. 조심하세요.",
        ):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory) / "outputs"
                output_dir.mkdir()
                (output_dir / "running_report.md").write_text(summary, encoding="utf-8")
                (output_dir / "feature_results.service.json").write_text("{}", encoding="utf-8")
                with self.assertRaises(ValueError):
                    build_structured_narrative(Path(directory))


if __name__ == "__main__":
    unittest.main()
