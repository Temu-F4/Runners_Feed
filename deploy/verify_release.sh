#!/usr/bin/env bash

set -euo pipefail

readonly TARGET_TAG="${1:?usage: verify_release.sh sha-<commit>}"
readonly IMAGE_PREFIX="${IMAGE_PREFIX:-ghcr.io/temu-f4/runners-feed}"
readonly ENV_FILE="${RUNNERS_FEED_ENV_FILE:-/etc/runners-feed/prod.env}"
readonly BASE_URL="${PRODUCTION_BASE_URL:-https://140.238.0.197}"
readonly PROJECT_DIR="${RUNNERS_FEED_PROJECT_DIR:-/opt/runners-feed/current}"
readonly COMPOSE_FILES=(
  -f "${PROJECT_DIR}/compose.yaml"
  -f "${PROJECT_DIR}/compose.coach.yaml"
)
readonly SERVICES=(api frontend web coach-worker maintenance)
readonly SUPPORT_SERVICES=(alertmanager)

fail() {
  echo "Release verification failed: $*" >&2
  exit 1
}

if [[ ! "${TARGET_TAG}" =~ ^sha-[0-9a-f]{40}$ ]]; then
  fail "refusing non-immutable image tag: ${TARGET_TAG}"
fi

if [[ ! -r "${ENV_FILE}" ]]; then
  fail "production environment file is not readable: ${ENV_FILE}"
fi

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is required for JSON response validation"
fi

compose() {
  docker compose \
    --env-file "${ENV_FILE}" \
    --project-name runners-feed \
    "${COMPOSE_FILES[@]}" \
    --profile coach \
    "$@"
}

verify_services() {
  local service container_ids container_id state config_image health expected_image

  for service in "${SERVICES[@]}"; do
    container_ids="$(compose ps -q "${service}")" || fail "unable to inspect Compose service ${service}"
    if [[ -z "${container_ids}" ]]; then
      fail "Compose service ${service} has no running container"
    fi
    if [[ "$(printf '%s\n' "${container_ids}" | awk 'NF {count++} END {print count + 0}')" != 1 ]]; then
      fail "Compose service ${service} does not have exactly one running container"
    fi

    container_id="$(printf '%s\n' "${container_ids}" | awk 'NF {print; exit}')"
    state="$(docker inspect -f '{{.State.Status}}' "${container_id}")" \
      || fail "unable to inspect state for ${service}"
    [[ "${state}" == "running" ]] \
      || fail "${service} is ${state}, expected running"

    config_image="$(docker inspect -f '{{.Config.Image}}' "${container_id}")" \
      || fail "unable to inspect image for ${service}"
    expected_image="${IMAGE_PREFIX}-${service}:${TARGET_TAG}"
    [[ "${config_image}" == "${expected_image}" ]] \
      || fail "${service} uses ${config_image}, expected ${expected_image}"

    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}")" \
      || fail "unable to inspect health for ${service}"
    if [[ "${health}" != "none" && "${health}" != "healthy" ]]; then
      fail "${service} health is ${health}"
    fi
  done
}

verify_support_services() {
  local service container_ids container_id state health

  for service in "${SUPPORT_SERVICES[@]}"; do
    container_ids="$(compose ps -q "${service}")" \
      || fail "unable to inspect Compose support service ${service}"
    if [[ -z "${container_ids}" ]]; then
      fail "Compose support service ${service} has no running container"
    fi
    if [[ "$(printf '%s\n' "${container_ids}" | awk 'NF {count++} END {print count + 0}')" != 1 ]]; then
      fail "Compose support service ${service} does not have exactly one running container"
    fi

    container_id="$(printf '%s\n' "${container_ids}" | awk 'NF {print; exit}')"
    state="$(docker inspect -f '{{.State.Status}}' "${container_id}")" \
      || fail "unable to inspect state for ${service}"
    [[ "${state}" == "running" ]] \
      || fail "${service} is ${state}, expected running"

    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}")" \
      || fail "unable to inspect health for ${service}"
    if [[ "${health}" != "none" && "${health}" != "healthy" ]]; then
      fail "${service} health is ${health}"
    fi
  done
}

fetch_http() {
  local path="$1"
  local output_file="$2"
  local status

  status="$(curl \
    --silent \
    --show-error \
    --output "${output_file}" \
    --write-out '%{http_code}' \
    --max-time 20 \
    "${BASE_URL}${path}")" \
    || fail "request failed: ${path}"
  [[ "${status}" == "200" ]] || fail "${path} returned HTTP ${status}"
}

assert_json_fields() {
  local payload_file="$1"
  shift

  python3 - "${payload_file}" "$@" <<'PY'
import json
import sys

payload_file = sys.argv[1]
specs = sys.argv[2:]
with open(payload_file, encoding="utf-8") as stream:
    payload = json.load(stream)

for spec in specs:
    path, expected = spec.split("=", 1)
    value = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"missing JSON field: {path}")
        value = value[part]
    if str(value) != expected:
        raise SystemExit(
            f"JSON field {path} is {value!r}, expected {expected!r}"
        )
PY
}

assert_storage_buckets() {
  local payload_file="$1"

  python3 - "${payload_file}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)

buckets = payload.get("buckets")
if not isinstance(buckets, dict) or not buckets.get("raw") or not buckets.get("results"):
    raise SystemExit("storage health did not return both bucket names")
PY
}

response_dir="$(mktemp -d)"
trap 'rm -rf "${response_dir}"' EXIT

verify_services
verify_support_services

root_response="${response_dir}/root.html"
fetch_http "/" "${root_response}"
grep -Eqi '<html|<!doctype html' "${root_response}" \
  || fail "Frontend response is not HTML"

health_response="${response_dir}/health.json"
fetch_http "/api/health" "${health_response}"
assert_json_fields "${health_response}" "status=ok"

dependencies_response="${response_dir}/dependencies.json"
fetch_http "/api/health/dependencies" "${dependencies_response}"
assert_json_fields \
  "${dependencies_response}" \
  "status=ok" \
  "dependencies.postgres=ok" \
  "dependencies.redis=ok"

storage_response="${response_dir}/storage.json"
fetch_http "/api/health/storage" "${storage_response}"
assert_json_fields \
  "${storage_response}" \
  "status=ok" \
  "storage=oci_object_storage"
assert_storage_buckets "${storage_response}"

echo "Release verification passed: ${TARGET_TAG}"
