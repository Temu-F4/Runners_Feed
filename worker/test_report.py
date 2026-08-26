import unittest

from inference.report import generate_report


def _person(offset: float) -> dict:
    points = [[100.0 + offset, 100.0 + index * 8.0] for index in range(26)]
    points[5] = [90.0 + offset, 160.0]
    points[6] = [110.0 + offset, 160.0]
    points[7] = [80.0 + offset, 190.0]
    points[8] = [120.0 + offset, 190.0]
    points[9] = [88.0 + offset, 220.0]
    points[10] = [112.0 + offset, 220.0]
    points[11] = [92.0, 240.0]
    points[12] = [108.0, 240.0]
    points[18] = [104.0 + offset, 150.0]
    points[19] = [100.0, 240.0]
    points[13] = [88.0 + offset, 290.0]
    points[14] = [112.0 - offset, 290.0]
    points[15] = [95.0 - offset, 340.0]
    points[16] = [105.0 + offset, 340.0]
    points[20] = [86.0 - offset, 345.0]
    points[21] = [114.0 + offset, 345.0]
    points[22] = [90.0 - offset, 344.0]
    points[23] = [110.0 + offset, 344.0]
    points[24] = [98.0 - offset, 342.0]
    points[25] = [102.0 + offset, 342.0]
    return {
        "track_id": 0,
        "keypoints": points,
        "keypoint_scores": [0.9] * 26,
        "observed": [True] * 26,
        "imputed_keypoints": [None] * 26,
    }


class GenerateReportTest(unittest.TestCase):
    def test_generates_finite_metrics(self) -> None:
        details = {
            "video": {
                "duration_seconds": 1.0,
                "fps": 30.0,
                "frame_count": 3,
                "width": 1920,
                "height": 1080,
            }
        }
        predictions = {
            "frames": [
                {"people": [_person(-4.0)]},
                {"people": [_person(0.0)]},
                {"people": [_person(4.0)]},
            ]
        }

        report = generate_report(details, predictions)

        self.assertEqual(report["schema_version"], "2.0")
        self.assertEqual(report["tracking"]["coverage_pct"], 100.0)
        self.assertEqual(report["tracking"]["observed_keypoints_pct"], 100.0)
        self.assertEqual(report["tracking"]["stance_candidate_frames"], 3)
        self.assertEqual(len(report["metrics"]), 4)
        self.assertEqual(
            [metric["id"] for metric in report["metrics"]],
            [
                "postural_lean_angle_deg",
                "torso_flexion_angle_deg",
                "peak_hip_flexion_stance_deg",
                "peak_knee_flexion_stance_deg",
            ],
        )
        self.assertTrue(
            all(metric["value"] is not None for metric in report["metrics"])
        )
        self.assertTrue(
            all(metric["evidence_query"] for metric in report["metrics"])
        )

    def test_rejects_predictions_without_primary_runner(self) -> None:
        with self.assertRaisesRegex(ValueError, "primary runner"):
            generate_report({}, {"frames": [{"people": []}]})


if __name__ == "__main__":
    unittest.main()
