import logging
import os
import re
import shutil
from pathlib import Path

from inference_celery_app import celery_app
from inference.pipeline_runner import run_pipeline
from job_repository import (
    mark_job_failed,
    mark_job_processing,
    mark_job_success,
)
from job_stages import JobStageRecorder
from object_storage_gateway import ObjectStorageGateway
from run_cleanup import remove_successful_run


LOGGER = logging.getLogger(__name__)
WORKSPACE_DIR = Path("/workspace")
CASE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)


def validate_case_id(case_id: str) -> None:
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id")


def execute_pipeline(
    case_id: str,
    job_id: str,
    run_id: str | None = None,
    stage_recorder: JobStageRecorder | None = None,
) -> dict:
    validate_case_id(case_id)

    pipeline_run_id = run_id or case_id
    validate_case_id(pipeline_run_id)

    run_dir = WORKSPACE_DIR / "run" / pipeline_run_id

    output_dir = run_dir / "outputs"

    timeout_seconds = int(
        os.getenv("INFERENCE_TIMEOUT_SECONDS", "3600")
    )

    if stage_recorder is None:
        pipeline = run_pipeline(
            pipeline_run_id,
            workspace_dir=WORKSPACE_DIR,
            timeout_seconds=timeout_seconds,
        )
    else:
        pipeline = run_pipeline(
            pipeline_run_id,
            workspace_dir=WORKSPACE_DIR,
            timeout_seconds=timeout_seconds,
            stage_context=stage_recorder.track,
        )

    return {
        "job_id": job_id,
        "case_id": case_id,
        "status": "success",
        "artifacts": {
            "details": str(
                output_dir / "details.json"
            ),
            "predictions": str(
                output_dir / "pose_predictions.json"
            ),
            "report": str(
                output_dir / "report.json"
            ),
            "rendered_video": str(
                output_dir / "rendered.mp4"
            ),
        },
        "log_tail": (
            pipeline.log_output
        )[-4000:],
    }


@celery_app.task(
    name="inference.run_video",
    bind=True,
    acks_late=False,
)
def run_video(self, case_id: str) -> dict:
    return execute_pipeline(
        case_id=case_id,
        job_id=self.request.id,
    )


@celery_app.task(
    name="inference.run_object_storage",
    bind=True,
)
def run_object_storage(
    self,
    case_id: str,
    input_object_name: str,
) -> dict:
    job_id = str(self.request.id)
    stage_recorder: JobStageRecorder | None = None

    try:
        validate_case_id(case_id)
        validate_case_id(job_id)

        if not input_object_name:
            raise ValueError(
                "input_object_name must not be empty"
            )

        mark_job_processing(job_id)
        stage_recorder = JobStageRecorder(job_id)
        stage_recorder.initialize()

        run_dir = WORKSPACE_DIR / "run" / job_id

        if run_dir.exists():
            shutil.rmtree(run_dir)

        run_dir.mkdir(parents=True, exist_ok=False)
        input_path = run_dir / "input.mp4"

        with stage_recorder.track("input_download"):
            storage = ObjectStorageGateway()
            storage.download_input(
                object_name=input_object_name,
                destination=input_path,
            )

        result = execute_pipeline(
            case_id=case_id,
            job_id=job_id,
            run_id=job_id,
            stage_recorder=stage_recorder,
        )

        output_dir = run_dir / "outputs"
        output_prefix = f"jobs/{job_id}"

        result_objects = {
            "details": f"{output_prefix}/details.json",
            "predictions": (
                f"{output_prefix}/pose_predictions.json"
            ),
            "report": f"{output_prefix}/report.json",
            "rendered_video": (
                f"{output_prefix}/rendered.mp4"
            ),
        }

        with stage_recorder.track("result_upload"):
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
            with stage_recorder.track(
                "workspace_cleanup",
                failure_status="WARNING",
            ):
                result["local_run_deleted"] = (
                    remove_successful_run(
                        run_dir,
                        run_root=WORKSPACE_DIR / "run",
                    )
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
        if stage_recorder is not None:
            try:
                stage_recorder.skip_pending()
            except Exception:
                LOGGER.exception(
                    "Failed to skip remaining stages for job %s",
                    job_id,
                )
        try:
            mark_job_failed(job_id, error)
        except Exception:
            LOGGER.exception(
                "Failed to persist FAILED state for job %s",
                job_id,
            )
        raise
