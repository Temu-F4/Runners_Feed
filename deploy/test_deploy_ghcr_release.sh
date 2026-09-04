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

chmod +x "${test_root}/bin/docker" "${test_root}/bin/curl"

run_deploy() {
  PATH="${test_root}/bin:${PATH}" \
  MOCK_LOG="${test_root}/docker.log" \
  MOCK_FAILED_TAG="${MOCK_FAILED_TAG:-}" \
  RUNNERS_FEED_ENV_FILE="${test_root}/prod.env" \
  RUNNERS_FEED_DEPLOY_STATE_DIR="${test_root}/state" \
  PRODUCTION_BASE_URL="https://production.example" \
  bash "${DEPLOY_SCRIPT}" "$1"
}

run_deploy "${SUCCESS_TAG}"
grep -qx "IMAGE_TAG=${SUCCESS_TAG}" "${test_root}/state/last-successful.env"

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
grep -qx "IMAGE_TAG=${PREVIOUS_TAG}" "${test_root}/state/last-successful.env"

echo "Deployment success and rollback tests passed"
