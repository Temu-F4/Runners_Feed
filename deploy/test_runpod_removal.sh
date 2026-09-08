#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
cd "${PROJECT_ROOT}"

for path in \
  worker/runpod_client.py \
  worker/video_analysis_contract.py \
  api/migrations/010_gpu_video_attempts.sql; do
  if [[ -e "${path}" ]]; then
    echo "RunPod/GPU-attempt artifact must be absent: ${path}" >&2
    exit 1
  fi
done

for path in compose.yaml compose.coach.yaml compose.backup.yaml api worker coach deploy; do
  [[ -e "${path}" ]] || continue
  if git grep -n -i -E \
    'runpod|gpu[-_]dispatch[-_]worker|coach\.dispatch_video_analysis|coach\.run_postprocess|gpu_video_attempts|gpu_dispatch|postprocess' \
    -- "${path}" ':(exclude)deploy/test_runpod_removal.sh'; then
    echo "RunPod/GPU-dispatch references remain in the OCI coach-only runtime" >&2
    exit 1
  fi
done

echo "RunPod removal contract passed"
