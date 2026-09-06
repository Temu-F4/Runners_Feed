#!/usr/bin/env bash
set -euo pipefail

echo "Features 진입"

FEATURES_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(cd "$FEATURES_DIR/.." && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"
FEATURE_ENTRYPOINT="${COACH_FEATURE_ENTRYPOINT:-$FEATURES_DIR/feature_extract.py}"

echo "$FEATURES_DIR"
echo "$WORKSPACE_ROOT"

if [[ ! -f "$FEATURE_ENTRYPOINT" ]]; then
  echo "Feature 엔트리포인트를 찾지 못했습니다: $FEATURE_ENTRYPOINT" >&2
  exit 1
fi

export PYTHONPATH="$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

RUN_FOLDER="$1"

"$PYTHON_BIN" \
  "$FEATURE_ENTRYPOINT" \
  "$WORKSPACE_ROOT" \
  "$RUN_FOLDER"
