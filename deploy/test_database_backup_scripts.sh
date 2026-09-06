#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly SUCCESS_TAG="sha-4444444444444444444444444444444444444444"

test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

mkdir -p "${test_root}/bin" "${test_root}/project" "${test_root}/state"
touch "${test_root}/project/compose.yaml" "${test_root}/project/compose.backup.yaml"
printf 'API_KEY=test\nPOSTGRES_DB=runners_feed\n' >"${test_root}/prod.env"
printf 'IMAGE_TAG=%s\n' "${SUCCESS_TAG}" >"${test_root}/state/last-successful.env"

cat >"${test_root}/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf 'IMAGE_PREFIX=%s IMAGE_TAG=%s ARGS=%s\n' \
  "${IMAGE_PREFIX:-}" "${IMAGE_TAG:-}" "$*" >>"${MOCK_LOG}"
EOF
chmod +x "${test_root}/bin/docker"

run_backup() {
  PATH="${test_root}/bin:${PATH}" \
  MOCK_LOG="${test_root}/docker.log" \
  RUNNERS_FEED_PROJECT_DIR="${test_root}/project" \
  RUNNERS_FEED_ENV_FILE="${test_root}/prod.env" \
  RUNNERS_FEED_DEPLOY_STATE_DIR="${test_root}/state" \
  bash "$1"
}

run_backup "${PROJECT_ROOT}/deploy/run_database_backup.sh"
run_backup "${PROJECT_ROOT}/deploy/verify_database_backup.sh"

grep -q "IMAGE_PREFIX=ghcr.io/temu-f4/runners-feed IMAGE_TAG=${SUCCESS_TAG}" \
  "${test_root}/docker.log"
grep -q -- 'pull db-backup' "${test_root}/docker.log"
grep -q -- 'pull db-backup-verify' "${test_root}/docker.log"
grep -q -- '--no-deps db-backup' "${test_root}/docker.log"
grep -q -- '--no-deps db-backup-verify' "${test_root}/docker.log"

printf 'Database backup script tests passed\n'
