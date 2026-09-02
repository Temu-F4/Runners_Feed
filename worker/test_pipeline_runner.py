import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from inference.pipeline_runner import run_pipeline


class PipelineRunnerTest(unittest.TestCase):
    def _workspace(self, temporary_dir: str) -> Path:
        workspace = Path(temporary_dir) / "workspace"
        run_dir = workspace / "run" / "job-1"
        run_dir.mkdir(parents=True)
        (run_dir / "input.mp4").write_bytes(b"video")
        return workspace

    def test_runs_six_internal_stages_in_existing_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            workspace = self._workspace(temporary_dir)
            events: list[tuple[str, str]] = []

            @contextmanager
            def stage_context(stage_key: str):
                events.append(("start", stage_key))
                try:
                    yield
                finally:
                    events.append(("finish", stage_key))

            completed = SimpleNamespace(stdout="ok\n", stderr="")
            with patch(
                "inference.pipeline_runner.subprocess.run",
                return_value=completed,
            ) as run:
                result = run_pipeline(
                    "job-1",
                    workspace_dir=workspace,
                    timeout_seconds=60,
                    stage_context=stage_context,
                )

            stage_keys = [
                stage_key
                for event, stage_key in events
                if event == "start"
            ]
            self.assertEqual(
                stage_keys,
                [
                    "frame_extract",
                    "pose_inference",
                    "report_generate",
                    "frame_render",
                    "video_compose",
                    "video_encode",
                ],
            )
            self.assertEqual(run.call_count, 6)
            self.assertTrue(result.output_dir.is_dir())
            self.assertEqual(result.log_output, "ok\n" * 6)

            timeouts = [
                invocation.kwargs["timeout"]
                for invocation in run.call_args_list
            ]
            self.assertTrue(all(timeout > 0 for timeout in timeouts))
            self.assertTrue(
                all(
                    later <= earlier
                    for earlier, later in zip(timeouts, timeouts[1:])
                )
            )

    def test_reports_the_failed_stage_and_stops_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            workspace = self._workspace(temporary_dir)
            completed = SimpleNamespace(stdout="ok", stderr="")
            failure = subprocess.CalledProcessError(
                returncode=1,
                cmd=["pose"],
                stderr="pose failed",
            )

            with patch(
                "inference.pipeline_runner.subprocess.run",
                side_effect=[completed, failure],
            ) as run:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "pose_inference",
                ):
                    run_pipeline(
                        "job-1",
                        workspace_dir=workspace,
                        timeout_seconds=60,
                    )

            self.assertEqual(run.call_count, 2)

    def test_rejects_multiple_input_videos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            workspace = self._workspace(temporary_dir)
            run_dir = workspace / "run" / "job-1"
            (run_dir / "other.mp4").write_bytes(b"video")

            with self.assertRaisesRegex(ValueError, "exactly one MP4"):
                run_pipeline(
                    "job-1",
                    workspace_dir=workspace,
                )


if __name__ == "__main__":
    unittest.main()
