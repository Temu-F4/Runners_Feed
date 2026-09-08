import os
import sys
import unittest
from unittest.mock import Mock, patch

try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["psycopg"] = Mock()

from job_repository import (
    create_gpu_attempt,
    finish_gpu_attempt,
    mark_job_failed,
    mark_job_success,
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
            ("attempt", 1, "RUNNING", True),
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
            ("attempt", 1, "RUNNING", False),
        ]
        result = create_gpu_attempt("job")
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual(cursor.execute.call_count, 2)

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


if __name__ == "__main__":
    unittest.main()
