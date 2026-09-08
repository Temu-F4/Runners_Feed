import os
from typing import Any
from uuid import uuid4

import psycopg


FINISHED_STAGE_STATUSES = {
    "SUCCESS",
    "FAILED",
    "WARNING",
}


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def create_gpu_attempt(
    job_id: str,
    *,
    stale_after_seconds: int = 4200,
) -> dict[str, Any]:
    """Create, reuse, or recover the only active GPU attempt for one job."""
    if stale_after_seconds < 1:
        raise ValueError("stale_after_seconds must be positive")
    attempt_id = str(uuid4())
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM inference_jobs WHERE job_id = %s FOR UPDATE",
                (job_id,),
            )
            job_row = cursor.fetchone()
            if job_row is None:
                raise LookupError(f"Unknown job: {job_id}")
            if job_row[0] in {"SUCCESS", "FAILED"}:
                return {"status": f"JOB_{job_row[0]}"}
            cursor.execute(
                """
                SELECT attempt_id, attempt_number, status, manifest_object,
                       remote_job_id,
                       (
                           status IN ('RUNNING', 'POSTPROCESSING')
                           AND updated_at < NOW() - (%s * INTERVAL '1 second')
                       ) AS stale
                FROM inference_gpu_attempts
                WHERE job_id = %s AND status IN (
                    'QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING'
                )
                FOR UPDATE
                """,
                (stale_after_seconds, job_id),
            )
            active = cursor.fetchone()
            if active is not None:
                (active_id, active_number, active_status, manifest_object,
                 remote_job_id, is_stale) = active
                if active_status in {"RUNNING", "POSTPROCESSING"} and not is_stale:
                    return {
                        "attempt_id": str(active_id),
                        "attempt_number": active_number,
                        "status": active_status,
                        "manifest_object": manifest_object,
                        "remote_job_id": remote_job_id,
                    }
                if active_status in {"RUNNING", "POSTPROCESSING"} and not (
                    active_status == "RUNNING" and remote_job_id
                ):
                    recovered_status = (
                        "QUEUED" if active_status == "RUNNING" else "GPU_SUCCESS"
                    )
                    cursor.execute(
                        """
                        UPDATE inference_gpu_attempts
                        SET status = %s, started_at = CASE
                                WHEN %s = 'QUEUED' THEN NULL ELSE started_at
                            END,
                            error_code = 'StaleAttemptRecovered',
                            error_message = NULL, updated_at = NOW()
                        WHERE attempt_id = %s AND status = %s
                        """,
                        (recovered_status, recovered_status, active_id, active_status),
                    )
                returned_status = active_status
                if active_status in {"RUNNING", "POSTPROCESSING"} and not (
                    active_status == "RUNNING" and remote_job_id
                ) and is_stale:
                    returned_status = recovered_status
                return {
                    "attempt_id": str(active_id),
                    "attempt_number": active_number,
                    "status": returned_status,
                    "manifest_object": manifest_object,
                    "remote_job_id": remote_job_id,
                }
            cursor.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) + 1 AS attempt_number
                FROM inference_gpu_attempts
                WHERE job_id = %s
                """,
                (job_id,),
            )
            attempt_number = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO inference_gpu_attempts (
                    attempt_id, job_id, attempt_number, status
                ) VALUES (%s, %s, %s, 'QUEUED')
                """,
                (attempt_id, job_id, attempt_number),
            )
    return {
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "status": "QUEUED",
    }


def start_gpu_attempt(job_id: str, attempt_id: str) -> dict[str, Any]:
    """Claim one queued attempt and return its immutable dispatch snapshot."""
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'RUNNING', started_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s AND status = 'QUEUED'
                """,
                (job_id, attempt_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("GPU attempt is not the queued current attempt")
            cursor.execute(
                """
                SELECT job_id, case_id, input_object_name, input_size_bytes,
                       input_etag, height_snapshot_m, model_id, model_release
                FROM inference_jobs WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"Unknown job: {job_id}")
            return dict(zip(
                ("job_id", "case_id", "input_object_name", "input_size_bytes",
                 "input_etag", "height_snapshot_m", "model_id", "model_release"),
                row,
            ))


def finish_gpu_attempt(job_id: str, attempt_id: str, manifest_object: str) -> bool:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'GPU_SUCCESS', manifest_object = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s AND status = 'RUNNING'
                """,
                (manifest_object, job_id, attempt_id),
            )
            if cursor.rowcount == 1:
                return True
            cursor.execute(
                """
                SELECT status, manifest_object
                FROM inference_gpu_attempts
                WHERE job_id = %s AND attempt_id = %s
                """,
                (job_id, attempt_id),
            )
            row = cursor.fetchone()
            return (
                row is not None
                and row[0] in {"GPU_SUCCESS", "POSTPROCESSING", "SUCCESS"}
                and row[1] == manifest_object
            )


def save_remote_job_id(job_id: str, attempt_id: str, remote_job_id: str) -> bool:
    """Persist the submit result once; an identical redelivery is idempotent."""
    if not remote_job_id.strip():
        raise ValueError("remote_job_id is required")
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET remote_job_id = %s, updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s AND status = 'RUNNING'
                  AND (remote_job_id IS NULL OR remote_job_id = %s)
                """,
                (remote_job_id, job_id, attempt_id, remote_job_id),
            )
            return cursor.rowcount == 1


