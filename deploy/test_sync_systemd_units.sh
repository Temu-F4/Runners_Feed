#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

mkdir -p "${TEMP_ROOT}/units" "${TEMP_ROOT}/bin"
cp "${PROJECT_ROOT}"/deploy/systemd/* "${TEMP_ROOT}/units/"

cat >"${TEMP_ROOT}/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  is-enabled|is-active) exit 0 ;;
  *) exit 90 ;;
esac
EOF
chmod +x "${TEMP_ROOT}/bin/systemctl"

cat >"${TEMP_ROOT}/bin/sudo" <<'EOF'
#!/usr/bin/env bash
echo "sudo must not run for an already synchronized systemd configuration" >&2
exit 91
EOF
chmod +x "${TEMP_ROOT}/bin/sudo"

PATH="${TEMP_ROOT}/bin:${PATH}" \
RUNNERS_FEED_SYSTEMD_UNIT_TARGET="${TEMP_ROOT}/units" \
RUNNERS_FEED_SYSTEMCTL_BIN="${TEMP_ROOT}/bin/systemctl" \
  bash "${PROJECT_ROOT}/deploy/sync_systemd_units.sh"

echo "systemd synchronization idempotency test passed"
