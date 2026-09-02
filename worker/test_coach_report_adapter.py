import json
import tempfile
import unittest
from pathlib import Path

from coach_adapter.report_adapter import build_report, write_report


class CoachReportAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.run_dir = Path(temporary_directory.name)
        self.output_dir = self.run_dir / "outputs"
        self.output_dir.mkdir()
        (self.output_dir / "details.json").write_text(
            json.dumps(
                {
                    "video": {
                        "duration_seconds": 1.0,
                        "fps": 30.0,
                        "frame_count": 2,
                        "width": 640,
                        "height": 480,
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.output_dir / "pose_predictions.json").write_text(
            json.dumps(
                {
                    "frames": [
                        {
                            "people": [
                                {
                                    "track_id": 0,
                                    "keypoint_scores": [0.9, 0.8],
                                    "observed": [True, False],
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.output_dir / "feature_results.json").write_text(
            json.dumps(
                {
                    "feature1": {
                        "value": 0.046,
                        "unit": "ratio",
                        "measurement_source": "2d_pose",
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_preserves_coach_feature_value(self) -> None:
        report = build_report(self.run_dir)

        self.assertEqual(report["source"], "coach")
        self.assertEqual(report["features"]["feature1"]["value"], 0.046)
        self.assertEqual(report["metrics"][0]["value"], 0.046)
        self.assertEqual(report["tracking"]["coverage_pct"], 50.0)
        self.assertEqual(report["tracking"]["observed_keypoints_pct"], 50.0)
        self.assertEqual(report["narrative"]["status"], "disabled")

    def test_includes_optional_coach_markdown_without_interpreting_it(self) -> None:
        coaching = "수직진동 — 논문 표본과 유사: 현재 리듬을 유지하세요."
        (self.output_dir / "running_report.md").write_text(
            coaching,
            encoding="utf-8",
        )

        report = build_report(self.run_dir)

        self.assertEqual(report["narrative"]["status"], "success")
        self.assertEqual(report["narrative"]["overall_summary"], coaching)

    def test_writes_api_compatible_report_json(self) -> None:
        output_path = write_report(self.run_dir)

        self.assertEqual(output_path, self.output_dir / "report.json")
        persisted = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["schema_version"], "coach-1.0")


if __name__ == "__main__":
    unittest.main()
