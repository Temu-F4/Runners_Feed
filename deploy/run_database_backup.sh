#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_DIR="/home/ubuntu/runners-feed-poc-deploy"

cd "$PROJECT_DIR"
docker compose \
  -f compose.yaml \
  -f compose.backup.yaml \
  --profile backup \
  run --rm db-backup
