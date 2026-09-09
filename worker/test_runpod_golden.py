import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from coach.scripts.model_contract.validate_runpod_golden import validate


class RunPodGoldenValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        self.plugin_dir = root / "plugin"
        self.output_dir = root / "run" / "outputs"
        self.plugin_dir.mkdir()
        self.output_dir.mkdir(parents=True)
        (self.plugin_dir / "hpe.py").write_text("pass\n", encoding="utf-8")
        self.source_hash = hashlib.sha256(b"pass\n").hexdigest()
        self.weight_hash = "a" * 64
        (self.plugin_dir / "model_manifest.json").write_text(json.dumps({
            "model_id": "model-1",
            "source_files": ["hpe.py"],
            "weights": [{"path": "pose.onnx", "sha256": self.weight_hash}],
        }), encoding="utf-8")
        for filename, contents in (
            ("pose_predictions.json", b"{}"),
            ("details.json", b"{}"),
            ("rendered.mp4", b"video"),
        ):
            (self.output_dir / filename).write_bytes(contents)
        self._write_evidence()

    def _write_evidence(self, *, provider: str = "CUDAExecutionProvider") -> None:
        prefix = "jobs/job-1/video-analysis/attempt-1"
        objects = {}
        for role, filename, content_type in (
            ("predictions", "pose_predictions.json", "application/json"),
            ("details", "details.json", "application/json"),
            ("video", "rendered.mp4", "video/mp4"),
        ):
            path = self.output_dir / filename
            objects[role] = {
                "object_name": f"{prefix}/{filename}",
                "content_type": content_type,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        (self.output_dir / "pose_manifest.json").write_text(json.dumps({
            "schema_version": "video-analysis-manifest-2.0",
            "status": "complete",
            "job_id": "job-1",
            "attempt_id": "attempt-1",
            "model_id": "model-1",
            "source_sha256": {"hpe.py": self.source_hash},
            "model_sha256": {"pose.onnx": self.weight_hash},
            "execution": {
                "device": "cuda",
                "provider": provider,
                "gpu_name": "Test GPU",
            },
            "objects": objects,
            "timings_seconds": {
                "download": 1,
                "analysis": 2,
                "encode": 1,
                "upload": 1,
                "worker_total": 5,
            },
        }), encoding="utf-8")

    def test_accepts_matching_cuda_evidence_and_artifacts(self) -> None:
        result = validate(self.plugin_dir, self.output_dir.parent)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["gpu_name"], "Test GPU")

    def test_rejects_non_cuda_provider(self) -> None:
        self._write_evidence(provider="CPUExecutionProvider")

        with self.assertRaisesRegex(ValueError, "wrong provider"):
            validate(self.plugin_dir, self.output_dir.parent)

    def test_rejects_modified_artifact(self) -> None:
        (self.output_dir / "rendered.mp4").write_bytes(b"modified")

        with self.assertRaisesRegex(ValueError, "size mismatch"):
            validate(self.plugin_dir, self.output_dir.parent)


if __name__ == "__main__":
    unittest.main()
