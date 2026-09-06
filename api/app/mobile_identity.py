from __future__ import annotations

import hashlib
import os
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


MOBILE_OAUTH_STATE_TTL_SECONDS = 600
MOBILE_EXCHANGE_TTL_SECONDS = 60
MOBILE_APP_REDIRECT_URI_DEFAULT = "runnersfeed://auth/callback"


@dataclass(frozen=True)
class IssuedMobileValue:
    value: str
    value_hash: str
    expires_at: datetime


def _hash(value: str) -> str:
    if not value or len(value) > 512:
        raise ValueError("Invalid mobile authentication value")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_mobile_value(value: str) -> str:
    return _hash(value)


def issue_mobile_state(*, now: datetime | None = None) -> IssuedMobileValue:
    issued_at = now or datetime.now(timezone.utc)
    value = secrets.token_urlsafe(32)
    return IssuedMobileValue(
        value=value,
        value_hash=_hash(value),
        expires_at=issued_at + timedelta(seconds=MOBILE_OAUTH_STATE_TTL_SECONDS),
    )


def issue_mobile_exchange(*, now: datetime | None = None) -> IssuedMobileValue:
    issued_at = now or datetime.now(timezone.utc)
    value = secrets.token_urlsafe(32)
    return IssuedMobileValue(
        value=value,
        value_hash=_hash(value),
        expires_at=issued_at + timedelta(seconds=MOBILE_EXCHANGE_TTL_SECONDS),
    )


def mobile_kakao_redirect_uri() -> str:
    value = os.getenv("KAKAO_MOBILE_REDIRECT_URI", "").strip()
    if not value:
        raise RuntimeError("KAKAO_MOBILE_REDIRECT_URI is not configured")
    return value


def mobile_app_redirect_uri() -> str:
    value = os.getenv(
        "MOBILE_APP_REDIRECT_URI",
        MOBILE_APP_REDIRECT_URI_DEFAULT,
    ).strip()
    parsed = urllib.parse.urlparse(value)
    if not parsed.scheme or parsed.scheme in {"http", "https"}:
        raise RuntimeError("MOBILE_APP_REDIRECT_URI must use an app scheme")
    return value


def mobile_kakao_login_configured() -> bool:
    return bool(
        os.getenv("KAKAO_REST_API_KEY", "").strip()
        and os.getenv("KAKAO_MOBILE_REDIRECT_URI", "").strip()
    )


def mobile_redirect(*, code: str | None = None, error: str | None = None):
    query: dict[str, str] = {}
    if code:
        query["code"] = code
    if error:
        query["error"] = error
    return mobile_app_redirect_uri() + (
        "?" + urllib.parse.urlencode(query) if query else ""
    )
