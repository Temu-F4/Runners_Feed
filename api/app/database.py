import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

CREATE_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def _validate_token_hash(token_hash: str) -> None:
    if len(token_hash) != 64:
        raise ValueError("Guest token hash must be 64 hexadecimal characters")

    try:
        int(token_hash, 16)
    except ValueError as error:
        raise ValueError(
            "Guest token hash must be 64 hexadecimal characters"
        ) from error


def initialize_database() -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("runners_feed_schema_migrations",),
            )
            cursor.execute(CREATE_SCHEMA_MIGRATIONS_SQL)
            cursor.execute("SELECT version FROM schema_migrations")
            applied_versions = {
                row[0]
                for row in cursor.fetchall()
            }

            migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
            if not migration_paths:
                raise RuntimeError(
                    f"No database migrations found in {MIGRATIONS_DIR}"
                )

            for migration_path in migration_paths:
                version = migration_path.name
                if version in applied_versions:
                    continue

                cursor.execute(
                    migration_path.read_text(encoding="utf-8")
                )
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )


def create_guest_session(
    *,
    token_hash: str,
    expires_at: datetime,
) -> UUID:
    _validate_token_hash(token_hash)
    if expires_at.tzinfo is None:
        raise ValueError("Guest session expiry must include a timezone")

    user_id = uuid4()

    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app_users (user_id, user_type)
                VALUES (%s, 'guest')
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO guest_sessions (
                    token_hash,
                    user_id,
                    expires_at
                )
                VALUES (%s, %s, %s)
                """,
                (token_hash, user_id, expires_at),
            )

    return user_id


def find_active_guest_user(token_hash: str) -> UUID | None:
    _validate_token_hash(token_hash)

    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id
                FROM guest_sessions
                WHERE token_hash = %s
                  AND expires_at > NOW()
                """,
                (token_hash,),
            )
            row = cursor.fetchone()

    return row[0] if row is not None else None


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
