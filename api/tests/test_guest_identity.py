from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.guest_identity import (
    GUEST_COOKIE_NAME,
    hash_guest_token,
    issue_guest_identity,
    set_guest_cookie,
)


class GuestIdentityTests(TestCase):
    def test_cookie_name_uses_host_prefix(self) -> None:
        self.assertEqual(GUEST_COOKIE_NAME, "__Host-rf_guest")

    def test_hash_is_deterministic_sha256_hex(self) -> None:
        first = hash_guest_token("guest-token")
        second = hash_guest_token("guest-token")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        int(first, 16)
        self.assertNotIn("guest-token", first)

    def test_rejects_empty_or_oversized_token(self) -> None:
        with self.assertRaises(ValueError):
            hash_guest_token("")
        with self.assertRaises(ValueError):
            hash_guest_token("x" * 513)

    @patch.dict("os.environ", {}, clear=True)
    def test_issues_30_day_identity_by_default(self) -> None:
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)

        identity = issue_guest_identity(now=now)

        self.assertEqual(identity.expires_at, now + timedelta(days=30))
        self.assertEqual(identity.max_age_seconds, 30 * 24 * 60 * 60)
        self.assertEqual(identity.token_hash, hash_guest_token(identity.token))

    @patch.dict("os.environ", {"GUEST_SESSION_TTL_DAYS": "7"})
    def test_supports_configured_session_ttl(self) -> None:
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)

        identity = issue_guest_identity(now=now)

        self.assertEqual(identity.expires_at, now + timedelta(days=7))

    @patch.dict("os.environ", {"GUEST_SESSION_TTL_DAYS": "0"})
    def test_rejects_out_of_range_session_ttl(self) -> None:
        with self.assertRaises(ValueError):
            issue_guest_identity()

    def test_rejects_issue_time_without_timezone(self) -> None:
        with self.assertRaises(ValueError):
            issue_guest_identity(now=datetime(2026, 9, 3))

    def test_sets_secure_host_cookie(self) -> None:
        now = datetime(2026, 9, 3, tzinfo=timezone.utc)
        identity = issue_guest_identity(now=now)
        response = MagicMock()

        set_guest_cookie(response, identity)

        response.set_cookie.assert_called_once_with(
            key="__Host-rf_guest",
            value=identity.token,
            max_age=30 * 24 * 60 * 60,
            expires=now + timedelta(days=30),
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
