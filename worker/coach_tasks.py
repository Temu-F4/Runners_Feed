import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from coach_celery_app import celery_app
from job_repository import (
    mark_job_failed,
    mark_job_processing,
    mark_job_success,
)
from object_storage_gateway import ObjectStorageGateway
from run_cleanup import remove_successful_run


LOGGER = logging.getLogger(__name__)
WORKSPACE_DIR = Path("/workspace")
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_case_id(case_id: str) -> None:
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id")


def execute_pipeline(
    case_id: str,
    job_id: str,
    run_id: str,
) -> dict:
    validate_case_id(case_id)
    validate_case_id(run_id)

    run_dir = WORKSPACE_DIR / "run" / run_id
    video_files = sorted(run_dir.glob("*.mp4"))
    if len(video_files) != 1:
        raise ValueError(
            f"Expected exactly one MP4 in {run_dir}, found {len(video_files)}"
        )

    output_dir = run_dir / "outputs"
    if output_dir.exists():
        raise FileExistsError(f"Output already exists: {output_dir}")

    timeout_seconds = int(os.getenv("COACH_TIMEOUT_SECONDS", "3600"))
    try:
        completed = subprocess.run(
            ["/app/run_coach_pipeline.sh", run_id],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.CalledProcessError as error:
        error_log = (error.stderr or error.stdout or "")[-4000:]
        raise RuntimeError(f"Coach pipeline failed:\n{error_log}") from error

    required_artifacts = {
        "details": output_dir / "details.json",
        "predictions": output_dir / "pose_predictions.json",
        "report": output_dir / "report.json",
        "rendered_video": output_dir / "rendered.mp4",
    }
    missing = [
        str(path)
        for path in required_artifacts.values()
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Coach pipeline did not create required artifacts: "
            + ", ".join(missing)
        )

    return {
        "job_id": job_id,
        "case_id": case_id,
        "status": "success",
        "artifacts": {
            name: str(path)
            for name, path in required_artifacts.items()
        },
        "log_tail": (completed.stdout + completed.stderr)[-4000:],
    }


@celery_app.task(name="coach.run_object_storage", bind=True)
def run_object_storage(
    self,
    case_id: str,
    input_object_name: str,
    user_height_m: float,
) -> dict:
    job_id = str(self.request.id)

    try:
        validate_case_id(case_id)
        validate_case_id(job_id)
        if not input_object_name:
            raise ValueError("input_object_name must not be empty")
        if not 0.5 <= user_height_m <= 2.5:
            raise ValueError("user_height_m must be between 0.5 and 2.5")

        mark_job_processing(job_id)
        run_dir = WORKSPACE_DIR / "run" / job_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=False)

        (run_dir / "user_info.json").write_text(
            json.dumps(
                {"user": {"height": user_height_m}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        storage = ObjectStorageGateway()
        storage.download_input(
            object_name=input_object_name,
            destination=run_dir / "input.mp4",
        )

        result = execute_pipeline(
            case_id=case_id,
            job_id=job_id,
            run_id=job_id,
        )
        output_dir = run_dir / "outputs"
        output_prefix = f"jobs/{job_id}"
        result_objects = {
            "details": f"{output_prefix}/details.json",
            "predictions": f"{output_prefix}/pose_predictions.json",
            "report": f"{output_prefix}/report.json",
            "rendered_video": f"{output_prefix}/rendered.mp4",
        }

        storage.upload_result(
            source=output_dir / "details.json",
            object_name=result_objects["details"],
            content_type="application/json",
        )
        storage.upload_result(
            source=output_dir / "pose_predictions.json",
            object_name=result_objects["predictions"],
            content_type="application/json",
        )
        storage.upload_result(
            source=output_dir / "report.json",
            object_name=result_objects["report"],
            content_type="application/json",
        )
        storage.upload_result(
            source=output_dir / "rendered.mp4",
            object_name=result_objects["rendered_video"],
            content_type="video/mp4",
        )

        mark_job_success(job_id, result_objects)
        try:
            result["local_run_deleted"] = remove_successful_run(
                run_dir,
                run_root=WORKSPACE_DIR / "run",
            )
        except Exception:
            result["local_run_deleted"] = False
            LOGGER.warning(
                "Failed to clean successful run directory for job %s",
                job_id,
                exc_info=True,
            )

        result["input_object"] = input_object_name
        result["result_objects"] = result_objects
        return result
    except Exception as error:
        try:
            mark_job_failed(job_id, error)
        except Exception:
            LOGGER.exception(
                "Failed to persist FAILED state for job %s",
                job_id,
            )
        raise
