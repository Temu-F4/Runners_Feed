-- Migration 010 was already applied on some installations before the
-- asynchronous RunPod states were added to its status contract. Reconcile
-- the live constraint and active-attempt index without changing any rows.
ALTER TABLE inference_gpu_attempts
DROP CONSTRAINT IF EXISTS inference_gpu_attempts_status_check;

ALTER TABLE inference_gpu_attempts
ADD CONSTRAINT inference_gpu_attempts_status_check CHECK (status IN (
    'QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING',
    'SUCCESS', 'FAILED'
));

DROP INDEX IF EXISTS inference_gpu_attempts_one_active_idx;

CREATE UNIQUE INDEX inference_gpu_attempts_one_active_idx
ON inference_gpu_attempts (job_id)
WHERE status IN ('QUEUED', 'RUNNING', 'GPU_SUCCESS', 'POSTPROCESSING');
