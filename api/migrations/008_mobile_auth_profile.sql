ALTER TABLE app_users
ADD COLUMN IF NOT EXISTS profile_height_m DOUBLE PRECISION
CHECK (
    profile_height_m IS NULL
    OR profile_height_m BETWEEN 0.5 AND 2.5
);

CREATE TABLE IF NOT EXISTS mobile_oauth_transactions (
    state_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES app_users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS mobile_oauth_transactions_expiry_idx
ON mobile_oauth_transactions (expires_at);

CREATE TABLE IF NOT EXISTS mobile_auth_exchanges (
    code_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES app_users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS mobile_auth_exchanges_expiry_idx
ON mobile_auth_exchanges (expires_at);
