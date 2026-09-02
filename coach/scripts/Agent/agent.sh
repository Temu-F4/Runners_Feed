#!/usr/bin/env bash
set -e

echo "Agent 진입"

FEATURES_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(cd "$FEATURES_DIR/.." && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"

## 파이썬 import 경로 지정
export PYTHONPATH="$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

cd "$CODE_COACH_DIR"

RUN_FOLDER="$1"

"$PYTHON_BIN" \
  "$FEATURES_DIR/Running_coach.py" \
  "$WORKSPACE_ROOT" \
  "$RUN_FOLDER" \
