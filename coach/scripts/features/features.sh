#!/usr/bin/env bash
set -e

echo "Features 진입"

FEATURES_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(cd "$FEATURES_DIR/.." && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"

echo $FEATURES_DIR
echo "$WORKSPACE_ROOT"

export PYTHONPATH="$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

RUN_FOLDER="$1"

"$PYTHON_BIN" \
  "$FEATURES_DIR/feature_extract.py" \
  "$WORKSPACE_ROOT" \
  "$RUN_FOLDER" \
