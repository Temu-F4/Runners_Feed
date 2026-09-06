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
    create_account_session,
    create_guest_session,
    create_job,
    delete_user_data,
    find_active_guest_user,
    get_job,
    list_jobs,
    list_user_artifacts,
    link_kakao_account,
    renew_active_account_session,
    renew_active_guest_session,
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
    def test_renew_active_guest_session_updates_expiry_and_activity(
        self,
        connect,
    ) -> None:
        expected_user_id = uuid4()
        expires_at = datetime(2027, 9, 3, tzinfo=timezone.utc)
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (expected_user_id,)

        actual_user_id = renew_active_guest_session(
            token_hash=VALID_TOKEN_HASH,
            expires_at=expires_at,
        )

        self.assertEqual(actual_user_id, expected_user_id)
        session_query, session_parameters = cursor.execute.call_args_list[0].args
        self.assertIn("last_seen_at = NOW()", session_query)
        self.assertEqual(session_parameters, (expires_at, VALID_TOKEN_HASH))
        user_query, user_parameters = cursor.execute.call_args_list[1].args
        self.assertIn("updated_at = NOW()", user_query)
        self.assertEqual(user_parameters, (expected_user_id,))

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

    @patch("app.database.psycopg.connect")
    def test_list_jobs_returns_only_owner_rows_in_recent_order(
        self,
        connect,
    ) -> None:
        user_id = uuid4()
        expected_jobs = [{"job_id": uuid4(), "status": "SUCCESS"}]
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = expected_jobs

        result = list_jobs(user_id=user_id, limit=20)

        self.assertEqual(result, expected_jobs)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE user_id = %s", query)
        self.assertIn("ORDER BY created_at DESC", query)
        self.assertIn("LIMIT %s", query)
        self.assertEqual(parameters, (user_id, 20))

    @patch("app.database.psycopg.connect")
    def test_list_jobs_rejects_invalid_limit_before_database_access(
        self,
        connect,
    ) -> None:
        with self.assertRaises(ValueError):
            list_jobs(user_id=uuid4(), limit=51)

        connect.assert_not_called()

    @patch("app.database.psycopg.connect")
    def test_lists_all_artifacts_for_one_user(self, connect) -> None:
        user_id = uuid4()
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{"result_report_object": "report.json"}]

        result = list_user_artifacts(user_id)

        self.assertEqual(result, [{"result_report_object": "report.json"}])
        query, parameters = cursor.execute.call_args.args
        self.assertIn("result_skeleton_object", query)
        self.assertEqual(parameters, (user_id,))

    @patch("app.database.psycopg.connect")
    def test_deletes_jobs_before_user(self, connect) -> None:
        user_id = uuid4()

        delete_user_data(user_id)

        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertIn("DELETE FROM inference_jobs", cursor.execute.call_args_list[0].args[0])
        self.assertIn("DELETE FROM app_users", cursor.execute.call_args_list[1].args[0])

    @patch("app.database.psycopg.connect")
    def test_creates_hashed_account_session(self, connect) -> None:
        user_id = uuid4()
        expires_at = datetime(2026, 10, 6, tzinfo=timezone.utc)

        create_account_session(
            token_hash=VALID_TOKEN_HASH,
            user_id=user_id,
            expires_at=expires_at,
        )

        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        _, parameters = cursor.execute.call_args.args
        self.assertEqual(parameters, (VALID_TOKEN_HASH, user_id, expires_at))

    @patch("app.database.psycopg.connect")
    def test_renews_account_session_and_returns_kakao_identity(self, connect) -> None:
        user_id = uuid4()
        expires_at = datetime(2026, 10, 6, tzinfo=timezone.utc)
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {"user_id": user_id},
            {
                "user_id": user_id,
                "provider": "kakao",
                "email": None,
                "display_name": "러너",
            },
        ]

        account = renew_active_account_session(
            token_hash=VALID_TOKEN_HASH,
            expires_at=expires_at,
        )

        self.assertEqual(account["display_name"], "러너")
        self.assertEqual(cursor.execute.call_count, 3)

    @patch("app.database.psycopg.connect")
    def test_existing_kakao_login_moves_guest_jobs_to_account(self, connect) -> None:
        guest_user_id = uuid4()
        account_user_id = uuid4()
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {"user_id": guest_user_id, "user_type": "guest"},
            {"user_id": account_user_id},
        ]

        result = link_kakao_account(
            current_user_id=guest_user_id,
            provider_user_id="123456",
            email="runner@example.com",
            display_name="러너",
        )

        self.assertEqual(result, account_user_id)
        queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any("UPDATE inference_jobs" in query for query in queries))
        self.assertTrue(any("DELETE FROM guest_sessions" in query for query in queries))

    @patch("app.database.psycopg.connect")
    def test_first_kakao_login_converts_guest_without_moving_jobs(self, connect) -> None:
        guest_user_id = uuid4()
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {"user_id": guest_user_id, "user_type": "guest"},
            None,
        ]

        result = link_kakao_account(
            current_user_id=guest_user_id,
            provider_user_id="123456",
            email=None,
            display_name="러너",
        )

        self.assertEqual(result, guest_user_id)
        queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any("SET user_type = 'account'" in query for query in queries))
        self.assertTrue(any("INSERT INTO oauth_identities" in query for query in queries))
        self.assertFalse(any("UPDATE inference_jobs" in query for query in queries))

    @patch("app.database.psycopg.connect")
    def test_logged_in_account_cannot_merge_a_different_account(self, connect) -> None:
        current_user_id = uuid4()
        other_user_id = uuid4()
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {"user_id": current_user_id, "user_type": "account"},
            {"user_id": other_user_id},
        ]

        with self.assertRaises(ValueError):
            link_kakao_account(
                current_user_id=current_user_id,
                provider_user_id="other-kakao-id",
                email=None,
                display_name=None,
            )

        queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any("UPDATE inference_jobs" in query for query in queries))
