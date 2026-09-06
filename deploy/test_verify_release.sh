#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROJECT_ROOT
readonly VERIFY_SCRIPT="${PROJECT_ROOT}/deploy/verify_release.sh"
readonly TARGET_TAG="sha-4444444444444444444444444444444444444444"

test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

mkdir -p "${test_root}/bin" "${test_root}/project"
touch "${test_root}/project/compose.yaml" "${test_root}/project/compose.coach.yaml"
printf 'API_KEY=test\n' >"${test_root}/prod.env"

cat >"${test_root}/bin/docker" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

if [[ "${1:-}" == "compose" ]]; then
  for arg in "$@"; do
    if [[ "$arg" == "ps" ]]; then
      service="${@: -1}"
      printf 'container-%s\n' "$service"
      exit 0
    fi
  done
fi

if [[ "${1:-}" == "inspect" ]]; then
  format="$3"
  container_id="$4"
  service="${container_id#container-}"
  case "$format" in
    "{{.State.Status}}")
      printf 'running\n'
      ;;
    "{{.Config.Image}}")
      if [[ "${MOCK_BAD_IMAGE_SERVICE:-}" == "$service" ]]; then
        printf 'unexpected/image:latest\n'
      else
        printf 'ghcr.io/temu-f4/runners-feed-%s:%s\n' "$service" "${IMAGE_TAG}"
      fi
      ;;
    "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}")
      if [[ "$service" == "api" || "$service" == "frontend" ]]; then
        printf 'healthy\n'
      else
        printf 'none\n'
      fi
      ;;
    *)
      echo "unexpected docker inspect format: $format" >&2
      exit 1
      ;;
  esac
  exit 0
fi

echo "unexpected docker command: $*" >&2
exit 1
EOF

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

url="${@: -1}"
path="${url#*production.example}"

if [[ "${MOCK_FAIL_PATH:-}" == "$path" ]]; then
  printf '{"status":"error"}\n' >"$output_file"
  printf '503'
  exit 0
fi

case "$path" in
  "/")
    printf '<!doctype html><html><body>Runners Feed</body></html>\n' >"$output_file"
    ;;
  "/api/health")
    printf '{"status":"ok"}\n' >"$output_file"
    ;;
  "/api/health/dependencies")
    printf '{"status":"ok","dependencies":{"postgres":"ok","redis":"ok"}}\n' >"$output_file"
    ;;
  "/api/health/storage")
    printf '{"status":"ok","storage":"oci_object_storage","buckets":{"raw":"raw","results":"results"}}\n' >"$output_file"
    ;;
  *)
    printf '{"status":"error"}\n' >"$output_file"
    printf '404'
    exit 0
    ;;
esac

printf '200'
EOF

chmod +x "${test_root}/bin/docker" "${test_root}/bin/curl"

run_verify() {
  PATH="${test_root}/bin:${PATH}" \
  IMAGE_PREFIX="ghcr.io/temu-f4/runners-feed" \
  IMAGE_TAG="${TARGET_TAG}" \
  RUNNERS_FEED_PROJECT_DIR="${test_root}/project" \
  RUNNERS_FEED_ENV_FILE="${test_root}/prod.env" \
  PRODUCTION_BASE_URL="https://production.example" \
  bash "${VERIFY_SCRIPT}" "${TARGET_TAG}"
}

run_verify

MOCK_BAD_IMAGE_SERVICE="api"
export MOCK_BAD_IMAGE_SERVICE
if run_verify; then
  echo "Expected image mismatch to fail" >&2
  exit 1
fi
unset MOCK_BAD_IMAGE_SERVICE

MOCK_FAIL_PATH="/api/health/storage"
export MOCK_FAIL_PATH
if run_verify; then
  echo "Expected storage health failure to fail" >&2
  exit 1
fi

echo "Release verification tests passed"
