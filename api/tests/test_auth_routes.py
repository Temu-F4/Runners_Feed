from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from uuid import uuid4

from app.account_identity import KakaoProfile
from app.main import finish_kakao_login


async def run_immediately(function, *args, **kwargs):
    return function(*args, **kwargs)


class KakaoAuthRouteTests(IsolatedAsyncioTestCase):
    async def test_rejects_callback_when_state_cookie_does_not_match(self) -> None:
        request = SimpleNamespace(
            cookies={"__Host-rf_oauth_state": "expected"},
            state=SimpleNamespace(user_id=uuid4()),
        )

        response = await finish_kakao_login(
            request,
            code="authorization-code",
            state="different",
            error=None,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/?login=kakao-error")

    @patch("app.main.create_account_session")
    @patch("app.main.link_kakao_account")
    @patch("app.main.fetch_kakao_profile")
    @patch("app.main.run_in_threadpool", side_effect=run_immediately)
    async def test_callback_links_guest_and_issues_account_cookie(
        self,
        _run_in_threadpool,
        fetch_profile,
        link_account,
        create_session,
    ) -> None:
        guest_user_id = uuid4()
        account_user_id = uuid4()
        request = SimpleNamespace(
            cookies={"__Host-rf_oauth_state": "expected"},
            state=SimpleNamespace(user_id=guest_user_id),
        )
        fetch_profile.return_value = KakaoProfile(
            "123456",
            "runner@example.com",
            "러너",
        )
        link_account.return_value = account_user_id

        response = await finish_kakao_login(
            request,
            code="authorization-code",
            state="expected",
            error=None,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/?login=kakao-success")
        self.assertTrue(request.state.delete_guest_cookie)
        self.assertTrue(request.state.suppress_account_cookie)
        link_account.assert_called_once_with(
            current_user_id=guest_user_id,
            provider_user_id="123456",
            email="runner@example.com",
            display_name="러너",
        )
        self.assertEqual(create_session.call_args.kwargs["user_id"], account_user_id)
        cookies = "\n".join(
            value.decode("latin-1")
            for name, value in response.raw_headers
            if name.lower() == b"set-cookie"
        )
        self.assertIn("__Host-rf_session=", cookies)
        self.assertIn("HttpOnly", cookies)
        self.assertIn("Secure", cookies)
