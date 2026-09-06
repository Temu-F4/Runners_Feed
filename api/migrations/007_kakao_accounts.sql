CREATE TABLE IF NOT EXISTS oauth_identities (
    provider VARCHAR(32) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL
        REFERENCES app_users(user_id) ON DELETE CASCADE,
    email TEXT,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, provider_user_id),
    UNIQUE (provider, user_id)
);

CREATE TABLE IF NOT EXISTS account_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES app_users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS account_sessions_user_idx
ON account_sessions (user_id);

CREATE INDEX IF NOT EXISTS account_sessions_expiry_idx
ON account_sessions (expires_at);