def get_gpu_attempt(job_id: str, attempt_id: str) -> dict[str, Any]:
    """Return polling state and immutable request fields for one active attempt."""
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT attempts.status, attempts.remote_job_id,
                       attempts.manifest_object,
                       EXTRACT(EPOCH FROM (NOW() - attempts.started_at)),
                       jobs.job_id, jobs.case_id, jobs.input_object_name,
                       jobs.input_size_bytes, jobs.input_etag,
                       jobs.height_snapshot_m, jobs.model_id, jobs.model_release
                FROM inference_gpu_attempts AS attempts
                JOIN inference_jobs AS jobs ON jobs.job_id = attempts.job_id
                WHERE attempts.job_id = %s AND attempts.attempt_id = %s
                """,
                (job_id, attempt_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"Unknown GPU attempt: {attempt_id}")
            return dict(zip(
                ("status", "remote_job_id", "manifest_object", "elapsed_seconds",
                 "job_id", "case_id", "input_object_name", "input_size_bytes",
                 "input_etag", "height_snapshot_m", "model_id", "model_release"),
                row,
            ))


def accept_gpu_result(job_id: str, attempt_id: str, manifest_object: str) -> bool:
    """Atomically accept a complete poll exactly once."""
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'GPU_SUCCESS', manifest_object = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s AND status = 'RUNNING'
                  AND remote_job_id IS NOT NULL
                """,
                (manifest_object, job_id, attempt_id),
            )
            return cursor.rowcount == 1


def claim_postprocess_attempt(
    job_id: str,
    attempt_id: str,
    manifest_object: str,
    *,
    stale_after_seconds: int = 1200,
) -> dict[str, Any]:
    """Atomically claim the accepted GPU result for OCI postprocessing."""
    if stale_after_seconds < 1:
        raise ValueError("stale_after_seconds must be positive")
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT jobs.job_id, jobs.case_id, jobs.input_object_name,
                       jobs.input_size_bytes, jobs.input_etag,
                       jobs.height_snapshot_m, jobs.model_id, jobs.model_release,
                       jobs.status, attempts.status,
                       attempts.updated_at < NOW() - (%s * INTERVAL '1 second')
                FROM inference_jobs AS jobs
                JOIN inference_gpu_attempts AS attempts
                  ON attempts.job_id = jobs.job_id
                WHERE jobs.job_id = %s
                  AND attempts.attempt_id = %s
                  AND attempts.manifest_object = %s
                FOR UPDATE OF jobs, attempts
                """,
                (stale_after_seconds, job_id, attempt_id, manifest_object),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("GPU attempt is not the accepted postprocess input")
            snapshot = dict(zip(
                ("job_id", "case_id", "input_object_name", "input_size_bytes",
                 "input_etag", "height_snapshot_m", "model_id", "model_release",
                 "job_status", "attempt_status", "attempt_stale"),
                row,
            ))
            if snapshot["job_status"] == "SUCCESS" and snapshot["attempt_status"] == "SUCCESS":
                snapshot["claim_status"] = "COMPLETE"
                return snapshot
            if snapshot["job_status"] != "PROCESSING":
                raise RuntimeError("Job is not available for postprocess")
            if (
                snapshot["attempt_status"] == "POSTPROCESSING"
                and not snapshot["attempt_stale"]
            ):
                snapshot["claim_status"] = "BUSY"
                return snapshot
            if snapshot["attempt_status"] not in {"GPU_SUCCESS", "POSTPROCESSING"}:
                raise RuntimeError("GPU attempt is not ready for postprocess")
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'POSTPROCESSING', updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s
                  AND status IN ('GPU_SUCCESS', 'POSTPROCESSING')
                """,
                (job_id, attempt_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("GPU attempt postprocess claim was lost")
            snapshot["claim_status"] = "CLAIMED"
            return snapshot


def complete_postprocess(
    job_id: str,
    attempt_id: str,
    result_objects: dict[str, str],
) -> bool:
    """Commit attempt and job success in one database transaction."""
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'SUCCESS', completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s
                  AND status = 'POSTPROCESSING'
                """,
                (job_id, attempt_id),
            )
            if cursor.rowcount != 1:
                return False
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'SUCCESS',
                    result_details_object = %s,
                    result_predictions_object = %s,
                    result_report_object = %s,
                    result_skeleton_object = %s,
                    result_video_object = %s,
                    artifact_validation_status = 'VALID',
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND status = 'PROCESSING'
                """,
                (
                    result_objects["details"], result_objects["predictions"],
                    result_objects["report"], result_objects["skeleton"],
                    result_objects["rendered_video"], job_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Job reached a final state before postprocess completed")
            return True


def fail_gpu_attempt(job_id: str, attempt_id: str, error: Exception) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'FAILED', error_code = %s, error_message = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s
                  AND status IN (
                      'QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING'
                  )
                """,
                (
                    getattr(error, "error_code", type(error).__name__),
                    str(error)[-2000:],
                    job_id,
                    attempt_id,
                ),
            )


def fail_gpu_attempt_and_job(
    job_id: str,
    attempt_id: str,
    error: Exception,
    *,
    artifact_invalid: bool = False,
) -> bool:
    """Atomically fail an active attempt and its non-final parent job."""
    error_code = getattr(error, "error_code", type(error).__name__)
    error_message = str(error)[-2000:]
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'FAILED', error_code = %s, error_message = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s
                  AND status IN ('QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING')
                """,
                (error_code, error_message, job_id, attempt_id),
            )
            if cursor.rowcount != 1:
                return False
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'FAILED', error_code = %s, error_message = %s,
                    artifact_validation_status = CASE
                        WHEN %s THEN 'INVALID' ELSE artifact_validation_status
                    END,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND status IN ('QUEUED', 'PROCESSING')
                """,
                (error_code, error_message, artifact_invalid, job_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Job reached a final state before attempt failed")
            return True


def mark_job_processing(
    job_id: str,
    *,
    model_id: str,
    model_release: str,
) -> bool:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'PROCESSING',
                    started_at = COALESCE(started_at, NOW()),
                    completed_at = NULL,
                    error_code = NULL,
                    error_message = NULL,
                    model_id = %s,
                    model_release = %s,
                    artifact_validation_status = NULL,
                    updated_at = NOW()
                WHERE job_id = %s AND status IN ('QUEUED', 'PROCESSING')
                """,
                (model_id, model_release, job_id),
            )
            return cursor.rowcount == 1


