import json
import tempfile
from pathlib import Path
from unittest import TestCase

from coach.scripts.model_contract.validate_artifacts import validate_run


class ModelContractTests(TestCase):
    def _write_valid_run(self, run_dir: Path) -> None:
        output_dir = run_dir / "outputs"
        output_dir.mkdir(parents=True)
        (output_dir / "details.json").write_text(
            json.dumps(
                {
                    "video": {
                        "width": 1280,
                        "height": 720,
                        "fps": 30,
                        "frame_count": 2,
                    }
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "pose_predictions.json").write_text(
            json.dumps({"frames": [{"people": []}, {"people": []}]}),
            encoding="utf-8",
        )
        (output_dir / "feature_results.json").write_text(
            json.dumps({"feature1": {"value": 0.1, "unit": "ratio"}}),
            encoding="utf-8",
        )

    def test_validates_required_model_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self._write_valid_run(run_dir)
            result = validate_run(run_dir)

        self.assertEqual(result["contract_version"], "coach-model-1.0")
        self.assertEqual(result["feature_ids"], ["feature1"])
        self.assertEqual(result["frame_count"], 2)

    def test_rejects_non_finite_feature_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self._write_valid_run(run_dir)
            feature_path = run_dir / "outputs" / "feature_results.json"
            feature_path.write_text(
                '{"feature1":{"value":NaN,"unit":"ratio"}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "non-finite"):
                validate_run(run_dir)
