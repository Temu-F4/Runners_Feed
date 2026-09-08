#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly DEPLOY_SCRIPT="${PROJECT_ROOT}/deploy/deploy_ghcr_release.sh"
readonly SUCCESS_TAG="sha-1111111111111111111111111111111111111111"
readonly FAILED_TAG="sha-2222222222222222222222222222222222222222"
readonly PREVIOUS_TAG="sha-3333333333333333333333333333333333333333"

test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

mkdir -p "${test_root}/bin" "${test_root}/state"
printf 'API_KEY=test\n' >"${test_root}/prod.env"

cat >"${test_root}/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s|%s\n' "${IMAGE_TAG:-unset}" "$*" >>"${MOCK_LOG}"
exit 0
EOF

cat >"${test_root}/bin/curl" <<'EOF'
#!/usr/bin/env bash
if [[ "${IMAGE_TAG:-}" == "${MOCK_FAILED_TAG:-}" ]]; then
  exit 22
fi
exit 0
EOF

cat >"${test_root}/verify_release.sh" <<'EOF'
#!/usr/bin/env bash
printf 'verify|%s|%s\n' \
  "${IMAGE_TAG:-unset}" \
  "${ALLOW_LEGACY_MODEL_QUALITY:-0}" >>"${MOCK_LOG}"
if [[ "${IMAGE_TAG:-}" == "${MOCK_FAILED_TAG:-}" || "${IMAGE_TAG:-}" == "${MOCK_ROLLBACK_FAILED_TAG:-}" ]]; then
  exit 1
fi
EOF

cat >"${test_root}/verify_model_candidate.sh" <<'EOF'
#!/usr/bin/env bash
printf 'canary|%s\n' "${IMAGE_TAG:-unset}" >>"${MOCK_LOG}"
exit 0
EOF

cat >"${test_root}/disk_guard.sh" <<'EOF'
#!/usr/bin/env bash
echo "disk-guard" >>"${MOCK_LOG}"
EOF

chmod +x \
  "${test_root}/bin/docker" \
  "${test_root}/bin/curl" \
  "${test_root}/verify_release.sh" \
  "${test_root}/verify_model_candidate.sh" \
  "${test_root}/disk_guard.sh"

run_deploy() {
  PATH="${test_root}/bin:${PATH}" \
  MOCK_LOG="${test_root}/docker.log" \
  MOCK_FAILED_TAG="${MOCK_FAILED_TAG:-}" \
  RUNNERS_FEED_ENV_FILE="${test_root}/prod.env" \
  RUNNERS_FEED_DEPLOY_STATE_DIR="${test_root}/state" \
  RELEASE_VERIFIER="${test_root}/verify_release.sh" \
  MODEL_CANDIDATE_VERIFIER="${test_root}/verify_model_candidate.sh" \
  RUNNERS_FEED_DEPLOY_DISK_GUARD="${test_root}/disk_guard.sh" \
  PRODUCTION_BASE_URL="https://production.example" \
  bash "${DEPLOY_SCRIPT}" "$1"
}

run_deploy "${SUCCESS_TAG}"
grep -qx "IMAGE_TAG=${SUCCESS_TAG}" "${test_root}/state/last-successful.env"
grep -q "gpu-dispatch-worker" "${test_root}/docker.log"
grep -q "disk-guard" "${test_root}/docker.log"

printf 'IMAGE_TAG=%s\n' "${PREVIOUS_TAG}" >"${test_root}/state/last-successful.env"
run_deploy "${SUCCESS_TAG}"
grep -qx "TARGET_TAG=${SUCCESS_TAG}" "${test_root}/state/model-candidate.env"
grep -qx "PREVIOUS_TAG=${PREVIOUS_TAG}" "${test_root}/state/model-candidate.env"
grep -qx "MODEL_ID=sehyeon-dcc2d7d" "${test_root}/state/model-candidate.env"
rm "${test_root}/state/model-candidate.env"

printf 'IMAGE_TAG=%s\n' "${PREVIOUS_TAG}" >"${test_root}/state/last-successful.env"
: >"${test_root}/docker.log"

MOCK_FAILED_TAG="${FAILED_TAG}"
export MOCK_FAILED_TAG
if run_deploy "${FAILED_TAG}"; then
  echo "Expected the failed release to return a non-zero status" >&2
  exit 1
fi

grep -q "${FAILED_TAG}|compose" "${test_root}/docker.log"
grep -q "${PREVIOUS_TAG}|compose" "${test_root}/docker.log"
grep -q "verify|${FAILED_TAG}|0" "${test_root}/docker.log"
grep -q "verify|${PREVIOUS_TAG}|1" "${test_root}/docker.log"
grep -q "canary|${FAILED_TAG}" "${test_root}/docker.log"
if grep -q "canary|${PREVIOUS_TAG}" "${test_root}/docker.log"; then
  echo "Rollback must not be blocked by the candidate canary" >&2
  exit 1
fi
grep -qx "IMAGE_TAG=${PREVIOUS_TAG}" "${test_root}/state/last-successful.env"

if [[ -e "${test_root}/state/model-candidate.env" ]]; then
  echo "Failed release must not arm watchdog" >&2
  exit 1
fi

: >"${test_root}/docker.log"
MOCK_ROLLBACK_FAILED_TAG="${PREVIOUS_TAG}"
export MOCK_ROLLBACK_FAILED_TAG
if run_deploy "${FAILED_TAG}" >"${test_root}/rollback-failure.log" 2>&1; then
  echo "Expected rollback verification failure to return a non-zero status" >&2
  exit 1
fi

grep -q "Rollback failed" "${test_root}/rollback-failure.log"
grep -qx "IMAGE_TAG=${PREVIOUS_TAG}" "${test_root}/state/last-successful.env"

echo "Deployment success and rollback tests passed"
bash "${PROJECT_ROOT}/deploy/test_sync_systemd_units.sh"
