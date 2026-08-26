import os

import psycopg


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
                    result_video_object = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (
                    result_objects["details"],
                    result_objects["predictions"],
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
