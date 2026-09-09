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
        (self.output_dir / "feature_results.service.json").write_text(
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
        self.assertIsNone(report["run_metrics"])

    def test_passes_through_run_metrics_without_estimating_them(self) -> None:
        details = json.loads((self.output_dir / "details.json").read_text(encoding="utf-8"))
        details["run_metrics"] = {"pace_per_km": "4:25", "cadence_spm": 181}
        (self.output_dir / "details.json").write_text(json.dumps(details), encoding="utf-8")

        report = build_report(self.run_dir)

        self.assertEqual(report["run_metrics"]["pace_per_km"], "4:25")
        self.assertEqual(report["run_metrics"]["cadence_spm"], 181)

    def test_adapts_model_cadence_and_decimal_pace(self) -> None:
        (self.output_dir / "feature_results.json").write_text(
            json.dumps({
                "cadence": 180.4,
                "pace": 4.4167,
            }),
            encoding="utf-8",
        )

        report = build_report(self.run_dir)

        self.assertEqual(report["run_metrics"]["cadence_spm"], 180.4)
        self.assertEqual(report["run_metrics"]["pace_per_km"], "4:25 /km")

    def test_does_not_publish_unvalidated_coach_markdown(self) -> None:
        coaching = "수직진동 — 논문 표본과 유사: 현재 리듬을 유지하세요."
        (self.output_dir / "running_report.md").write_text(
            coaching,
            encoding="utf-8",
        )

        report = build_report(self.run_dir)

        self.assertEqual(report["narrative"]["status"], "disabled")

    def test_reads_structured_narrative_without_requiring_model_source_changes(self) -> None:
        (self.output_dir / "running_report.json").write_text(
            json.dumps(
                {
                    "status": "success",
                    "model": "coach-model",
                    "summary": "측정 결과 요약",
                    "priority_actions": [
                        {"feature_id": "feature1", "text": "현재 값을 확인해 보세요."}
                    ],
                    "maintain_actions": [],
                    "validator_version": "validator-1",
                }
            ),
            encoding="utf-8",
        )

        report = build_report(self.run_dir)

        self.assertEqual(report["narrative"]["status"], "success")
        self.assertEqual(report["narrative"]["overall_summary"], "측정 결과 요약")
        self.assertEqual(report["narrative"]["priority_actions"][0]["feature_id"], "feature1")

    def test_writes_api_compatible_report_json(self) -> None:
        output_path = write_report(self.run_dir)

        self.assertEqual(output_path, self.output_dir / "report.json")
        persisted = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["schema_version"], "coach-1.0")

    def test_posture_score_averages_only_features_two_through_four(self) -> None:
        features = {
            "feature1": {"value": 0.046, "unit": "ratio", "score": 100},
            "feature2": {"value": 80, "unit": "degree", "score": 30},
            "feature3": {"value": 12, "unit": "degree", "score": 60},
            "feature4": {"value": 3, "unit": "degree", "score": 90},
        }
        (self.output_dir / "feature_results.service.json").write_text(
            json.dumps(features), encoding="utf-8"
        )
        self.assertEqual(build_report(self.run_dir)["posture_score"], 60.0)

    def test_posture_score_is_missing_when_any_required_feature_is_unavailable(self) -> None:
        features = {
            "feature2": {"value": 80, "unit": "degree", "score": 30},
            "feature3": {"value": 12, "unit": "degree", "score": 60},
        }
        (self.output_dir / "feature_results.service.json").write_text(
            json.dumps(features), encoding="utf-8"
        )
        self.assertIsNone(build_report(self.run_dir)["posture_score"])

    def test_converts_non_finite_feature_value_to_null(self) -> None:
        (self.output_dir / "feature_results.service.json").write_text(
            '{"feature1":{"value":NaN,"unit":"ratio"}}',
            encoding="utf-8",
        )

        output_path = write_report(self.run_dir)

        persisted = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertIsNone(persisted["features"]["feature1"]["value"])
        self.assertIsNone(persisted["metrics"][0]["value"])


if __name__ == "__main__":
    unittest.main()
