import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


CREATE_APP_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_users (
    user_id UUID PRIMARY KEY,
    user_type VARCHAR(16) NOT NULL
        CHECK (user_type IN ('guest', 'account')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

CREATE_GUEST_SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS guest_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES app_users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

CREATE_JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS inference_jobs (
    job_id UUID PRIMARY KEY,
    case_id VARCHAR(64) NOT NULL,
    input_object_name TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('QUEUED', 'PROCESSING', 'SUCCESS', 'FAILED')),
    result_details_object TEXT,
    result_predictions_object TEXT,
    result_report_object TEXT,
    result_video_object TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

CREATE_JOBS_STATUS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS inference_jobs_status_created_idx
ON inference_jobs (status, created_at DESC)
"""

ADD_REPORT_COLUMN_SQL = """
ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS result_report_object TEXT
"""

ADD_JOB_USER_COLUMN_SQL = """
ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS user_id UUID
    REFERENCES app_users(user_id) ON DELETE SET NULL
"""

ADD_JOB_HEIGHT_COLUMN_SQL = """
ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS height_snapshot_m DOUBLE PRECISION
    CHECK (
        height_snapshot_m IS NULL
        OR height_snapshot_m BETWEEN 0.5 AND 2.5
    )
"""

CREATE_JOBS_USER_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS inference_jobs_user_created_idx
ON inference_jobs (user_id, created_at DESC)
"""


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def initialize_database() -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_APP_USERS_TABLE_SQL)
            cursor.execute(CREATE_GUEST_SESSIONS_TABLE_SQL)
            cursor.execute(CREATE_JOBS_TABLE_SQL)
            cursor.execute(ADD_REPORT_COLUMN_SQL)
            cursor.execute(ADD_JOB_USER_COLUMN_SQL)
            cursor.execute(ADD_JOB_HEIGHT_COLUMN_SQL)
            cursor.execute(CREATE_JOBS_STATUS_INDEX_SQL)
            cursor.execute(CREATE_JOBS_USER_INDEX_SQL)


def create_job(
    job_id: str,
    case_id: str,
    input_object_name: str,
) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO inference_jobs (
                    job_id,
                    case_id,
                    input_object_name,
                    status
                )
                VALUES (%s, %s, %s, 'QUEUED')
                """,
                (job_id, case_id, input_object_name),
            )


def mark_job_dispatch_failed(job_id: str) -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE inference_jobs
                SET status = 'FAILED',
                    error_code = 'dispatch_failed',
                    error_message = 'Failed to dispatch inference task',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )


def get_job(job_id: str) -> dict[str, Any] | None:
    with psycopg.connect(
        _database_url(),
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id,
                       case_id,
                       input_object_name,
                       status,
                       result_details_object,
                       result_predictions_object,
                       result_report_object,
                       result_video_object,
                       error_code,
                       created_at,
                       started_at,
                       completed_at,
                       updated_at
                FROM inference_jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            return cursor.fetchone()
