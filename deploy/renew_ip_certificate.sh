#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_DIR="${RUNNERS_FEED_PROJECT_DIR:-/opt/runners-feed/current}"
readonly ENV_FILE="${RUNNERS_FEED_ENV_FILE:-/etc/runners-feed/prod.env}"

cd "${PROJECT_DIR}"

docker compose \
  --env-file "${ENV_FILE}" \
  --project-name runners-feed \
  -f compose.yaml \
  --profile tls-tools \
  run --rm certbot \
  renew \
  --no-random-sleep-on-renew \
  --webroot \
  --webroot-path /var/www/certbot \
  --quiet

docker compose \
  --env-file "${ENV_FILE}" \
  --project-name runners-feed \
  -f compose.yaml \
  exec -T web \
  nginx -s reload
