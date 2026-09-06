import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


GUEST_COOKIE_NAME = "__Host-rf_guest"
DEFAULT_GUEST_SESSION_TTL_DAYS = 365
MIN_GUEST_SESSION_TTL_DAYS = 1
MAX_GUEST_SESSION_TTL_DAYS = 365
MAX_GUEST_TOKEN_LENGTH = 512


@dataclass(frozen=True)
class IssuedGuestIdentity:
    token: str
    token_hash: str
    expires_at: datetime
    max_age_seconds: int


def guest_session_ttl_days() -> int:
    ttl_days = int(
        os.getenv(
            "GUEST_SESSION_TTL_DAYS",
            str(DEFAULT_GUEST_SESSION_TTL_DAYS),
        )
    )
    if not MIN_GUEST_SESSION_TTL_DAYS <= ttl_days <= MAX_GUEST_SESSION_TTL_DAYS:
        raise ValueError(
            "GUEST_SESSION_TTL_DAYS must be between 1 and 365"
        )
    return ttl_days


def hash_guest_token(token: str) -> str:
    if not token or len(token) > MAX_GUEST_TOKEN_LENGTH:
        raise ValueError("Invalid guest token")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_guest_identity(
    *,
    now: datetime | None = None,
) -> IssuedGuestIdentity:
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("Guest identity issue time must include a timezone")

    ttl_days = guest_session_ttl_days()
    max_age_seconds = int(timedelta(days=ttl_days).total_seconds())
    token = secrets.token_urlsafe(32)

    return IssuedGuestIdentity(
        token=token,
        token_hash=hash_guest_token(token),
        expires_at=issued_at + timedelta(days=ttl_days),
        max_age_seconds=max_age_seconds,
    )


def renew_guest_identity(
    token: str,
    *,
    now: datetime | None = None,
) -> IssuedGuestIdentity:
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("Guest identity renewal time must include a timezone")

    ttl_days = guest_session_ttl_days()
    max_age_seconds = int(timedelta(days=ttl_days).total_seconds())
    return IssuedGuestIdentity(
        token=token,
        token_hash=hash_guest_token(token),
        expires_at=issued_at + timedelta(days=ttl_days),
        max_age_seconds=max_age_seconds,
    )


def set_guest_cookie(response, identity: IssuedGuestIdentity) -> None:
    response.set_cookie(
        key=GUEST_COOKIE_NAME,
        value=identity.token,
        max_age=identity.max_age_seconds,
        expires=identity.expires_at,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
