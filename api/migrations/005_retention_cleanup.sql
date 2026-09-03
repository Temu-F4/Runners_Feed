ALTER TABLE inference_jobs
ALTER COLUMN input_object_name DROP NOT NULL;

CREATE INDEX IF NOT EXISTS guest_sessions_last_seen_idx
ON guest_sessions (last_seen_at);

CREATE INDEX IF NOT EXISTS inference_jobs_completed_idx
ON inference_jobs (completed_at)
WHERE completed_at IS NOT NULL;
