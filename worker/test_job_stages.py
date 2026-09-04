import sys
import unittest
from unittest.mock import Mock, call, patch

try:
    import psycopg  # noqa: F401
except ModuleNotFoundError:
    sys.modules["psycopg"] = Mock()

from job_stages import JOB_STAGE_DEFINITIONS, JobStageRecorder


class JobStageRecorderTest(unittest.TestCase):
    def test_defines_current_pipeline_in_execution_order(self) -> None:
        self.assertEqual(
            JOB_STAGE_DEFINITIONS,
            (
                (1, "input_download"),
                (2, "video_analysis"),
                (3, "feature_extract"),
                (4, "report_generate"),
                (5, "result_upload"),
                (6, "workspace_cleanup"),
            ),
        )

    @patch("job_stages.mark_job_stage_finished")
    @patch("job_stages.mark_job_stage_running")
    @patch("job_stages.initialize_job_stages")
    @patch("job_stages.time.perf_counter", side_effect=[10.0, 12.5])
    def test_records_successful_stage_duration(
        self,
        _perf_counter,
        initialize,
        mark_running,
        mark_finished,
    ) -> None:
        recorder = JobStageRecorder("job-1")
        recorder.initialize()

        with recorder.track("input_download"):
            pass

        initialize.assert_called_once_with(
            "job-1",
            JOB_STAGE_DEFINITIONS,
        )
        mark_running.assert_called_once_with(
            "job-1",
            "input_download",
        )
        mark_finished.assert_called_once_with(
            "job-1",
            "input_download",
            status="SUCCESS",
            duration_seconds=2.5,
        )

    @patch("job_stages.mark_job_stage_finished")
    @patch("job_stages.mark_job_stage_running")
    @patch("job_stages.initialize_job_stages")
    @patch("job_stages.time.perf_counter", side_effect=[20.0, 21.25])
    def test_records_cleanup_failure_as_warning(
        self,
        _perf_counter,
        _initialize,
        _mark_running,
        mark_finished,
    ) -> None:
        recorder = JobStageRecorder("job-2")
        recorder.initialize()

        with self.assertRaisesRegex(RuntimeError, "cleanup"):
            with recorder.track(
                "workspace_cleanup",
                failure_status="WARNING",
            ):
                raise RuntimeError("cleanup")

        mark_finished.assert_has_calls(
            [
                call(
                    "job-2",
                    "workspace_cleanup",
                    status="WARNING",
                    duration_seconds=1.25,
                    error_code="RuntimeError",
                )
            ]
        )

    @patch("job_stages.mark_job_stage_finished")
    @patch("job_stages.mark_job_stage_running")
    @patch("job_stages.initialize_job_stages")
    @patch("job_stages.time.perf_counter", side_effect=[30.0, 34.0])
    def test_supports_stage_markers_from_pipeline_process(
        self,
        _perf_counter,
        _initialize,
        mark_running,
        mark_finished,
    ) -> None:
        recorder = JobStageRecorder("job-4")
        recorder.initialize()

        recorder.start("video_analysis")
        recorder.finish("video_analysis", status="SUCCESS")

        mark_running.assert_called_once_with("job-4", "video_analysis")
        mark_finished.assert_called_once_with(
            "job-4",
            "video_analysis",
            status="SUCCESS",
            duration_seconds=4.0,
        )

    @patch("job_stages.mark_pending_job_stages_skipped")
    @patch("job_stages.initialize_job_stages")
    def test_skips_only_after_initialization(
        self,
        _initialize,
        mark_skipped,
    ) -> None:
        recorder = JobStageRecorder("job-3")
        recorder.skip_pending()
        mark_skipped.assert_not_called()

        recorder.initialize()
        recorder.skip_pending()
        mark_skipped.assert_called_once_with("job-3")


if __name__ == "__main__":
    unittest.main()
