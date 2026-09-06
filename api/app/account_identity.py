import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


ACCOUNT_COOKIE_NAME = "__Host-rf_session"
OAUTH_STATE_COOKIE_NAME = "__Host-rf_oauth_state"
DEFAULT_ACCOUNT_SESSION_TTL_DAYS = 30
OAUTH_STATE_TTL_SECONDS = 600
MAX_SESSION_TOKEN_LENGTH = 512
KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_URL = "https://kapi.kakao.com/v2/user/me"


@dataclass(frozen=True)
class IssuedAccountIdentity:
    token: str
    token_hash: str
    expires_at: datetime
    max_age_seconds: int


@dataclass(frozen=True)
class KakaoProfile:
    provider_user_id: str
    email: str | None
    display_name: str | None


def _required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def kakao_login_configured() -> bool:
    return bool(
        os.getenv("KAKAO_REST_API_KEY", "").strip()
        and os.getenv("KAKAO_REDIRECT_URI", "").strip()
    )


def hash_account_token(token: str) -> str:
    if not token or len(token) > MAX_SESSION_TOKEN_LENGTH:
        raise ValueError("Invalid account session token")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def account_session_ttl_days() -> int:
    value = int(
        os.getenv(
            "ACCOUNT_SESSION_TTL_DAYS",
            str(DEFAULT_ACCOUNT_SESSION_TTL_DAYS),
        )
    )
    if not 1 <= value <= 90:
        raise ValueError("ACCOUNT_SESSION_TTL_DAYS must be between 1 and 90")
    return value


def issue_account_identity(
    *, now: datetime | None = None
) -> IssuedAccountIdentity:
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("Account identity issue time must include a timezone")
    ttl_days = account_session_ttl_days()
    max_age_seconds = int(timedelta(days=ttl_days).total_seconds())
    token = secrets.token_urlsafe(32)
    return IssuedAccountIdentity(
        token=token,
        token_hash=hash_account_token(token),
        expires_at=issued_at + timedelta(days=ttl_days),
        max_age_seconds=max_age_seconds,
    )


def renew_account_identity(
    token: str, *, now: datetime | None = None
) -> IssuedAccountIdentity:
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("Account identity renewal time must include a timezone")
    ttl_days = account_session_ttl_days()
    max_age_seconds = int(timedelta(days=ttl_days).total_seconds())
    return IssuedAccountIdentity(
        token=token,
        token_hash=hash_account_token(token),
        expires_at=issued_at + timedelta(days=ttl_days),
        max_age_seconds=max_age_seconds,
    )


def set_account_cookie(response, identity: IssuedAccountIdentity) -> None:
    response.set_cookie(
        key=ACCOUNT_COOKIE_NAME,
        value=identity.token,
        max_age=identity.max_age_seconds,
        expires=identity.expires_at,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def set_oauth_state_cookie(response, state: str) -> None:
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=OAUTH_STATE_TTL_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def kakao_authorization_url(
    state: str,
    *,
    redirect_uri: str | None = None,
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": _required_setting("KAKAO_REST_API_KEY"),
            "redirect_uri": redirect_uri
            or _required_setting("KAKAO_REDIRECT_URI"),
            "response_type": "code",
            "state": state,
        }
    )
    return f"{KAKAO_AUTHORIZE_URL}?{query}"


def _json_request(
    request: urllib.request.Request,
    *, timeout: float = 10.0,
) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("Kakao authentication request failed") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Kakao authentication returned an invalid response")
    return payload


def fetch_kakao_profile(
    code: str,
    *,
    redirect_uri: str | None = None,
) -> KakaoProfile:
    token_fields = {
        "grant_type": "authorization_code",
        "client_id": _required_setting("KAKAO_REST_API_KEY"),
        "redirect_uri": redirect_uri
        or _required_setting("KAKAO_REDIRECT_URI"),
        "code": code,
    }
    client_secret = os.getenv("KAKAO_CLIENT_SECRET", "").strip()
    if client_secret:
        token_fields["client_secret"] = client_secret
    token_request = urllib.request.Request(
        KAKAO_TOKEN_URL,
        data=urllib.parse.urlencode(token_fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token_payload = _json_request(token_request)
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Kakao did not return an access token")

    profile_request = urllib.request.Request(
        KAKAO_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    payload = _json_request(profile_request)
    provider_user_id = payload.get("id")
    if not isinstance(provider_user_id, (str, int)):
        raise RuntimeError("Kakao did not return a user identifier")
    account = payload.get("kakao_account")
    account = account if isinstance(account, dict) else {}
    profile = account.get("profile")
    profile = profile if isinstance(profile, dict) else {}
    email = account.get("email")
    display_name = profile.get("nickname")
    return KakaoProfile(
        provider_user_id=str(provider_user_id),
        email=email if isinstance(email, str) else None,
        display_name=display_name if isinstance(display_name, str) else None,
    )
