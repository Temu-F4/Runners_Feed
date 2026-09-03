import tempfile
import unittest
import sys
from types import ModuleType
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

psycopg_module = sys.modules.setdefault("psycopg", ModuleType("psycopg"))
if not hasattr(psycopg_module, "connect"):
    psycopg_module.connect = MagicMock()
psycopg_rows_module = sys.modules.setdefault(
    "psycopg.rows",
    ModuleType("psycopg.rows"),
)
psycopg_rows_module.dict_row = object()
object_storage_module = sys.modules.setdefault(
    "object_storage_gateway",
    ModuleType("object_storage_gateway"),
)
object_storage_module.ObjectStorageGateway = MagicMock

import maintenance


class MaintenanceTest(unittest.TestCase):
    @patch("maintenance.delete_user")
    @patch("maintenance.list_user_artifacts")
    @patch("maintenance.list_inactive_guest_users")
    @patch("maintenance.list_expired_failed_jobs")
    @patch("maintenance.clear_transient_result_objects")
    @patch("maintenance.list_expired_transient_results")
    @patch("maintenance.clear_input_object")
    @patch("maintenance.list_expired_inputs")
    @patch("maintenance.ObjectStorageGateway")
    def test_applies_each_retention_policy(
        self,
        gateway_type,
        list_inputs,
        clear_input,
        list_results,
        clear_results,
        list_failed,
        list_inactive,
        list_artifacts,
        delete_user,
    ) -> None:
        input_job = uuid4()
        result_job = uuid4()
        failed_job = uuid4()
        guest_user = uuid4()
        list_inputs.return_value = [
            {"job_id": input_job, "input_object_name": "uploads/input.mp4"}
        ]
        list_results.return_value = [
            {
                "job_id": result_job,
                "result_details_object": "jobs/id/details.json",
                "result_predictions_object": "jobs/id/pose_predictions.json",
                "result_video_object": "jobs/id/rendered.mp4",
            }
        ]
        list_failed.return_value = [{"job_id": failed_job}]
        list_inactive.return_value = [{"user_id": guest_user}]
        list_artifacts.return_value = [
            {
                "result_report_object": "jobs/id/report.json",
                "result_skeleton_object": "jobs/id/skeleton.json.gz",
            }
        ]
        storage = gateway_type.return_value

        with tempfile.TemporaryDirectory() as temporary_directory:
            run_root = Path(temporary_directory)
            (run_root / str(failed_job)).mkdir()
            with patch.object(maintenance, "RUN_ROOT", run_root):
                counts = maintenance.run_once(
                    datetime(2026, 9, 3, tzinfo=timezone.utc)
                )

        storage.delete_input.assert_called_once_with("uploads/input.mp4")
        self.assertEqual(storage.delete_result.call_count, 5)
        clear_input.assert_called_once_with(input_job)
        clear_results.assert_called_once_with(result_job)
        delete_user.assert_called_once_with(guest_user)
        self.assertEqual(
            counts,
            {"inputs": 1, "results": 1, "failed_runs": 1, "guest_users": 1},
        )

    @patch.dict("os.environ", {"FAILED_RUN_TTL_HOURS": "0"})
    def test_rejects_non_positive_retention(self) -> None:
        with self.assertRaises(ValueError):
            maintenance.run_once(
                datetime(2026, 9, 3, tzinfo=timezone.utc)
            )


if __name__ == "__main__":
    unittest.main()
