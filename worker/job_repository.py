import os

import psycopg


FINISHED_STAGE_STATUSES = {
    "SUCCESS",
    "FAILED",
    "WARNING",
}


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def mark_job_processing(job_id: str) -> None:
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
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
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
                    result_video_object = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (
                    result_objects["details"],
                    result_objects["predictions"],
                    result_objects["report"],
                    result_objects["rendered_video"],
                    job_id,
                ),
            )


def mark_job_failed(job_id: str, error: Exception) -> None:
    error_message = str(error)[-2000:]

    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'FAILED',
                    error_code = %s,
                    error_message = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (
                    type(error).__name__,
                    error_message,
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
