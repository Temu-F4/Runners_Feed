CREATE TABLE IF NOT EXISTS inference_jobs (
    job_id UUID PRIMARY KEY,
    case_id VARCHAR(64) NOT NULL,
    input_object_name TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('QUEUED', 'PROCESSING', 'SUCCESS', 'FAILED')),
    result_details_object TEXT,
    result_predictions_object TEXT,
    result_report_object TEXT,
    result_video_object TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS result_report_object TEXT;

CREATE INDEX IF NOT EXISTS inference_jobs_status_created_idx
ON inference_jobs (status, created_at DESC);
