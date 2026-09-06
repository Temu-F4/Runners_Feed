import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.account_identity import (
    ACCOUNT_COOKIE_NAME,
    KakaoProfile,
    fetch_kakao_profile,
    hash_account_token,
    issue_account_identity,
    kakao_authorization_url,
    kakao_login_configured,
    set_account_cookie,
)


class AccountIdentityTests(TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_login_is_disabled_until_required_settings_exist(self) -> None:
        self.assertFalse(kakao_login_configured())

    @patch.dict(
        "os.environ",
        {"KAKAO_REST_API_KEY": "key", "KAKAO_REDIRECT_URI": "https://example.com/callback"},
        clear=True,
    )
    def test_login_is_enabled_when_required_settings_exist(self) -> None:
        self.assertTrue(kakao_login_configured())

    def test_account_token_is_hashed_and_never_stored_raw(self) -> None:
        digest = hash_account_token("account-token")
        self.assertEqual(len(digest), 64)
        self.assertNotIn("account-token", digest)

    @patch.dict("os.environ", {"ACCOUNT_SESSION_TTL_DAYS": "30"})
    def test_issues_30_day_account_session(self) -> None:
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        identity = issue_account_identity(now=now)
        self.assertEqual(identity.expires_at, now + timedelta(days=30))
        self.assertEqual(identity.token_hash, hash_account_token(identity.token))

    def test_sets_secure_account_cookie(self) -> None:
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        identity = issue_account_identity(now=now)
        response = MagicMock()
        set_account_cookie(response, identity)
        response.set_cookie.assert_called_once_with(
            key=ACCOUNT_COOKIE_NAME,
            value=identity.token,
            max_age=30 * 24 * 60 * 60,
            expires=identity.expires_at,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )

    @patch.dict(
        "os.environ",
        {
            "KAKAO_REST_API_KEY": "rest-key",
            "KAKAO_REDIRECT_URI": "https://example.com/api/auth/kakao/callback",
        },
        clear=True,
    )
    def test_authorization_url_contains_state_and_exact_redirect(self) -> None:
        url = kakao_authorization_url("csrf-state")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["client_id"], ["rest-key"])
        self.assertEqual(query["state"], ["csrf-state"])
        self.assertEqual(
            query["redirect_uri"],
            ["https://example.com/api/auth/kakao/callback"],
        )

    @patch.dict(
        "os.environ",
        {
            "KAKAO_REST_API_KEY": "rest-key",
            "KAKAO_REDIRECT_URI": "https://example.com/api/auth/kakao/callback",
        },
        clear=True,
    )
    @patch("app.account_identity._json_request")
    def test_fetches_kakao_identity_without_persisting_token(self, request) -> None:
        request.side_effect = [
            {"access_token": "temporary-access-token"},
            {
                "id": 123456,
                "kakao_account": {
                    "email": "runner@example.com",
                    "profile": {"nickname": "러너"},
                },
            },
        ]
        self.assertEqual(
            fetch_kakao_profile("authorization-code"),
            KakaoProfile("123456", "runner@example.com", "러너"),
        )
        profile_request = request.call_args_list[1].args[0]
        self.assertEqual(
            profile_request.headers["Authorization"],
            "Bearer temporary-access-token",
        )
