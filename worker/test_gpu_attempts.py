import os
import sys
import unittest
from unittest.mock import Mock, patch

try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["psycopg"] = Mock()

from job_repository import (
    claim_postprocess_attempt,
    complete_postprocess,
    create_gpu_attempt,
    finish_gpu_attempt,
    fail_gpu_attempt_and_job,
    mark_job_failed,
    mark_job_success,
    save_remote_job_id,
    accept_gpu_result,
    start_gpu_attempt,
)


class GPUAttemptTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "postgresql://test"

    @patch("job_repository.uuid4", return_value="attempt-uuid")
    @patch("job_repository.psycopg.connect")
    def test_create_attempt_locks_job_and_increments_number(self, connect, uuid4):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("QUEUED",), None, (2,)]
        result = create_gpu_attempt("job")
        self.assertEqual(result, {
            "attempt_id": "attempt-uuid",
            "attempt_number": 2,
            "status": "QUEUED",
        })
        self.assertIn("FOR UPDATE", cursor.execute.call_args_list[0].args[0])

    @patch("job_repository.psycopg.connect")
    def test_reuses_stale_running_attempt_as_queued(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            ("PROCESSING",),
            ("attempt", 1, "RUNNING", None, None, True),
        ]
        result = create_gpu_attempt("job", stale_after_seconds=60)
        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(result["attempt_id"], "attempt")
        self.assertIn("StaleAttemptRecovered", cursor.execute.call_args_list[2].args[0])

    @patch("job_repository.psycopg.connect")
    def test_does_not_duplicate_live_running_attempt(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            ("PROCESSING",),
            ("attempt", 1, "RUNNING", None, None, False),
        ]
        result = create_gpu_attempt("job")
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual(cursor.execute.call_count, 2)

    @patch("job_repository.psycopg.connect")
    def test_stale_submitted_attempt_keeps_remote_job(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            ("PROCESSING",),
            ("attempt", 1, "RUNNING", None, "remote-1", True),
        ]
        result = create_gpu_attempt("job", stale_after_seconds=60)
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual(result["remote_job_id"], "remote-1")
        self.assertEqual(cursor.execute.call_count, 2)

    @patch("job_repository.psycopg.connect")
    def test_saves_remote_id_only_on_running_attempt(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        self.assertTrue(save_remote_job_id("job", "attempt", "remote-1"))
        query = cursor.execute.call_args.args[0]
        self.assertIn("status = 'RUNNING'", query)
        self.assertIn("remote_job_id IS NULL OR remote_job_id = %s", query)

    @patch("job_repository.psycopg.connect")
    def test_accepts_completed_poll_only_once(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        self.assertTrue(accept_gpu_result("job", "attempt", "manifest"))
        self.assertIn("remote_job_id IS NOT NULL", cursor.execute.call_args.args[0])

    @patch("job_repository.psycopg.connect")
    def test_start_returns_persisted_snapshot(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        cursor.fetchone.return_value = (
            "job", "case", "uploads/input.mp4", 123, "etag", 1.75, "model", "release"
        )
        self.assertEqual(start_gpu_attempt("job", "attempt")["input_etag"], "etag")
        self.assertIn("status = 'QUEUED'", cursor.execute.call_args_list[0].args[0])

    @patch("job_repository.psycopg.connect")
    def test_finish_is_conditional_on_running_attempt(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0
        cursor.fetchone.return_value = None
        self.assertFalse(finish_gpu_attempt("job", "old", "manifest"))
        self.assertIn("status = 'RUNNING'", cursor.execute.call_args_list[0].args[0])

    @patch("job_repository.psycopg.connect")
    def test_reuses_completed_gpu_attempt_for_postprocess(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            ("PROCESSING",),
            ("attempt", 2, "GPU_SUCCESS", "manifest.json", None, False),
        ]

        result = create_gpu_attempt("job")

        self.assertEqual(result["status"], "GPU_SUCCESS")
        self.assertEqual(result["manifest_object"], "manifest.json")
        self.assertEqual(cursor.execute.call_count, 2)

    @patch("job_repository.psycopg.connect")
    def test_claims_gpu_result_for_postprocess(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (
            "job", "case", "uploads/input.mp4", 123, "etag", 1.75,
            "model", "release", "PROCESSING", "GPU_SUCCESS", False,
        )
        cursor.rowcount = 1

        result = claim_postprocess_attempt("job", "attempt", "manifest.json")

        self.assertEqual(result["claim_status"], "CLAIMED")
        self.assertIn("status = 'POSTPROCESSING'", cursor.execute.call_args_list[1].args[0])

    @patch("job_repository.psycopg.connect")
    def test_live_postprocess_claim_is_busy(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (
            "job", "case", "uploads/input.mp4", 123, "etag", 1.75,
            "model", "release", "PROCESSING", "POSTPROCESSING", False,
        )

        result = claim_postprocess_attempt("job", "attempt", "manifest.json")

        self.assertEqual(result["claim_status"], "BUSY")
        self.assertEqual(cursor.execute.call_count, 1)

    @patch("job_repository.psycopg.connect")
    def test_completes_attempt_and_job_in_one_connection(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1

        result = complete_postprocess("job", "attempt", {
            "details": "details",
            "predictions": "predictions",
            "report": "report",
            "skeleton": "skeleton",
            "rendered_video": "video",
        })

        self.assertTrue(result)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertIn("status = 'SUCCESS'", cursor.execute.call_args_list[0].args[0])
        self.assertIn("artifact_validation_status = 'VALID'", cursor.execute.call_args_list[1].args[0])

    @patch("job_repository.psycopg.connect")
    def test_success_cannot_overwrite_a_final_job(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0
        result = mark_job_success("job", {
            "details": "details",
            "predictions": "predictions",
            "report": "report",
            "skeleton": "skeleton",
            "rendered_video": "video",
        })
        self.assertFalse(result)
        self.assertIn("status = 'PROCESSING'", cursor.execute.call_args.args[0])

    @patch("job_repository.psycopg.connect")
    def test_failure_cannot_overwrite_a_final_job(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0
        self.assertFalse(mark_job_failed("job", RuntimeError("failed")))
        self.assertIn(
            "status IN ('QUEUED', 'PROCESSING')",
            cursor.execute.call_args.args[0],
        )

    @patch("job_repository.psycopg.connect")
    def test_fails_attempt_and_job_in_one_transaction(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        self.assertTrue(
            fail_gpu_attempt_and_job("job", "attempt", RuntimeError("failed"))
        )
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertIn("inference_gpu_attempts", cursor.execute.call_args_list[0].args[0])
        self.assertIn("inference_jobs", cursor.execute.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
