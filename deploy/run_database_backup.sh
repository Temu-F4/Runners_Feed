#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_DIR="${RUNNERS_FEED_PROJECT_DIR:-/opt/runners-feed/current}"
readonly ENV_FILE="${RUNNERS_FEED_ENV_FILE:-/etc/runners-feed/prod.env}"
readonly STATE_FILE="${RUNNERS_FEED_DEPLOY_STATE_DIR:-/var/lib/runners-feed-cd}/last-successful.env"
readonly IMAGE_PREFIX="${IMAGE_PREFIX:-ghcr.io/temu-f4/runners-feed}"

if [[ ! -r "${ENV_FILE}" ]]; then
  echo "Production environment file is not readable: ${ENV_FILE}" >&2
  exit 2
fi

if [[ ! -r "${STATE_FILE}" ]]; then
  echo "Successful release state is not readable: ${STATE_FILE}" >&2
  exit 2
fi

readonly IMAGE_TAG="$(sed -n 's/^IMAGE_TAG=//p' "${STATE_FILE}" | head -n 1)"
if [[ ! "${IMAGE_TAG}" =~ ^sha-[0-9a-f]{40}$ ]]; then
  echo "Successful release state is invalid: ${STATE_FILE}" >&2
  exit 2
fi

export IMAGE_PREFIX IMAGE_TAG

cd "$PROJECT_DIR"
docker compose \
  --env-file "${ENV_FILE}" \
  --project-name runners-feed \
  -f compose.yaml \
  -f compose.backup.yaml \
  --profile backup \
  pull db-backup
docker compose \
  --env-file "${ENV_FILE}" \
  --project-name runners-feed \
  -f compose.yaml \
  -f compose.backup.yaml \
  --profile backup \
  run --rm --no-deps db-backup
