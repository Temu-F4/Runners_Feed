import json
import logging
import os
import re
import selectors
import shutil
import subprocess
import time
from pathlib import Path

from celery.exceptions import Retry
from coach_celery_app import celery_app
from job_repository import (
    accept_gpu_result,
    claim_postprocess_attempt,
    complete_postprocess,
    create_gpu_attempt,
    fail_gpu_attempt_and_job,
    get_gpu_attempt,
    mark_job_failed,
    mark_job_processing,
    mark_job_stage_running_if_pending,
    save_remote_job_id,
    start_gpu_attempt,
)
from job_stages import JobStageRecorder
from object_storage_gateway import ObjectStorageGateway
from output_validation import (
    ModelArtifactValidationError,
    validate_completed_artifacts,
)
from run_cleanup import remove_successful_run
from runpod_client import RunPodTransientError, client_from_environment
from video_analysis_contract import (
    build_request,
    validate_downloaded_artifacts,
    validate_manifest,
    verify_file,
)


LOGGER = logging.getLogger(__name__)
WORKSPACE_DIR = Path("/workspace")
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
STAGE_MARKER_PATTERN = re.compile(
    r"^COACH_STAGE_(START|SUCCESS)=([a-z_]+)$"
)
PIPELINE_STAGE_KEYS = (
    "video_analysis",
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
    expected_stage_keys: tuple[str, ...] = PIPELINE_STAGE_KEYS,
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
                        expected_index >= len(expected_stage_keys)
                        or stage_key != expected_stage_keys[expected_index]
                    ):
                        expected = (
                            expected_stage_keys[expected_index]
                            if expected_index < len(expected_stage_keys)
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
        if tuple(observed_stages) != expected_stage_keys:
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


def _prepare_run_directory(job_id: str, user_height_m: float) -> tuple[Path, Path]:
    validate_case_id(job_id)
    if not 0.5 <= user_height_m <= 2.5:
        raise ValueError("user_height_m must be between 0.5 and 2.5")
    run_dir = WORKSPACE_DIR / "run" / job_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    output_dir = run_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "user_info.json").write_text(
        json.dumps({"user": {"height": user_height_m}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir, output_dir


def _postprocess_pipeline(job_id: str, stage_recorder: JobStageRecorder) -> subprocess.CompletedProcess[str]:
    try:
        return invoke_tracked_pipeline(
            ["/app/run_coach_postprocess.sh", job_id],
            timeout_seconds=int(os.getenv("COACH_POSTPROCESS_TIMEOUT_SECONDS", "900")),
            stage_recorder=stage_recorder,
            expected_stage_keys=("feature_extract", "report_generate"),
        )
    except subprocess.CalledProcessError as error:
        error_log = (error.stderr or error.stdout or "")[-4000:]
        if "MODEL_CONTRACT_INVALID=" in error_log:
            raise ModelArtifactValidationError(error_log) from error
        raise RuntimeError(f"Coach postprocess failed:\n{error_log}") from error


@celery_app.task(
    name="coach.dispatch_video_analysis",
    bind=True,
    soft_time_limit=120,
    time_limit=180,
)
def dispatch_video_analysis(self, job_id: str) -> dict:
    """Submit the GPU boundary quickly, then hand monitoring to the poll task."""
    attempt_id: str | None = None
    stage_recorder: JobStageRecorder | None = None
    try:
        validate_case_id(job_id)
        attempt = create_gpu_attempt(
            job_id,
            stale_after_seconds=int(
                os.getenv("GPU_ATTEMPT_STALE_SECONDS", "4200")
            ),
        )
        if attempt["status"] in {"JOB_SUCCESS", "JOB_FAILED"}:
            return {
                "job_id": job_id,
                "status": f"already_{attempt['status'].lower()}",
            }
        attempt_id = attempt["attempt_id"]
        if attempt["status"] == "POSTPROCESSING":
            return {
                "job_id": job_id,
                "attempt_id": attempt_id,
                "status": "already_postprocessing",
            }
        if attempt["status"] == "GPU_SUCCESS":
            manifest_object = attempt["manifest_object"]
            if not manifest_object:
                raise RuntimeError("Completed GPU attempt has no manifest")
            celery_app.send_task(
                "coach.run_postprocess",
                args=[job_id, attempt_id, manifest_object],
                queue="postprocess",
            )
            return {
                "job_id": job_id,
                "attempt_id": attempt_id,
                "attempt_number": attempt["attempt_number"],
                "manifest_object": manifest_object,
                "status": "postprocess_requeued",
            }
        if attempt["status"] == "RUNNING":
            if attempt.get("remote_job_id"):
                celery_app.send_task(
                    "coach.poll_video_analysis",
                    args=[job_id, attempt_id],
                    queue="gpu_dispatch",
                    countdown=_poll_interval(),
                )
                return {
                    "job_id": job_id,
                    "attempt_id": attempt_id,
                    "remote_job_id": attempt["remote_job_id"],
                    "status": "poll_requeued",
                }
            snapshot = get_gpu_attempt(job_id, attempt_id)
        else:
            snapshot = start_gpu_attempt(job_id, attempt_id)
            if not mark_job_processing(
                job_id,
                model_id=snapshot["model_id"],
                model_release=snapshot["model_release"],
            ):
                raise RuntimeError("Job reached a final state before GPU dispatch")
        stage_recorder = JobStageRecorder(job_id)
        if attempt["status"] == "QUEUED":
            stage_recorder.initialize()
        else:
            stage_recorder.attach_existing()
        storage = ObjectStorageGateway()
        request_without_transfer = build_request(
            snapshot, attempt_id, Path("/app/coach")
        )
        transfer = storage.create_video_analysis_transfer(
            input_object_name=snapshot["input_object_name"],
            result_prefix=request_without_transfer["result_prefix"],
            ttl_seconds=int(os.getenv("RUNPOD_SIGNED_URL_TTL_SECONDS", "7200")),
        )
        request = build_request(
            snapshot, attempt_id, Path("/app/coach"), transfer=transfer
        )
        response = client_from_environment().submit(request)
        remote_job_id = response["remote_job_id"]
        if not save_remote_job_id(job_id, attempt_id, remote_job_id):
            raise RuntimeError("GPU attempt was superseded before submit completed")
        celery_app.send_task(
            "coach.poll_video_analysis",
            args=[job_id, attempt_id],
            queue="gpu_dispatch",
            countdown=_poll_interval(),
        )
        return {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "attempt_number": attempt["attempt_number"],
            "remote_job_id": remote_job_id,
            "status": "submitted",
        }
    except Retry:
        raise
    except RunPodTransientError as error:
        if self.request.retries >= 20:
            if attempt_id is not None:
                try:
                    fail_gpu_attempt_and_job(job_id, attempt_id, error)
                except Exception:
                    LOGGER.exception("Failed to persist exhausted GPU submit for %s", job_id)
            elif mark_job_failed(job_id, error) is False:
                LOGGER.warning("GPU submit exhausted after job reached a final state: %s", job_id)
            if stage_recorder is not None:
                try:
                    stage_recorder.skip_pending()
                except Exception:
                    LOGGER.exception("Failed to skip stages after exhausted GPU submit for %s", job_id)
            raise
        raise self.retry(
            exc=error,
            countdown=_transient_retry_interval(),
            max_retries=20,
        )
    except Exception as error:
        if attempt_id is not None:
            try:
                fail_gpu_attempt_and_job(job_id, attempt_id, error)
            except Exception:
                LOGGER.exception("Failed to persist GPU attempt failure for job %s", job_id)
        if stage_recorder is not None:
            try:
                stage_recorder.skip_pending()
            except Exception:
                LOGGER.exception("Failed to skip remaining stages for job %s", job_id)
        if attempt_id is None:
            try:
                mark_job_failed(job_id, error)
            except Exception:
                LOGGER.exception("Failed to persist FAILED state for job %s", job_id)
        raise


def _poll_interval() -> int:
    value = int(os.getenv("RUNPOD_POLL_INTERVAL_SECONDS", "3"))
    if value < 1:
        raise ValueError("RUNPOD_POLL_INTERVAL_SECONDS must be positive")
    return value


def _transient_retry_interval() -> int:
    value = int(os.getenv("RUNPOD_TRANSIENT_RETRY_INTERVAL_SECONDS", "10"))
    if value < 1:
        raise ValueError("RUNPOD_TRANSIENT_RETRY_INTERVAL_SECONDS must be positive")
    return value


def _max_poll_seconds() -> int:
    value = int(os.getenv("RUNPOD_MAX_POLL_SECONDS", "4200"))
    if value < 1:
        raise ValueError("RUNPOD_MAX_POLL_SECONDS must be positive")
    return value


class RunPodPollingTimeout(RuntimeError):
    pass


@celery_app.task(
    name="coach.poll_video_analysis",
    bind=True,
    soft_time_limit=120,
    time_limit=180,
)
def poll_video_analysis(self, job_id: str, attempt_id: str) -> dict:
    """Poll once without sleeping, scheduling another short task when needed."""
    stage_recorder = JobStageRecorder(job_id)
    try:
        validate_case_id(job_id)
        attempt = get_gpu_attempt(job_id, attempt_id)
        if attempt["status"] in {"GPU_SUCCESS", "POSTPROCESSING", "SUCCESS"}:
            return {"job_id": job_id, "attempt_id": attempt_id, "status": "already_complete"}
        if attempt["status"] == "FAILED":
            return {"job_id": job_id, "attempt_id": attempt_id, "status": "already_failed"}
        if attempt["status"] != "RUNNING" or not attempt["remote_job_id"]:
            raise RuntimeError("GPU attempt is not submitted")
        elapsed = float(attempt["elapsed_seconds"] or 0)
        if elapsed >= _max_poll_seconds():
            raise RunPodPollingTimeout(
                f"RunPod polling exceeded {_max_poll_seconds()} seconds"
            )
        response = client_from_environment().poll(
            attempt["remote_job_id"],
            job_id=job_id,
            attempt_id=attempt_id,
        )
        if response["status"] in {"queued", "running"}:
            if response["status"] == "running":
                mark_job_stage_running_if_pending(job_id, "video_analysis")
            celery_app.send_task(
                "coach.poll_video_analysis",
                args=[job_id, attempt_id],
                queue="gpu_dispatch",
                countdown=_poll_interval(),
            )
            return {"job_id": job_id, "attempt_id": attempt_id, "status": response["status"]}

        manifest_object = response["manifest_object"]
        request = build_request(attempt, attempt_id, Path("/app/coach"))
        manifest = ObjectStorageGateway().load_result_json(manifest_object)
        validate_manifest(manifest, request)
        if not accept_gpu_result(job_id, attempt_id, manifest_object):
            return {"job_id": job_id, "attempt_id": attempt_id, "status": "already_complete"}
        timings = manifest["timings_seconds"]
        stage_recorder.attach_existing()
        stage_recorder.record_external("input_download", float(timings["download"]))
        stage_recorder.record_external(
            "video_analysis", float(timings["analysis"]) + float(timings["encode"])
        )
        celery_app.send_task(
            "coach.run_postprocess",
            args=[job_id, attempt_id, manifest_object],
            queue="postprocess",
        )
        return {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "manifest_object": manifest_object,
            "status": "postprocess_queued",
        }
    except RunPodTransientError:
        celery_app.send_task(
            "coach.poll_video_analysis",
            args=[job_id, attempt_id],
            queue="gpu_dispatch",
            countdown=_transient_retry_interval(),
        )
        return {"job_id": job_id, "attempt_id": attempt_id, "status": "poll_retry"}
    except Exception as error:
        fail_gpu_attempt_and_job(job_id, attempt_id, error)
        try:
            stage_recorder.attach_existing()
            stage_recorder.skip_pending()
        except Exception:
            LOGGER.exception("Failed to close stages for job %s", job_id)
        raise

@celery_app.task(name="coach.run_postprocess", bind=True)
def run_postprocess(
    self,
    job_id: str,
    attempt_id: str,
    manifest_object: str,
) -> dict:
    """Verify RunPod artifacts and run only feature/report adapters on OCI."""
    stage_recorder = JobStageRecorder(job_id)
    run_dir: Path | None = None
    try:
        validate_case_id(job_id)
        snapshot = claim_postprocess_attempt(
            job_id,
            attempt_id,
            manifest_object,
            stale_after_seconds=int(
                os.getenv("POSTPROCESS_ATTEMPT_STALE_SECONDS", "1200")
            ),
        )
        if snapshot["claim_status"] == "COMPLETE":
            return {
                "job_id": job_id,
                "attempt_id": attempt_id,
                "status": "already_success",
            }
        if snapshot["claim_status"] == "BUSY":
            raise self.retry(countdown=30, max_retries=40)
        stage_recorder.attach_existing()
        request = build_request(snapshot, attempt_id, Path("/app/coach"))
        storage = ObjectStorageGateway()
        manifest = storage.load_result_json(manifest_object)
        validate_manifest(manifest, request)

        run_dir, output_dir = _prepare_run_directory(job_id, snapshot["height_snapshot_m"])
        for role in ("predictions", "details", "video"):
            metadata = manifest["objects"][role]
            if metadata["bytes"] > 512 * 1024 * 1024:
                raise ValueError(f"RunPod artifact exceeds size limit: {role}")
            destination = output_dir / Path(metadata["object_name"]).name
            storage.download_result(
                metadata["object_name"],
                destination,
                max_bytes=metadata["bytes"],
            )
            verify_file(destination, metadata)
        validate_downloaded_artifacts(output_dir)

        _postprocess_pipeline(job_id, stage_recorder)
        required_artifacts = {
            "details": output_dir / "details.json",
            "predictions": output_dir / "pose_predictions.json",
            "report": output_dir / "report.json",
            "skeleton": output_dir / "skeleton.json.gz",
            "rendered_video": output_dir / "rendered.mp4",
        }
        missing = [str(path) for path in required_artifacts.values() if not path.is_file()]
        if missing:
            raise ModelArtifactValidationError("Postprocess did not create required artifacts: " + ", ".join(missing))
        validate_completed_artifacts(required_artifacts)

        postprocess_prefix = f"{request['result_prefix']}/postprocess/{self.request.id}"
        postprocess_objects = {
            "features_raw": f"{postprocess_prefix}/feature_results.json",
            "features": f"{postprocess_prefix}/feature_results.service.json",
            "report": f"{postprocess_prefix}/report.json",
            "skeleton": f"{postprocess_prefix}/skeleton.json.gz",
        }
        with stage_recorder.track("result_upload"):
            for role, filename, content_type in (
                ("features_raw", "feature_results.json", "application/json"),
                ("features", "feature_results.service.json", "application/json"),
                ("report", "report.json", "application/json"),
                ("skeleton", "skeleton.json.gz", "application/gzip"),
            ):
                storage.upload_result(output_dir / filename, postprocess_objects[role], content_type)

        result_objects = {
            "details": manifest["objects"]["details"]["object_name"],
            "predictions": manifest["objects"]["predictions"]["object_name"],
            "report": postprocess_objects["report"],
            "skeleton": postprocess_objects["skeleton"],
            "rendered_video": manifest["objects"]["video"]["object_name"],
        }
        if not complete_postprocess(job_id, attempt_id, result_objects):
            raise RuntimeError("Job reached a final state before postprocess completed")
        try:
            with stage_recorder.track("workspace_cleanup", failure_status="WARNING"):
                remove_successful_run(run_dir, run_root=WORKSPACE_DIR / "run")
        except Exception:
            LOGGER.warning("Failed to clean successful run directory for job %s", job_id, exc_info=True)
        return {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "manifest_object": manifest_object,
            "result_objects": result_objects,
            "feature_object": postprocess_objects["features"],
        }
    except Retry:
        raise
    except Exception as error:
        try:
            fail_gpu_attempt_and_job(
                job_id,
                attempt_id,
                error,
                artifact_invalid=isinstance(
                    error, (ModelArtifactValidationError, ValueError)
                ),
            )
        except Exception:
            LOGGER.exception("Failed to persist postprocess attempt failure for job %s", job_id)
        try:
            stage_recorder.skip_pending()
        except Exception:
            LOGGER.exception("Failed to skip remaining stages for job %s", job_id)
        raise
