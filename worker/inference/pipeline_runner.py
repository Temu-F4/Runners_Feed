from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path


StageContextFactory = Callable[[str], AbstractContextManager[None]]


@dataclass(frozen=True)
class PipelineResult:
    output_dir: Path
    log_output: str


def _default_stage_context(_: str) -> AbstractContextManager[None]:
    return nullcontext()


def _pipeline_commands(
    workspace_dir: Path,
    run_id: str,
    video_path: Path,
    input_dir: Path,
    output_dir: Path,
) -> tuple[tuple[str, list[str]], ...]:
    return (
        (
            "frame_extract",
            [
                sys.executable,
                "-m",
                "inference.extract_frames",
                str(video_path),
                str(input_dir),
            ],
        ),
        (
            "pose_inference",
            [
                sys.executable,
                "-m",
                "inference.hpe_model",
                str(workspace_dir),
                run_id,
                "--device",
                "cpu",
            ],
        ),
        (
            "report_generate",
            [
                sys.executable,
                "-m",
                "inference.report",
                str(output_dir / "details.json"),
                str(output_dir / "pose_predictions.json"),
                str(output_dir / "report.json"),
            ],
        ),
        (
            "frame_render",
            [
                sys.executable,
                "-m",
                "inference.render",
                str(input_dir),
                str(output_dir),
            ],
        ),
        (
            "video_compose",
            [
                sys.executable,
                "-m",
                "inference.compose_video",
                str(output_dir / "details.json"),
                str(output_dir / "rendered"),
                str(output_dir / "_rendered.mp4"),
            ],
        ),
        (
            "video_encode",
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stats",
                "-i",
                str(output_dir / "_rendered.mp4"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_dir / "rendered.mp4"),
            ],
        ),
    )


def run_pipeline(
    run_id: str,
    *,
    workspace_dir: Path = Path("/workspace"),
    timeout_seconds: int = 3600,
    stage_context: StageContextFactory = _default_stage_context,
) -> PipelineResult:
    run_dir = workspace_dir / "run" / run_id
    input_dir = run_dir / "inputs"
    output_dir = run_dir / "outputs"

    video_files = sorted(run_dir.glob("*.mp4"))
    if len(video_files) != 1:
        raise ValueError(
            f"Expected exactly one MP4 in {run_dir}, "
            f"found {len(video_files)}"
        )
    if output_dir.exists():
        raise FileExistsError(f"Output already exists: {output_dir}")
    if timeout_seconds <= 0:
        raise ValueError("Pipeline timeout must be positive")

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=False)

    deadline = time.monotonic() + timeout_seconds
    logs: list[str] = []

    for stage_key, command in _pipeline_commands(
        workspace_dir,
        run_id,
        video_files[0],
        input_dir,
        output_dir,
    ):
        try:
            with stage_context(stage_key):
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise TimeoutError(
                        f"Pipeline timed out before stage {stage_key}"
                    )
                completed = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=remaining_seconds,
                )
        except subprocess.CalledProcessError as error:
            error_log = (error.stderr or error.stdout or "")[-4000:]
            raise RuntimeError(
                f"Pipeline stage {stage_key} failed:\n{error_log}"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(
                f"Pipeline timed out during stage {stage_key}"
            ) from error

        logs.append(completed.stdout)
        logs.append(completed.stderr)

    return PipelineResult(
        output_dir=output_dir,
        log_output="".join(logs),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", nargs="?", default="test1")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
    )
    args = parser.parse_args()

    result = run_pipeline(
        args.run_id,
        timeout_seconds=args.timeout_seconds,
    )
    if result.log_output:
        print(result.log_output, end="")
    print("RTMPOSE_VIDEO_POC=PASS")
    print(f"결과 폴더: {result.output_dir}")


if __name__ == "__main__":
    main()
