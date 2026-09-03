CREATE TABLE IF NOT EXISTS inference_job_stages (
    job_id UUID NOT NULL
        REFERENCES inference_jobs(job_id) ON DELETE CASCADE,
    stage_key VARCHAR(32) NOT NULL,
    stage_order SMALLINT NOT NULL CHECK (stage_order > 0),
    status VARCHAR(16) NOT NULL
        CHECK (status IN (
            'PENDING',
            'RUNNING',
            'SUCCESS',
            'FAILED',
            'WARNING',
            'SKIPPED'
        )),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION
        CHECK (duration_seconds >= 0),
    error_code TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, stage_key)
);

CREATE INDEX IF NOT EXISTS inference_job_stages_job_order_idx
ON inference_job_stages (job_id, stage_order);
