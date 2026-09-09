#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
cd "${PROJECT_ROOT}"

for path in \
  worker/runpod_client.py \
  worker/start_coach_worker.sh \
  worker/video_analysis_contract.py \
  worker/run_coach_postprocess.sh \
  api/migrations/010_gpu_video_attempts.sql \
  api/migrations/011_gpu_attempt_status_contract.sql \
  coach/model_plugins/sehyeon-e2fe43e/model_manifest.json; do
  [[ -f "${path}" ]] || {
    echo "Required RunPod boundary file is missing: ${path}" >&2
    exit 1
  }
done

grep -q 'DROP CONSTRAINT IF EXISTS inference_gpu_attempts_status_check' \
  api/migrations/011_gpu_attempt_status_contract.sql
grep -q "'GPU_SUCCESS', 'POSTPROCESSING'" \
  api/migrations/011_gpu_attempt_status_contract.sql

grep -q -- '--queues=gpu_dispatch,postprocess,coach' compose.coach.yaml
if grep -q '^  gpu-dispatch-worker:' compose.coach.yaml; then
  echo "GPU dispatch must run in the single coach-worker service" >&2
  exit 1
fi
if grep -q 'coach.run_object_storage' worker/coach_celery_app.py worker/coach_tasks.py; then
  echo "Production local-inference fallback task must be absent" >&2
  exit 1
fi
grep -q 'coach.dispatch_video_analysis' api/app/main.py
grep -q 'normalize_features.py' worker/run_coach_postprocess.sh
grep -q '/app/start_coach_worker.sh' compose.coach.yaml
grep -q -- '--entrypoint /app/run_coach_postprocess.sh' deploy/verify_model_candidate.sh
grep -q -- '--profile manual-coach' deploy/verify_model_candidate.sh
if grep -q 'input.mp4' deploy/verify_model_candidate.sh; then
  echo "Production model canary must consume approved RunPod artifacts, not run local HPE" >&2
  exit 1
fi
grep -q 'sehyeon-e2fe43e' compose.yaml compose.coach.yaml

echo "RunPod video-analysis boundary contract passed"
