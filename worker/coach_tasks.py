import json
import logging
import os
import re
import selectors
import shutil
import subprocess
import time
from pathlib import Path

from coach_celery_app import celery_app
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
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
STAGE_MARKER_PATTERN = re.compile(
    r"^COACH_STAGE_(START|SUCCESS)=([a-z_]+)$"
)
PIPELINE_STAGE_KEYS = (
    "frame_extract",
    "pose_inference",
    "frame_render",
    "video_compose",
    "feature_extract",
    "report_generate",
)


def validate_case_id(case_id: str) -> None:
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id")


def invoke_tracked_pipeline(
    command: list[str],
    *,
    timeout_seconds: int,
    stage_recorder: JobStageRecorder,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        process.kill()
        raise RuntimeError("Coach pipeline output stream is unavailable")

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_seconds
    output_lines: list[str] = []
    active_stage: str | None = None
    observed_stages: list[str] = []

    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                if active_stage is not None:
                    stage_recorder.finish(
                        active_stage,
                        status="FAILED",
                        error_code="TimeoutExpired",
                    )
                    active_stage = None
                raise subprocess.TimeoutExpired(
                    command,
                    timeout_seconds,
                    output="".join(output_lines),
                )

            for key, _ in selector.select(timeout=min(0.25, remaining)):
                line = key.fileobj.readline()
                if not line:
                    selector.unregister(key.fileobj)
                    continue

                output_lines.append(line)
                marker = STAGE_MARKER_PATTERN.fullmatch(line.strip())
                if marker is None:
                    continue

                action, stage_key = marker.groups()
                if action == "START":
                    if active_stage is not None:
                        raise RuntimeError(
                            "Coach pipeline started a stage before finishing "
                            f"{active_stage}: {stage_key}"
                        )
                    expected_index = len(observed_stages)
                    if (
                        expected_index >= len(PIPELINE_STAGE_KEYS)
                        or stage_key != PIPELINE_STAGE_KEYS[expected_index]
                    ):
                        expected = (
                            PIPELINE_STAGE_KEYS[expected_index]
                            if expected_index < len(PIPELINE_STAGE_KEYS)
                            else "end of pipeline"
                        )
                        raise RuntimeError(
                            "Coach pipeline stage order mismatch: "
                            f"expected {expected}, got {stage_key}"
                        )
                    stage_recorder.start(stage_key)
                    active_stage = stage_key
                    observed_stages.append(stage_key)
                else:
                    if active_stage != stage_key:
                        raise RuntimeError(
                            "Coach pipeline finished an unexpected stage: "
                            f"{stage_key}"
                        )
                    stage_recorder.finish(stage_key, status="SUCCESS")
                    active_stage = None

        return_code = process.wait()
        output = "".join(output_lines)
        if return_code != 0:
            if active_stage is not None:
                stage_recorder.finish(
                    active_stage,
                    status="FAILED",
                    error_code="CalledProcessError",
                )
                active_stage = None
            raise subprocess.CalledProcessError(
                return_code,
                command,
                output=output,
            )
        if active_stage is not None:
            stage_recorder.finish(
                active_stage,
                status="FAILED",
                error_code="MissingStageSuccess",
            )
            unfinished_stage = active_stage
            active_stage = None
            raise RuntimeError(
                f"Coach pipeline did not finish stage: {unfinished_stage}"
            )
        if tuple(observed_stages) != PIPELINE_STAGE_KEYS:
            raise RuntimeError(
                "Coach pipeline did not report every stage: "
                f"{observed_stages}"
            )
        return subprocess.CompletedProcess(
            command,
            return_code,
            stdout=output,
            stderr="",
        )
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait()
        if active_stage is not None:
            stage_recorder.finish(
                active_stage,
                status="FAILED",
                error_code="StageProtocolError",
            )
        raise
    finally:
        selector.close()


def execute_pipeline(
    case_id: str,
    job_id: str,
    run_id: str,
    stage_recorder: JobStageRecorder | None = None,
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

    command = ["/app/run_coach_pipeline.sh", run_id]

    def invoke_pipeline() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

    try:
        if stage_recorder is None:
            completed = invoke_pipeline()
        else:
            completed = invoke_tracked_pipeline(
                command,
                timeout_seconds=timeout_seconds,
                stage_recorder=stage_recorder,
            )
    except subprocess.CalledProcessError as error:
        error_log = (error.stderr or error.stdout or "")[-4000:]
        raise RuntimeError(f"Coach pipeline failed:\n{error_log}") from error

    required_artifacts = {
        "details": output_dir / "details.json",
        "predictions": output_dir / "pose_predictions.json",
        "report": output_dir / "report.json",
        "skeleton": output_dir / "skeleton.json.gz",
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
    stage_recorder: JobStageRecorder | None = None

    try:
        validate_case_id(case_id)
        validate_case_id(job_id)
        if not input_object_name:
            raise ValueError("input_object_name must not be empty")
        if not 0.5 <= user_height_m <= 2.5:
            raise ValueError("user_height_m must be between 0.5 and 2.5")

        mark_job_processing(job_id)
        stage_recorder = JobStageRecorder(job_id)
        stage_recorder.initialize()

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

        with stage_recorder.track("input_download"):
            storage = ObjectStorageGateway()
            storage.download_input(
                object_name=input_object_name,
                destination=run_dir / "input.mp4",
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
            "predictions": f"{output_prefix}/pose_predictions.json",
            "report": f"{output_prefix}/report.json",
            "skeleton": f"{output_prefix}/skeleton.json.gz",
            "rendered_video": f"{output_prefix}/rendered.mp4",
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
                source=output_dir / "skeleton.json.gz",
                object_name=result_objects["skeleton"],
                content_type="application/gzip",
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
