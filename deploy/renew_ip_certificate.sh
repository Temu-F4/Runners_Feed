#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_DIR="/home/ubuntu/runners-feed-poc-deploy"

cd "${PROJECT_DIR}"

docker compose \
  -f compose.yaml \
  --profile tls-tools \
  run --rm certbot \
  renew \
  --no-random-sleep-on-renew \
  --webroot \
  --webroot-path /var/www/certbot \
  --quiet

docker compose \
  -f compose.yaml \
  exec -T web \
  nginx -s reload
