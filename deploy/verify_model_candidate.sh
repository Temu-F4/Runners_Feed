#!/usr/bin/env bash

set -euo pipefail

readonly TARGET_TAG="${1:?usage: verify_model_candidate.sh sha-<commit>}"
readonly REQUIRED="${MODEL_CANARY_REQUIRED:-0}"
readonly MODEL_ID="${COACH_MODEL_ID:-sehyeon-e2fe43e}"
readonly ENV_FILE="${RUNNERS_FEED_ENV_FILE:-/etc/runners-feed/prod.env}"
readonly PROJECT_DIR="${RUNNERS_FEED_PROJECT_DIR:-/opt/runners-feed/current}"
readonly GOLDEN_DIR="${MODEL_GOLDEN_DIR:-/opt/runners-feed/model-golden/${MODEL_ID}}"
readonly BASELINE_PATH="${PROJECT_DIR}/coach/model_plugins/${MODEL_ID}/quality_baseline.json"
readonly IMAGE_PREFIX="${IMAGE_PREFIX:-ghcr.io/temu-f4/runners-feed}"

if [[ ! "${TARGET_TAG}" =~ ^sha-[0-9a-f]{40}$ ]]; then
  echo "Model canary refused non-immutable image tag: ${TARGET_TAG}" >&2
  exit 2
fi
if [[ "${REQUIRED}" != "0" && "${REQUIRED}" != "1" ]]; then
  echo "MODEL_CANARY_REQUIRED must be 0 or 1" >&2
  exit 2
fi
if [[ ! "${MODEL_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]; then
  echo "Invalid COACH_MODEL_ID: ${MODEL_ID}" >&2
  exit 2
fi

if [[ "${REQUIRED}" == "0" ]]; then
  echo "Model canary skipped; MODEL_CANARY_REQUIRED is not enabled"
  exit 0
fi

for path in "${ENV_FILE}" "${GOLDEN_DIR}/input.mp4" \
  "${GOLDEN_DIR}/user_info.json" "${BASELINE_PATH}"; do
  if [[ ! -r "${path}" ]]; then
    echo "Required model canary input is not readable: ${path}" >&2
    exit 1
  fi
done

python3 - "${BASELINE_PATH}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    baseline = json.load(stream)
if baseline.get("approval_status") != "approved":
    raise SystemExit("model quality baseline is not approved by the modeler")
PY

compose() {
  IMAGE_TAG="${TARGET_TAG}" docker compose \
    --env-file "${ENV_FILE}" \
    --project-name runners-feed \
    -f "${PROJECT_DIR}/compose.yaml" \
    -f "${PROJECT_DIR}/compose.coach.yaml" \
    --profile coach \
    "$@"
}

runtime_run_root="$(compose config --format json | python3 -c '
import json, sys
config = json.load(sys.stdin)
for volume in config["services"]["coach-manual"].get("volumes", []):
    if volume.get("target") == "/workspace/run":
        print(volume["source"])
        break
else:
    raise SystemExit("coach-manual /workspace/run mount was not found")
')"
if [[ -z "${runtime_run_root}" || "${runtime_run_root}" != /* ]]; then
  echo "Model canary runtime path must be absolute" >&2
  exit 1
fi

run_id="canary-${TARGET_TAG#sha-}-$$"
run_dir="${runtime_run_root}/${run_id}"
case "${run_dir}" in
  "${runtime_run_root}"/canary-*) ;;
  *)
    echo "Refusing unsafe model canary path: ${run_dir}" >&2
    exit 2
    ;;
esac

cleanup() {
  if [[ -d "${run_dir}" ]]; then
    find "${run_dir}" -mindepth 1 -delete
    rmdir "${run_dir}"
  fi
}
trap cleanup EXIT

mkdir -p "${run_dir}"
cp "${GOLDEN_DIR}/input.mp4" "${run_dir}/input.mp4"
cp "${GOLDEN_DIR}/user_info.json" "${run_dir}/user_info.json"

echo "Running approved model canary with ${IMAGE_PREFIX}-coach-worker:${TARGET_TAG}"
compose run --rm \
  --entrypoint python \
  -e COACH_MODEL_ID="${MODEL_ID}" \
  coach-manual \
  /app/coach/scripts/model_contract/validate_plugin.py \
  "/app/coach/model_plugins/${MODEL_ID}" \
  --weights-root /workspace/models

compose run --rm \
  -e COACH_MODEL_ID="${MODEL_ID}" \
  -e COACH_AGENT_ENABLED=false \
  coach-manual "${run_id}"

compose run --rm \
  --entrypoint python \
  -e COACH_MODEL_ID="${MODEL_ID}" \
  coach-manual \
  /app/coach/scripts/model_contract/quality_gate.py \
  "/workspace/run/${run_id}" \
  "/app/coach/model_plugins/${MODEL_ID}/quality_baseline.json"

echo "Model canary passed: ${TARGET_TAG}/${MODEL_ID}"
