import json
import tempfile
from pathlib import Path
from unittest import TestCase

from coach.scripts.model_contract.quality_gate import evaluate_run


class ModelQualityGateTests(TestCase):
    def test_checked_in_golden_fixture_passes(self) -> None:
        root = Path(__file__).parents[1]
        result = evaluate_run(
            root / "coach" / "tests" / "fixtures" / "model-golden",
            root / "coach" / "scripts" / "model_contract" / "quality_baseline.example.json",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["feature_ids"], ["feature1"])

    def test_rejects_feature_unit_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            output_dir = run_dir / "outputs"
            output_dir.mkdir()
            (output_dir / "details.json").write_text(
                json.dumps({"video": {"width": 1, "height": 1, "fps": 1, "frame_count": 1}}),
                encoding="utf-8",
            )
            (output_dir / "pose_predictions.json").write_text(
                json.dumps({"frames": [{"people": [{"track_id": 0}]}]}),
                encoding="utf-8",
            )
            (output_dir / "feature_results.json").write_text(
                json.dumps({"feature1": {"value": 0.1, "unit": "degrees"}}),
                encoding="utf-8",
            )
            baseline = run_dir / "baseline.json"
            baseline.write_text(
                json.dumps({"required_feature_ids": ["feature1"], "min_tracking_coverage": 0, "feature_bounds": {"feature1": {"min": 0, "max": 1, "unit": "ratio"}}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unit changed"):
                evaluate_run(run_dir, baseline)
