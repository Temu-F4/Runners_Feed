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
            summary = "팔 동작은 유지하고 몸통 자세는 천천히 조정하세요."
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
            (output_dir / "feature_results.json").write_text(
                json.dumps({
                    "Elbow angle": {
                        "value": [80, 90],
                        "range": {"section": "70°-90° 진동 구간"},
                        "instruction": "좋아요. 현재 동작을 유지하세요.",
                    },
                    "Trunk flexion angle": {
                        "value": 8,
                        "instruction": "몸통을 조금 기울이세요.",
                    },
                }),
                encoding="utf-8",
            )

            result = build_structured_narrative(run_dir)

            self.assertEqual(result["overall_summary"], summary)
            self.assertEqual(result["priority_actions"][0]["feature_id"], "feature3")
            self.assertEqual(result["maintain_actions"][0]["feature_id"], "feature2")
            self.assertEqual(result["validator_version"], "service-narrative-3")
            self.assertTrue(result["exercise_videos"])

    def test_rejects_numbers_markup_and_medical_claims(self) -> None:
        for summary in (
            "점수는 90점이므로 자세를 유지하세요.",
            "```코드``` 자세를 유지하세요.",
            "부상이 발생하므로 자세를 바꾸세요.",
            "팔 동작은 안정적입니다. 몸통을 조정하세요.",
            "- 팔 동작을 유지하세요.",
            "**팔 동작**을 유지하세요.",
            "<b>팔 동작</b>을 유지하세요.",
            "자세 점수를 유지하세요.",
            "각도를 유지하세요.",
            "팔 동작을 유지하세요",
        ):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory) / "outputs"
                output_dir.mkdir()
                (output_dir / "running_report.md").write_text(summary, encoding="utf-8")
                (output_dir / "feature_results.service.json").write_text("{}", encoding="utf-8")
                (output_dir / "feature_results.json").write_text("{}", encoding="utf-8")
                with self.assertRaises(ValueError):
                    build_structured_narrative(Path(directory))

    def test_ignores_malformed_or_null_range_without_crashing(self) -> None:
        from coach.scripts.model_contract.exercise_video_tool import recommend_exercise_videos

        for value in (None, "invalid"):
            with self.subTest(value=value):
                videos = recommend_exercise_videos({
                    "Elbow angle": {"value": [90], "range": value, "instruction": "유지하세요."},
                })
                self.assertIsInstance(videos, list)
                if value == "invalid":
                    self.assertEqual(videos, [])


if __name__ == "__main__":
    unittest.main()