def mark_job_success(
    job_id: str,
    result_objects: dict[str, str],
) -> bool:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'SUCCESS',
                    result_details_object = %s,
                    result_predictions_object = %s,
                    result_report_object = %s,
                    result_skeleton_object = %s,
                    result_video_object = %s,
                    artifact_validation_status = 'VALID',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s AND status = 'PROCESSING'
                """,
                (
                    result_objects["details"],
                    result_objects["predictions"],
                    result_objects["report"],
                    result_objects["skeleton"],
                    result_objects["rendered_video"],
                    job_id,
                ),
            )
            return cursor.rowcount == 1


def mark_job_failed(
    job_id: str,
    error: Exception,
    *,
    artifact_invalid: bool = False,
) -> bool:
    error_message = str(error)[-2000:]

    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'FAILED',
                    error_code = %s,
                    error_message = %s,
                    artifact_validation_status = CASE
                        WHEN %s THEN 'INVALID'
                        ELSE artifact_validation_status
                    END,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s AND status IN ('QUEUED', 'PROCESSING')
                """,
                (
                    type(error).__name__,
                    error_message,
                    artifact_invalid,
                    job_id,
                ),
            )
            return cursor.rowcount == 1


def initialize_job_stages(
    job_id: str,
    stages: tuple[tuple[int, str], ...],
) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO inference_job_stages (
                    job_id,
                    stage_key,
                    stage_order,
                    status
                )
                VALUES (%s, %s, %s, 'PENDING')
                ON CONFLICT (job_id, stage_key)
                DO UPDATE SET
                    stage_order = EXCLUDED.stage_order,
                    status = 'PENDING',
                    started_at = NULL,
                    completed_at = NULL,
                    duration_seconds = NULL,
                    error_code = NULL,
                    updated_at = NOW()
                """,
                [
                    (job_id, stage_key, stage_order)
                    for stage_order, stage_key in stages
                ],
            )


def mark_job_stage_running(job_id: str, stage_key: str) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_job_stages
                SET status = 'RUNNING',
                    started_at = NOW(),
                    completed_at = NULL,
                    duration_seconds = NULL,
                    error_code = NULL,
                    updated_at = NOW()
                WHERE job_id = %s
                  AND stage_key = %s
                """,
                (job_id, stage_key),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    f"Unknown job stage: {job_id}/{stage_key}"
                )


def mark_job_stage_finished(
    job_id: str,
    stage_key: str,
    *,
    status: str,
    duration_seconds: float,
    error_code: str | None = None,
) -> None:
    if status not in FINISHED_STAGE_STATUSES:
        raise ValueError(f"Invalid finished stage status: {status}")
    if duration_seconds < 0:
        raise ValueError("Stage duration must not be negative")

    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_job_stages
                SET status = %s,
                    completed_at = NOW(),
                    duration_seconds = %s,
                    error_code = %s,
                    updated_at = NOW()
                WHERE job_id = %s
                  AND stage_key = %s
                """,
                (
                    status,
                    duration_seconds,
                    error_code,
                    job_id,
                    stage_key,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    f"Unknown job stage: {job_id}/{stage_key}"
                )


def mark_pending_job_stages_skipped(job_id: str) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_job_stages
                SET status = 'SKIPPED',
                    updated_at = NOW()
                WHERE job_id = %s
                  AND status = 'PENDING'
                """,
                (job_id,),
            )
