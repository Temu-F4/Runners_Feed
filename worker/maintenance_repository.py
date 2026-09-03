from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def _rows(query: str, parameters: tuple, limit: int) -> list[dict[str, Any]]:
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (*parameters, limit))
            return list(cursor.fetchall())


def list_expired_inputs(cutoff: datetime, limit: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT job_id, input_object_name
        FROM inference_jobs
        WHERE input_object_name IS NOT NULL
          AND created_at < %s
        ORDER BY created_at
        LIMIT %s
        """,
        (cutoff,),
        limit,
    )


def clear_input_object(job_id: UUID) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET input_object_name = NULL,
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )


def list_expired_transient_results(
    cutoff: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT job_id,
               result_details_object,
               result_predictions_object,
               result_video_object
        FROM inference_jobs
        WHERE completed_at < %s
          AND (
              result_details_object IS NOT NULL
              OR result_predictions_object IS NOT NULL
              OR result_video_object IS NOT NULL
          )
        ORDER BY completed_at
        LIMIT %s
        """,
        (cutoff,),
        limit,
    )


def clear_transient_result_objects(job_id: UUID) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET result_details_object = NULL,
                    result_predictions_object = NULL,
                    result_video_object = NULL,
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )


def list_expired_failed_jobs(cutoff: datetime, limit: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT job_id
        FROM inference_jobs
        WHERE status = 'FAILED'
          AND completed_at < %s
        ORDER BY completed_at
        LIMIT %s
        """,
        (cutoff,),
        limit,
    )


def list_inactive_guest_users(cutoff: datetime, limit: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT users.user_id
        FROM app_users AS users
        WHERE users.user_type = 'guest'
          AND NOT EXISTS (
              SELECT 1
              FROM guest_sessions AS sessions
              WHERE sessions.user_id = users.user_id
                AND sessions.last_seen_at >= %s
          )
        ORDER BY users.updated_at
        LIMIT %s
        """,
        (cutoff,),
        limit,
    )


def list_user_artifacts(user_id: UUID) -> list[dict[str, Any]]:
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT input_object_name,
                       result_details_object,
                       result_predictions_object,
                       result_report_object,
                       result_skeleton_object,
                       result_video_object
                FROM inference_jobs
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return list(cursor.fetchall())


def delete_user(user_id: UUID) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM inference_jobs WHERE user_id = %s",
                (user_id,),
            )
            cursor.execute(
                "DELETE FROM app_users WHERE user_id = %s",
                (user_id,),
            )
