import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

from runpod_client import RunPodRemoteFailure, RunPodVideoAnalysisClient
from video_analysis_contract import build_request, validate_manifest


HASH = "a" * 64


def manifest_for(request):
    prefix = request["result_prefix"]
    return {
        "schema_version": "video-analysis-manifest-2.0",
        "status": "complete",
        **{key: request[key] for key in (
            "job_id", "attempt_id", "model_id", "model_release",
            "source_sha256", "model_sha256", "input",
        )},
        "input_sha256": HASH,
        "objects": {
            "predictions": {"object_name": f"{prefix}/pose_predictions.json", "sha256": HASH, "bytes": 1, "content_type": "application/json"},
            "details": {"object_name": f"{prefix}/details.json", "sha256": HASH, "bytes": 1, "content_type": "application/json"},
            "video": {"object_name": f"{prefix}/rendered.mp4", "sha256": HASH, "bytes": 1, "content_type": "video/mp4"},
        },
        "execution": {"device": "cuda", "provider": "CUDAExecutionProvider", "gpu_name": "test GPU"},
        "timings_seconds": {"download": 1, "analysis": 2, "encode": 3, "upload": 4, "worker_total": 10},
    }


class VideoAnalysisContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        coach = Path(self.temp.name)
        plugin = coach / "model_plugins" / "model"
        hpe = plugin / "scripts" / "hpe"
        hpe.mkdir(parents=True)
        for name in ("hpe.py", "utils.py"):
            (hpe / name).write_text(name, encoding="utf-8")
        (plugin / "model_manifest.json").write_text(json.dumps({
            "source_files": ["scripts/hpe/hpe.py", "scripts/hpe/utils.py"],
            "weights": [{"path": "model.onnx", "sha256": HASH}],
        }), encoding="utf-8")
        self.request = build_request({
            "job_id": "job-1", "model_id": "model", "model_release": "sha-image",
            "input_object_name": "uploads/input.mp4", "input_etag": "etag-1",
            "input_size_bytes": 10,
        }, "attempt-1", coach)

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_exact_request_and_manifest(self):
        expected = "jobs/job-1/video-analysis/attempt-1/pose_manifest.json"
        self.assertEqual(validate_manifest(manifest_for(self.request), self.request), expected)

    def test_normalizes_database_uuids_to_json_contract_strings(self):
        job_id = UUID("e903648a-6a3f-4bef-af64-40b330c24a35")
        attempt_id = UUID("11111111-2222-4333-8444-555555555555")
        request = build_request({
            "job_id": job_id, "model_id": "model", "model_release": "sha-image",
            "input_object_name": "uploads/input.mp4", "input_etag": "etag-1",
            "input_size_bytes": 10,
        }, attempt_id, Path(self.temp.name))

        self.assertEqual(request["job_id"], str(job_id))
        self.assertEqual(request["attempt_id"], str(attempt_id))
        json.dumps(request)

    def test_rejects_artifact_from_another_attempt(self):
        manifest = manifest_for(self.request)
        manifest["objects"]["video"]["object_name"] = "jobs/job-1/video-analysis/old/rendered.mp4"
        with self.assertRaisesRegex(ValueError, "path mismatch"):
            validate_manifest(manifest, self.request)

    def test_rejects_cpu_evidence(self):
        manifest = manifest_for(self.request)
        manifest["execution"]["device"] = "cpu"
        with self.assertRaisesRegex(ValueError, "GPU evidence"):
            validate_manifest(manifest, self.request)


class RunPodClientTests(unittest.TestCase):
    @staticmethod
    def _response(payload):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(payload).encode()
        return response

    def test_submit_accepts_async_job_and_remote_id(self):
        response = self._response({
            "status": "accepted", "job_id": "job", "attempt_id": "attempt",
            "remote_job_id": "remote-1",
        })
        response.status = 202
        opener = Mock(return_value=response)
        client = RunPodVideoAnalysisClient("https://pod.example", "x" * 24, opener=opener)
        result = client.submit({"job_id": "job", "attempt_id": "attempt"})
        self.assertEqual(result["remote_job_id"], "remote-1")
        self.assertEqual(opener.call_args.args[0].method, "POST")

    def test_submit_requires_http_202(self):
        response = self._response({
            "status": "accepted", "job_id": "job", "attempt_id": "attempt",
            "remote_job_id": "remote-1",
        })
        response.status = 200
        client = RunPodVideoAnalysisClient(
            "https://pod.example", "x" * 24, opener=Mock(return_value=response)
        )
        with self.assertRaisesRegex(RuntimeError, "expected 202"):
            client.submit({"job_id": "job", "attempt_id": "attempt"})

    def test_poll_accepts_running_and_complete_states(self):
        complete = {
            "status": "complete", "job_id": "job", "attempt_id": "attempt",
            "manifest_object": "jobs/job/video-analysis/attempt/pose_manifest.json",
        }
        opener = Mock(side_effect=[
            self._response({"status": "running", "job_id": "job", "attempt_id": "attempt"}),
            self._response(complete),
        ])
        client = RunPodVideoAnalysisClient("https://pod.example", "x" * 24, opener=opener)
        self.assertEqual(client.poll("remote-1", job_id="job", attempt_id="attempt")["status"], "running")
        self.assertEqual(client.poll("remote-1", job_id="job", attempt_id="attempt"), complete)
        self.assertTrue(opener.call_args.args[0].full_url.endswith("/remote-1"))

    def test_poll_preserves_explicit_remote_failure(self):
        opener = Mock(return_value=self._response({
            "status": "failed", "job_id": "job", "attempt_id": "attempt",
            "error_code": "CUDA_OOM", "error_message": "out of memory",
        }))
        client = RunPodVideoAnalysisClient("https://pod.example", "x" * 24, opener=opener)
        with self.assertRaisesRegex(RunPodRemoteFailure, "CUDA_OOM") as raised:
            client.poll("remote-1", job_id="job", attempt_id="attempt")
        self.assertEqual(raised.exception.error_code, "CUDA_OOM")

    def test_rejects_non_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            RunPodVideoAnalysisClient("http://pod.example", "x" * 24)

    def test_accepts_full_endpoint_without_duplicating_path(self):
        endpoint = "https://pod.example/v4/storage-video-analysis"
        client = RunPodVideoAnalysisClient(endpoint, "x" * 24)
        self.assertEqual(client.endpoint, endpoint)

    def test_checks_response_identity(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({
            "status": "complete", "job_id": "other", "attempt_id": "attempt",
            "manifest_object": "bad",
        }).encode()
        opener = Mock(return_value=response)
        client = RunPodVideoAnalysisClient("https://pod.example", "x" * 24, opener=opener)
        payload = {"job_id": "job", "attempt_id": "attempt", "result_prefix": "jobs/job/video-analysis/attempt"}
        with self.assertRaisesRegex(RuntimeError, "job_id"):
            client.submit(payload)
        sent_request = opener.call_args.args[0]
        self.assertEqual(
            sent_request.get_header("User-agent"),
            "Runners-Feed-OCI-Dispatcher/1.0",
        )


if __name__ == "__main__":
    unittest.main()
