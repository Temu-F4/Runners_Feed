#!/usr/bin/env bash
set -euo pipefail

python /app/validate_runpod_config.py
exec celery "$@"
