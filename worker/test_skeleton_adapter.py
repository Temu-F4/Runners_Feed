import gzip
import json
import tempfile
import unittest
from pathlib import Path

from coach_adapter.skeleton_adapter import build_skeleton, write_skeleton


class SkeletonAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.run_dir = Path(temporary_directory.name)
        output_dir = self.run_dir / "outputs"
        output_dir.mkdir()
        (output_dir / "details.json").write_text(
            json.dumps(
                {
                    "video": {
                        "duration_seconds": 1.0,
                        "fps": 30.0,
                        "width": 200,
                        "height": 100,
                    }
                }
            ),
            encoding="utf-8",
        )
        frames = []
        for number in (1, 2, 4):
            frames.append(
                {
                    "image_path": f"run/id/inputs/{number:08d}.png",
                    "people": [
                        {
                            "track_id": 0,
                            "keypoints": [[100, 25], [220, -10]],
                            "keypoint_scores": [0.9, 1.2],
                        }
                    ],
                }
            )
        (output_dir / "pose_predictions.json").write_text(
            json.dumps({"frames": frames}),
            encoding="utf-8",
        )

    def test_normalizes_clamps_and_downsamples_keypoints(self) -> None:
        skeleton = build_skeleton(self.run_dir)

        self.assertEqual(skeleton["schema_version"], "skeleton-1.0")
        self.assertEqual(skeleton["fps"], 10.0)
        self.assertEqual(len(skeleton["frames"]), 2)
        self.assertEqual(
            skeleton["frames"][0]["keypoints"],
            [[0.5, 0.25, 0.9], [1.0, 0.0, 1.0]],
        )

    def test_writes_valid_gzip_json(self) -> None:
        output_path = write_skeleton(self.run_dir)

        with gzip.open(output_path, "rt", encoding="utf-8") as source:
            persisted = json.load(source)
        self.assertEqual(persisted["pose_model"], "halpe26")
        self.assertNotIn("image_path", source := persisted["frames"][0])
        self.assertNotIn("people", source)


if __name__ == "__main__":
    unittest.main()
