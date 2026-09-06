#!/usr/bin/env bash

set -euo pipefail

readonly BASE_URL="${PRODUCTION_BASE_URL:-https://140.238.0.197}"
readonly STATE_DIR="${RUNNERS_FEED_DEPLOY_STATE_DIR:-/var/lib/runners-feed-cd}"
readonly CANDIDATE_STATE_FILE="${STATE_DIR}/model-candidate.env"
readonly SUCCESS_STATE_FILE="${STATE_DIR}/last-successful.env"
readonly DEPLOY_SCRIPT="${RUNNERS_FEED_DEPLOY_SCRIPT:-/opt/runners-feed/current/deploy/deploy_ghcr_release.sh}"
readonly LOCK_FILE="${STATE_DIR}/model-quality-watchdog.lock"

log() {
  printf 'model-quality-watchdog: %s\n' "$*"
}

read_state_value() {
  local key="$1"
  local file="$2"
  sed -n "s/^${key}=//p" "${file}" | head -n 1
}

archive_candidate() {
  local outcome="$1"
  local archive

  archive="${STATE_DIR}/model-candidate-${outcome}-$(date -u +%Y%m%dT%H%M%SZ).env"
  mv "${CANDIDATE_STATE_FILE}" "${archive}"
  log "candidate state archived: ${archive}"
}

mkdir -p "${STATE_DIR}"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  log "another watchdog check is already running"
  exit 0
fi

if [[ ! -r "${CANDIDATE_STATE_FILE}" ]]; then
  exit 0
fi

target_tag="$(read_state_value TARGET_TAG "${CANDIDATE_STATE_FILE}")"
previous_tag="$(read_state_value PREVIOUS_TAG "${CANDIDATE_STATE_FILE}")"
model_id="$(read_state_value MODEL_ID "${CANDIDATE_STATE_FILE}")"
expires_at="$(read_state_value EXPIRES_AT_EPOCH "${CANDIDATE_STATE_FILE}")"

if [[ ! "${target_tag}" =~ ^sha-[0-9a-f]{40}$ ]] \
  || [[ ! "${previous_tag}" =~ ^sha-[0-9a-f]{40}$ ]] \
  || [[ ! "${model_id}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] \
  || [[ ! "${expires_at}" =~ ^[0-9]+$ ]]; then
  log "candidate state is invalid; refusing automatic rollback"
  exit 2
fi

active_tag=""
if [[ -r "${SUCCESS_STATE_FILE}" ]]; then
  active_tag="$(read_state_value IMAGE_TAG "${SUCCESS_STATE_FILE}")"
fi
if [[ "${active_tag}" != "${target_tag}" ]]; then
  log "candidate is no longer active; ending observation"
  archive_candidate superseded
  exit 0
fi

if (( $(date +%s) > expires_at )); then
  log "observation window completed without a rollback signal"
  archive_candidate passed
  exit 0
fi

response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT
http_status="$(curl \
  --silent \
  --show-error \
  --output "${response_file}" \
  --write-out '%{http_code}' \
  --max-time 20 \
  "${BASE_URL}/api/health/model-quality")" || {
    log "quality endpoint request failed; retrying on the next timer run"
    exit 1
  }

quality_status="$(python3 - \
  "${response_file}" \
  "${target_tag}" \
  "${model_id}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
if (
    payload.get("modelRelease") != sys.argv[2]
    or payload.get("modelId") != sys.argv[3]
):
    raise SystemExit("model identity mismatch in quality response")
print(payload.get("status", "missing"))
PY
)" || {
  log "quality response is invalid; retrying on the next timer run"
  exit 1
}

if [[ "${quality_status}" == "ok" || "${quality_status}" == "insufficient_sample" ]]; then
  log "${target_tag} remains healthy (${quality_status})"
  exit 0
fi

if [[ "${http_status}" != "503" || "${quality_status}" != "rollback_required" ]]; then
  log "unexpected quality response HTTP=${http_status} status=${quality_status}"
  exit 1
fi

log "rollback signal received for ${target_tag}; deploying ${previous_tag}"
if env \
  DISABLE_MODEL_WATCHDOG_ARM=1 \
  DISABLE_MODEL_CANARY=1 \
  ALLOW_LEGACY_MODEL_QUALITY=1 \
  bash "${DEPLOY_SCRIPT}" "${previous_tag}"; then
  archive_candidate rolled-back
  log "automatic rollback completed"
  exit 0
fi

log "automatic rollback failed"
exit 1
