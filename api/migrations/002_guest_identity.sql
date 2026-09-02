CREATE TABLE IF NOT EXISTS app_users (
    user_id UUID PRIMARY KEY,
    user_type VARCHAR(16) NOT NULL
        CHECK (user_type IN ('guest', 'account')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guest_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES app_users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS user_id UUID
    REFERENCES app_users(user_id) ON DELETE SET NULL;

ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS height_snapshot_m DOUBLE PRECISION
    CHECK (
        height_snapshot_m IS NULL
        OR height_snapshot_m BETWEEN 0.5 AND 2.5
    );

CREATE INDEX IF NOT EXISTS inference_jobs_user_created_idx
ON inference_jobs (user_id, created_at DESC);
