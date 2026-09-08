import json
import tempfile
import unittest
from pathlib import Path

from coach.scripts.model_contract.normalize_features import normalize, write_normalized


class FeatureNormalizerTests(unittest.TestCase):
    def _raw(self):
        return {
            "Amplitude of pelvis oscillation": {
                "value": 0.046,
                "range": {"section": "일반"},
                "instruction": "리듬을 유지하세요.",
                "outcome": "평균 범위입니다.",
            },
            "Elbow angle": {
                "value": [70.0, 90.0],
                "range": {"mean": 80.0, "min": 70.0, "max": 90.0},
                "instruction": "자연스럽게 움직이세요.",
                "outcome": "경제적인 구간입니다.",
            },
            "Trunk flexion angle": {
                "value": 7.2,
                "boundary": [5.0, 10.0],
                "instruction": "현재 각도를 확인하세요.",
                "outcome": "측정 결과입니다.",
            },
            "Postural lean angle": {
                "value": 4.1,
                "boundary": [2.0, 8.2],
                "instruction": "현재 자세를 유지하세요.",
                "outcome": "측정 결과입니다.",
            },
        }

    def test_maps_raw_names_and_representative_values(self):
        result = normalize(self._raw(), fps=20.0)

        self.assertEqual(list(result), ["feature1", "feature2", "feature3", "feature4"])
        self.assertEqual(result["feature1"]["value"], 0.046)
        self.assertEqual(result["feature2"]["value"], 80.0)
        self.assertEqual(result["feature2"]["unit"], "degree")
        self.assertEqual(result["feature1"]["coaching_action"], "리듬을 유지하세요.")
        self.assertEqual(result["feature1"]["source_range"], {"section": "일반"})
        self.assertNotIn("reference_range", result["feature1"])
        self.assertEqual(result["feature2"]["reference_range"]["min"], 70.0)
        self.assertEqual(result["feature2"]["score"], 100.0)
        self.assertEqual(result["feature2"]["series"][1], {
            "frame_index": 1,
            "timestamp_ms": 50,
            "value": 90.0,
            "confidence_pct": None,
        })

    def test_writes_separate_service_artifact_without_mutating_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "outputs"
            output_dir.mkdir()
            raw_path = output_dir / "feature_results.json"
            original = json.dumps(self._raw(), ensure_ascii=False)
            raw_path.write_text(original, encoding="utf-8")
            (output_dir / "details.json").write_text(
                json.dumps({"video": {"fps": 25.0}}),
                encoding="utf-8",
            )

            service_path = write_normalized(Path(directory))

            self.assertEqual(raw_path.read_text(encoding="utf-8"), original)
            self.assertTrue(service_path.name.endswith(".service.json"))
            service = json.loads(service_path.read_text(encoding="utf-8"))
            self.assertEqual(service["feature2"]["series"][1]["timestamp_ms"], 40)

    def test_filters_nonfinite_series_samples(self):
        raw = self._raw()
        raw["Elbow angle"]["value"] = [70.0, float("nan"), 90.0]

        result = normalize(raw, fps=10.0)

        self.assertEqual(
            [point["frame_index"] for point in result["feature2"]["series"]],
            [0, 2],
        )

    def test_rejects_missing_representative_value(self):
        raw = self._raw()
        del raw["Elbow angle"]["range"]["mean"]
        with self.assertRaisesRegex(ValueError, "range.mean"):
            normalize(raw)


if __name__ == "__main__":
    unittest.main()
