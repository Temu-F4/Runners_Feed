import sys
from types import ModuleType
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

psycopg_module = ModuleType("psycopg")
psycopg_module.connect = MagicMock()
psycopg_rows_module = ModuleType("psycopg.rows")
psycopg_rows_module.dict_row = object()
sys.modules.setdefault("psycopg", psycopg_module)
sys.modules.setdefault("psycopg.rows", psycopg_rows_module)

from app.database import (
    create_guest_session,
    create_job,
    find_active_guest_user,
    get_job,
)


VALID_TOKEN_HASH = "a" * 64


class GuestSessionDatabaseTests(TestCase):
    def setUp(self) -> None:
        database_url = patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql://test"},
        )
        database_url.start()
        self.addCleanup(database_url.stop)

    @patch("app.database.psycopg.connect")
    def test_create_guest_session_returns_user_id(self, connect) -> None:
        expires_at = datetime(2026, 10, 1, tzinfo=timezone.utc)

        user_id = create_guest_session(
            token_hash=VALID_TOKEN_HASH,
            expires_at=expires_at,
        )

        self.assertIsInstance(user_id, UUID)
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        self.assertEqual(cursor.execute.call_count, 2)

    @patch("app.database.psycopg.connect")
    def test_find_active_guest_user_returns_database_user(self, connect) -> None:
        expected_user_id = uuid4()
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (expected_user_id,)

        actual_user_id = find_active_guest_user(VALID_TOKEN_HASH)

        self.assertEqual(actual_user_id, expected_user_id)

    @patch("app.database.psycopg.connect")
    def test_find_active_guest_user_returns_none_when_missing(self, connect) -> None:
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        self.assertIsNone(find_active_guest_user(VALID_TOKEN_HASH))

    @patch("app.database.psycopg.connect")
    def test_rejects_invalid_token_hash_before_database_access(self, connect) -> None:
        with self.assertRaises(ValueError):
            find_active_guest_user("not-a-sha256-hash")

        connect.assert_not_called()

    @patch("app.database.psycopg.connect")
    def test_rejects_expiry_without_timezone(self, connect) -> None:
        with self.assertRaises(ValueError):
            create_guest_session(
                token_hash=VALID_TOKEN_HASH,
                expires_at=datetime(2026, 10, 1),
            )

        connect.assert_not_called()

    @patch("app.database.psycopg.connect")
    def test_create_job_persists_owner_and_height(self, connect) -> None:
        user_id = uuid4()

        create_job(
            job_id="8e9f1ecb-7181-46ee-a8d4-243f5af650da",
            case_id="case-1",
            input_object_name="uploads/input.mp4",
            user_id=user_id,
            height_snapshot_m=1.78,
        )

        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        query, parameters = cursor.execute.call_args.args
        self.assertIn("user_id", query)
        self.assertIn("height_snapshot_m", query)
        self.assertEqual(parameters[-2:], (user_id, 1.78))

    @patch("app.database.psycopg.connect")
    def test_get_job_scopes_query_to_owner(self, connect) -> None:
        user_id = uuid4()
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        result = get_job(
            job_id="8e9f1ecb-7181-46ee-a8d4-243f5af650da",
            user_id=user_id,
        )

        self.assertIsNone(result)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("AND user_id = %s", query)
        self.assertEqual(
            parameters,
            ("8e9f1ecb-7181-46ee-a8d4-243f5af650da", user_id),
        )
