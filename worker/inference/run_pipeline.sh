#!/usr/bin/env bash
set -euo pipefail

exec python -m inference.pipeline_runner "${1:-test1}"
