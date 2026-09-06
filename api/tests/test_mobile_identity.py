from datetime import datetime, timezone
from unittest import TestCase

from app.mobile_identity import (
    MOBILE_EXCHANGE_TTL_SECONDS,
    MOBILE_OAUTH_STATE_TTL_SECONDS,
    hash_mobile_value,
    issue_mobile_exchange,
    issue_mobile_state,
)


class MobileIdentityTests(TestCase):
    def test_state_and_exchange_are_random_and_hashed(self) -> None:
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        state = issue_mobile_state(now=now)
        exchange = issue_mobile_exchange(now=now)

        self.assertNotEqual(state.value, exchange.value)
        self.assertEqual(state.value_hash, hash_mobile_value(state.value))
        self.assertEqual(exchange.value_hash, hash_mobile_value(exchange.value))
        self.assertEqual(
            (state.expires_at - now).total_seconds(),
            MOBILE_OAUTH_STATE_TTL_SECONDS,
        )
        self.assertEqual(
            (exchange.expires_at - now).total_seconds(),
            MOBILE_EXCHANGE_TTL_SECONDS,
        )

    def test_mobile_values_are_not_stored_as_plaintext_hashes(self) -> None:
        value = issue_mobile_state().value
        digest = hash_mobile_value(value)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(value, digest)
