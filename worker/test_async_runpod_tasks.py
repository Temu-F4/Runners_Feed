import unittest
from unittest.mock import Mock, patch

from coach_tasks import dispatch_video_analysis, poll_video_analysis


SNAPSHOT = {
    "job_id": "job-1", "case_id": "case-1", "input_object_name": "uploads/a.mp4",
    "input_size_bytes": 10, "input_etag": "etag", "height_snapshot_m": 1.75,
    "model_id": "model", "model_release": "release",
}


class AsyncRunPodTaskTests(unittest.TestCase):
    @patch("coach_tasks.fail_gpu_attempt_and_job")
    @patch("coach_tasks.JobStageRecorder")
    @patch("coach_tasks.client_from_environment")
    @patch("coach_tasks.ObjectStorageGateway")
    @patch("coach_tasks.build_request", return_value={"job_id": "job-1", "result_prefix": "jobs/job-1"})
    @patch("coach_tasks.mark_job_processing", return_value=True)
    @patch("coach_tasks.start_gpu_attempt")
    @patch("coach_tasks.create_gpu_attempt")
    def test_exhausted_submit_retries_fail_attempt_and_job(
        self, create_attempt, start_attempt, _mark_processing, _build, storage_class,
        client_factory, _recorder, fail_attempt,
    ):
        create_attempt.return_value = {
            "status": "QUEUED", "attempt_id": "attempt-1",
            "attempt_number": 1, "remote_job_id": None, "manifest_object": None,
        }
        start_attempt.return_value = SNAPSHOT
        storage_class.return_value.create_video_analysis_transfer.return_value = {}
        client_factory.return_value.submit.side_effect = __import__("runpod_client").RunPodTransientError("offline")
        dispatch_video_analysis.push_request(retries=20)
        try:
            with self.assertRaisesRegex(Exception, "offline"):
                dispatch_video_analysis.run("job-1")
        finally:
            dispatch_video_analysis.pop_request()
        fail_attempt.assert_called_once()

    @patch("coach_tasks._poll_interval", return_value=10)
    @patch("coach_tasks.celery_app.send_task")
    @patch("coach_tasks.get_gpu_attempt")
    @patch("coach_tasks.create_gpu_attempt")
    def test_remote_id_redelivery_does_not_submit_again(
        self, create_attempt, get_attempt, send_task, _interval
    ):
        create_attempt.return_value = {
            "status": "RUNNING", "attempt_id": "attempt-1",
            "attempt_number": 1, "remote_job_id": "remote-1",
            "manifest_object": None,
        }
        result = dispatch_video_analysis.run("job-1")
        self.assertEqual(result["status"], "poll_requeued")
        get_attempt.assert_not_called()
        send_task.assert_called_once()

    @patch("coach_tasks._poll_interval", return_value=10)
    @patch("coach_tasks.celery_app.send_task")
    @patch("coach_tasks.client_from_environment")
    @patch("coach_tasks.get_gpu_attempt")
    def test_running_poll_schedules_next_poll(
        self, get_attempt, client_factory, send_task, _interval
    ):
        get_attempt.return_value = {
            **SNAPSHOT, "status": "RUNNING", "remote_job_id": "remote-1",
            "manifest_object": None, "elapsed_seconds": 20,
        }
        client_factory.return_value.poll.return_value = {
            "status": "running", "job_id": "job-1", "attempt_id": "attempt-1"
        }
        result = poll_video_analysis.run("job-1", "attempt-1")
        self.assertEqual(result["status"], "running")
        send_task.assert_called_once_with(
            "coach.poll_video_analysis", args=["job-1", "attempt-1"],
            queue="gpu_dispatch", countdown=10,
        )

    @patch("coach_tasks.JobStageRecorder")
    @patch("coach_tasks.validate_manifest")
    @patch("coach_tasks.build_request", return_value={"job_id": "job-1"})
    @patch("coach_tasks.ObjectStorageGateway")
    @patch("coach_tasks.accept_gpu_result", return_value=True)
    @patch("coach_tasks.client_from_environment")
    @patch("coach_tasks.get_gpu_attempt")
    @patch("coach_tasks.celery_app.send_task")
    def test_complete_manifest_queues_postprocess_once(
        self, send_task, get_attempt, client_factory, accept_result,
        storage_class, build_request, validate_manifest, recorder_class,
    ):
        get_attempt.return_value = {
            **SNAPSHOT, "status": "RUNNING", "remote_job_id": "remote-1",
            "manifest_object": None, "elapsed_seconds": 20,
        }
        manifest_object = "jobs/job-1/video-analysis/attempt-1/pose_manifest.json"
        client_factory.return_value.poll.return_value = {
            "status": "complete", "job_id": "job-1", "attempt_id": "attempt-1",
            "manifest_object": manifest_object,
        }
        storage_class.return_value.load_result_json.return_value = {
            "timings_seconds": {"download": 1, "analysis": 2, "encode": 3}
        }
        result = poll_video_analysis.run("job-1", "attempt-1")
        self.assertEqual(result["status"], "postprocess_queued")
        accept_result.assert_called_once()
        send_task.assert_called_once_with(
            "coach.run_postprocess",
            args=["job-1", "attempt-1", manifest_object], queue="postprocess",
        )

        accept_result.return_value = False
        send_task.reset_mock()
        self.assertEqual(
            poll_video_analysis.run("job-1", "attempt-1")["status"],
            "already_complete",
        )
        send_task.assert_not_called()

    @patch("coach_tasks.fail_gpu_attempt_and_job")
    @patch("coach_tasks.JobStageRecorder")
    @patch("coach_tasks._max_poll_seconds", return_value=10)
    @patch("coach_tasks.get_gpu_attempt")
    def test_poll_timeout_fails_attempt_and_job(
        self, get_attempt, _max_poll, _recorder, fail_attempt
    ):
        get_attempt.return_value = {
            **SNAPSHOT, "status": "RUNNING", "remote_job_id": "remote-1",
            "manifest_object": None, "elapsed_seconds": 11,
        }
        with self.assertRaisesRegex(RuntimeError, "exceeded"):
            poll_video_analysis.run("job-1", "attempt-1")
        fail_attempt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
