#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly WATCHDOG_SCRIPT="${PROJECT_ROOT}/deploy/check_model_quality.sh"
readonly TARGET_TAG="sha-5555555555555555555555555555555555555555"
readonly PREVIOUS_TAG="sha-6666666666666666666666666666666666666666"

test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT
mkdir -p "${test_root}/bin" "${test_root}/state"

cat >"${test_root}/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

output_file=""
for ((index = 1; index <= $#; index++)); do
  if [[ "${!index}" == "--output" ]]; then
    next=$((index + 1))
    output_file="${!next}"
  fi
done

printf '{"status":"%s","modelId":"sehyeon-57e4938","modelRelease":"%s"}\n' \
  "${MOCK_QUALITY_STATUS}" "${MOCK_RESPONSE_TAG}" >"${output_file}"
printf '%s' "${MOCK_HTTP_STATUS}"
EOF

cat >"${test_root}/deploy.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s|%s|%s\n' \
  "${DISABLE_MODEL_WATCHDOG_ARM:-}" \
  "${DISABLE_MODEL_CANARY:-}" \
  "${ALLOW_LEGACY_MODEL_QUALITY:-}" \
  "$1" >>"${MOCK_DEPLOY_LOG}"
EOF

chmod +x "${test_root}/bin/curl" "${test_root}/deploy.sh"

write_candidate() {
  local expires_at="$1"
  {
    printf 'TARGET_TAG=%s\n' "${TARGET_TAG}"
    printf 'PREVIOUS_TAG=%s\n' "${PREVIOUS_TAG}"
    printf 'MODEL_ID=sehyeon-57e4938\n'
    printf 'ARMED_AT_EPOCH=%s\n' "$((expires_at - 3600))"
    printf 'EXPIRES_AT_EPOCH=%s\n' "${expires_at}"
  } >"${test_root}/state/model-candidate.env"
  printf 'IMAGE_TAG=%s\n' "${TARGET_TAG}" \
    >"${test_root}/state/last-successful.env"
}

run_watchdog() {
  PATH="${test_root}/bin:${PATH}" \
  MOCK_DEPLOY_LOG="${test_root}/deploy.log" \
  RUNNERS_FEED_DEPLOY_STATE_DIR="${test_root}/state" \
  RUNNERS_FEED_DEPLOY_SCRIPT="${test_root}/deploy.sh" \
  PRODUCTION_BASE_URL="https://production.example" \
  bash "${WATCHDOG_SCRIPT}"
}

future_epoch="$(( $(date +%s) + 3600 ))"
write_candidate "${future_epoch}"
MOCK_QUALITY_STATUS=insufficient_sample
MOCK_HTTP_STATUS=200
MOCK_RESPONSE_TAG="${TARGET_TAG}"
export MOCK_QUALITY_STATUS MOCK_HTTP_STATUS MOCK_RESPONSE_TAG
run_watchdog
test -f "${test_root}/state/model-candidate.env"
test ! -f "${test_root}/deploy.log"

MOCK_QUALITY_STATUS=rollback_required
MOCK_HTTP_STATUS=503
export MOCK_QUALITY_STATUS MOCK_HTTP_STATUS
run_watchdog
grep -qx "1|1|1|${PREVIOUS_TAG}" "${test_root}/deploy.log"
test ! -f "${test_root}/state/model-candidate.env"
find "${test_root}/state" -maxdepth 1 \
  -name 'model-candidate-rolled-back-*.env' | grep -q .

write_candidate "$(( $(date +%s) - 1 ))"
: >"${test_root}/deploy.log"
run_watchdog
test ! -s "${test_root}/deploy.log"
find "${test_root}/state" -maxdepth 1 \
  -name 'model-candidate-passed-*.env' | grep -q .

echo "Model quality watchdog tests passed"
