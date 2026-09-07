import os
import sys
import unittest
from unittest.mock import Mock, patch

try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["psycopg"] = Mock()

from job_repository import create_gpu_attempt, finish_gpu_attempt, start_gpu_attempt


class GPUAttemptTests(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "postgresql://test"

    @patch("job_repository.uuid4", return_value="attempt-uuid")
    @patch("job_repository.psycopg.connect")
    def test_create_attempt_locks_job_and_increments_number(self, connect, uuid4):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("job",), (2,)]
        result = create_gpu_attempt("job")
        self.assertEqual(result, {"attempt_id": "attempt-uuid", "attempt_number": 2})
        self.assertIn("FOR UPDATE", cursor.execute.call_args_list[0].args[0])

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
        self.assertFalse(finish_gpu_attempt("job", "old", "manifest"))
        self.assertIn("status = 'RUNNING'", cursor.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
