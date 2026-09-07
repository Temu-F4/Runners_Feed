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


def create_gpu_attempt(job_id: str) -> dict[str, Any]:
    """Atomically create the only active GPU attempt for one service job."""
    attempt_id = str(uuid4())
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT job_id FROM inference_jobs WHERE job_id = %s FOR UPDATE",
                (job_id,),
            )
            if cursor.fetchone() is None:
                raise LookupError(f"Unknown job: {job_id}")
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
    return {"attempt_id": attempt_id, "attempt_number": attempt_number}


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
                SET status = 'SUCCESS', manifest_object = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s AND status = 'RUNNING'
                """,
                (manifest_object, job_id, attempt_id),
            )
            return cursor.rowcount == 1


def fail_gpu_attempt(job_id: str, attempt_id: str, error: Exception) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_gpu_attempts
                SET status = 'FAILED', error_code = %s, error_message = %s,
                    completed_at = NOW(), updated_at = NOW()
                WHERE job_id = %s AND attempt_id = %s
                  AND status IN ('QUEUED', 'RUNNING')
                """,
                (type(error).__name__, str(error)[-2000:], job_id, attempt_id),
            )


def get_successful_gpu_attempt(job_id: str, attempt_id: str, manifest_object: str) -> dict[str, Any]:
    """Return the postprocess snapshot only for the accepted successful attempt."""
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT jobs.job_id, jobs.case_id, jobs.input_object_name,
                       jobs.input_size_bytes, jobs.input_etag,
                       jobs.height_snapshot_m, jobs.model_id, jobs.model_release
                FROM inference_jobs AS jobs
                JOIN inference_gpu_attempts AS attempts
                  ON attempts.job_id = jobs.job_id
                WHERE jobs.job_id = %s
                  AND attempts.attempt_id = %s
                  AND attempts.status = 'SUCCESS'
                  AND attempts.manifest_object = %s
                  AND jobs.status = 'PROCESSING'
                """,
                (job_id, attempt_id, manifest_object),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("GPU attempt is not the accepted postprocess input")
            return dict(zip(
                ("job_id", "case_id", "input_object_name", "input_size_bytes",
                 "input_etag", "height_snapshot_m", "model_id", "model_release"),
                row,
            ))


def mark_job_processing(
    job_id: str,
    *,
    model_id: str,
    model_release: str,
) -> None:
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
                WHERE job_id = %s
                """,
                (model_id, model_release, job_id),
            )


def mark_job_success(
    job_id: str,
    result_objects: dict[str, str],
) -> None:
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
                WHERE job_id = %s
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


def mark_job_failed(
    job_id: str,
    error: Exception,
    *,
    artifact_invalid: bool = False,
) -> None:
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
                WHERE job_id = %s
                """,
                (
                    type(error).__name__,
                    error_message,
                    artifact_invalid,
                    job_id,
                ),
            )


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
