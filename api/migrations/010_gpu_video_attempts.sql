ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS input_size_bytes BIGINT CHECK (input_size_bytes > 0);

ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS input_etag TEXT;

CREATE TABLE IF NOT EXISTS inference_gpu_attempts (
    attempt_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES inference_jobs(job_id) ON DELETE CASCADE,
    attempt_number SMALLINT NOT NULL CHECK (attempt_number > 0),
    status VARCHAR(16) NOT NULL CHECK (status IN (
        'QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING',
        'SUCCESS', 'FAILED'
    )),
    remote_job_id TEXT,
    manifest_object TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, attempt_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS inference_gpu_attempts_one_active_idx
ON inference_gpu_attempts (job_id)
WHERE status IN ('QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING');
