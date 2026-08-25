import os
import re
import subprocess
from pathlib import Path

from inference_celery_app import celery_app


WORKSPACE_DIR = Path("/workspace")
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@celery_app.task(
    name="inference.run_video",
    bind=True,
)
def run_video(self, case_id: str) -> dict:
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id")

    run_dir = WORKSPACE_DIR / "run" / case_id
    video_files = sorted(run_dir.glob("*.mp4"))

    if len(video_files) != 1:
        raise ValueError(
            f"Expected exactly one MP4 in {run_dir}, "
            f"found {len(video_files)}"
        )

    timeout_seconds = int(
        os.getenv("INFERENCE_TIMEOUT_SECONDS", "3600")
    )

    try:
        completed = subprocess.run(
            [
                "/app/inference/run_pipeline.sh",
                case_id,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

    except subprocess.CalledProcessError as error:
        error_log = (error.stderr or error.stdout or "")[-4000:]
        raise RuntimeError(
            f"RTMPose pipeline failed:\n{error_log}"
        ) from error

    output_dir = run_dir / "outputs"

    return {
        "job_id": self.request.id,
        "case_id": case_id,
        "status": "success",
        "artifacts": {
            "details": str(output_dir / "details.json"),
            "predictions": str(
                output_dir / "pose_predictions.json"
            ),
            "rendered_video": str(
                output_dir / "rendered.mp4"
            ),
        },
        "log_tail": (
            completed.stdout + completed.stderr
        )[-4000:],
    }
