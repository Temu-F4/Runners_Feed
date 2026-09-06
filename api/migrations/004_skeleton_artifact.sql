ALTER TABLE inference_jobs
ADD COLUMN IF NOT EXISTS result_skeleton_object TEXT;
