import json
import tempfile
import unittest
from pathlib import Path

from coach.scripts.model_contract.normalize_features import (
    derive_pose_series,
    normalize,
    write_normalized,
)


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
        self.assertEqual(result["feature1"]["reference_range"]["min"], 0.028)
        self.assertEqual(result["feature1"]["research_reference"]["mean"], 0.046)
        self.assertEqual(result["feature2"]["reference_range"]["min"], 70.0)
        self.assertEqual(result["feature2"]["score"], 100.0)
        self.assertEqual(result["feature2"]["denominator_policy"], "evaluated_frames")
        self.assertEqual(result["feature1"]["visualization"]["kind"], "range_bar")
        self.assertEqual(result["feature2"]["visualization"]["x_axis"], "measurable_frame")
        self.assertEqual(result["feature3"]["visualization"]["x_axis"], "video_frame")
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

    def test_preserves_model_elbow_frame_indices(self):
        raw = self._raw()
        raw["Elbow angle"]["range"]["frame_indices"] = [20, 21]

        result = normalize(raw, fps=10.0)

        self.assertEqual([point["frame_index"] for point in result["feature2"]["series"]], [20, 21])
        self.assertEqual([point["timestamp_ms"] for point in result["feature2"]["series"]], [2000, 2100])

    def test_rejects_missing_representative_value(self):
        raw = self._raw()
        del raw["Elbow angle"]["range"]["mean"]
        with self.assertRaisesRegex(ValueError, "range.mean"):
            normalize(raw)

    def test_all_frames_counts_invalid_frames_in_denominator(self):
        result = normalize(
            self._raw(), source_frame_count=4, denominator_policy="all_frames"
        )
        elbow = result["feature2"]
        self.assertEqual(elbow["good_frame_count"], 2)
        self.assertEqual(elbow["evaluated_frame_count"], 2)
        self.assertEqual(elbow["source_frame_count"], 4)
        self.assertEqual(elbow["score"], 50.0)
        self.assertEqual(elbow["evaluation_coverage_pct"], 50.0)

    def test_evaluated_frames_policy_is_switchable(self):
        result = normalize(
            self._raw(), source_frame_count=4,
            denominator_policy="evaluated_frames",
        )
        self.assertEqual(result["feature2"]["score"], 100.0)
        self.assertEqual(result["feature2"]["denominator_policy"], "evaluated_frames")

    def test_feature_boundaries_and_feature1_exclusion(self):
        raw = self._raw()
        raw["Elbow angle"]["value"] = [70, 90, 110, 110.1]
        pose = {
            "feature3": [{"value": value} for value in (10.9, 18.899, 18.9)],
            "feature4": [{"value": value} for value in (1.7, 4.299, 4.3)],
        }
        result = normalize(raw, source_frame_count=4, pose_series=pose)
        self.assertEqual(result["feature2"]["good_frame_count"], 3)
        self.assertEqual(result["feature3"]["good_frame_count"], 2)
        self.assertEqual(result["feature4"]["good_frame_count"], 2)
        self.assertIsNone(result["feature1"]["score"])

    def test_default_denominators_are_feature_specific(self):
        pose = {
            "feature3": [{"value": 12.0}, {"value": 20.0}],
            "feature4": [{"value": 3.0}, {"value": 6.0}],
        }

        result = normalize(self._raw(), source_frame_count=4, pose_series=pose)

        self.assertEqual(result["feature2"]["denominator_policy"], "evaluated_frames")
        self.assertEqual(result["feature2"]["score"], 100.0)
        self.assertEqual(result["feature3"]["denominator_policy"], "all_frames")
        self.assertEqual(result["feature3"]["score"], 25.0)
        self.assertEqual(result["feature4"]["denominator_policy"], "all_frames")
        self.assertEqual(result["feature4"]["score"], 25.0)

    def test_feature1_verdict_uses_observed_range_without_scoring(self):
        inside = normalize(self._raw())["feature1"]
        raw = self._raw()
        raw["Amplitude of pelvis oscillation"]["value"] = 0.07
        outside = normalize(raw)["feature1"]

        self.assertEqual(inside["verdict"], "maintain")
        self.assertEqual(outside["verdict"], "improve")
        self.assertIsNone(inside["score"])

    def test_feature1_without_ground_contact_is_unavailable_not_fatal(self):
        raw = self._raw()
        raw["Amplitude of pelvis oscillation"] = {
            "value": None,
            "range": {"section": "측정 불가"},
            "instruction": "접지 구간을 확인할 수 있는 측면 영상을 사용해 주세요.",
            "outcome": "접지 구간이 검출되지 않았습니다.",
        }

        result = normalize(raw, source_frame_count=10)

        self.assertIsNone(result["feature1"]["value"])
        self.assertIsNone(result["feature1"]["representative_value"])
        self.assertEqual(result["feature1"]["verdict"], "unavailable")
        self.assertIsNone(result["feature1"]["score"])

    def test_confidence_is_explicitly_assumed_without_percentage(self):
        item = normalize(self._raw())["feature2"]
        self.assertEqual(item["confidence_level"], "high")
        self.assertIsNone(item["confidence_pct"])
        self.assertTrue(item["confidence_assumed"])

    def test_pose_series_skips_frames_without_required_joints(self):
        keypoints = [[0.0, 0.0] for _ in range(26)]
        keypoints[5], keypoints[6] = [1.0, 1.0], [3.0, 1.0]
        keypoints[11], keypoints[12] = [1.0, 3.0], [3.0, 3.0]
        keypoints[18], keypoints[15] = [2.0, 1.0], [2.0, 5.0]
        valid = {
            "track_id": 0, "keypoints": keypoints,
            "observed": [True] * 26,
            "imputed_keypoints": [None] * 26,
        }
        invalid = {**valid, "observed": [False] * 26}
        series = derive_pose_series(
            {"frames": [
                {"frame_num": 4, "people": [valid]},
                {"frame_num": 5, "people": [invalid]},
                {"frame_num": 6, "people": []},
            ]},
            20.0,
        )
        self.assertEqual(len(series["feature3"]), 1)
        self.assertEqual(len(series["feature4"]), 1)
        self.assertEqual(series["feature3"][0]["frame_index"], 4)
        self.assertEqual(series["feature3"][0]["timestamp_ms"], 200)


if __name__ == "__main__":
    unittest.main()
