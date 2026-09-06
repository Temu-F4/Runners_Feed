ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS model_id VARCHAR(64);

ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS model_release VARCHAR(128);

ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS artifact_validation_status VARCHAR(16)
CHECK (
    artifact_validation_status IS NULL
    OR artifact_validation_status IN ('VALID', 'INVALID')
);

CREATE INDEX IF NOT EXISTS inference_jobs_model_release_completed_idx
ON inference_jobs (model_id, model_release, completed_at DESC);

CREATE INDEX IF NOT EXISTS inference_jobs_model_release_active_idx
ON inference_jobs (model_id, model_release, status, created_at DESC);
