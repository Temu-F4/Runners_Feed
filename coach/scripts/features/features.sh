#!/usr/bin/env bash
set -euo pipefail

echo "Features 진입"

FEATURES_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(cd "$FEATURES_DIR/.." && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"
COACH_MODEL_ID="${COACH_MODEL_ID:-sehyeon-e2fe43e}"
MODEL_PLUGIN_ROOT="${COACH_MODEL_PLUGIN_ROOT:-$CODE_COACH_DIR/model_plugins/$COACH_MODEL_ID}"
FEATURE_ENTRYPOINT="${COACH_FEATURE_ENTRYPOINT:-$MODEL_PLUGIN_ROOT/scripts/features/feature_extract.py}"

echo "$FEATURES_DIR"
echo "$WORKSPACE_ROOT"

if [[ ! -f "$FEATURE_ENTRYPOINT" ]]; then
  echo "Feature 엔트리포인트를 찾지 못했습니다: $FEATURE_ENTRYPOINT" >&2
  exit 1
fi

export PYTHONPATH="$MODEL_PLUGIN_ROOT:$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

RUN_FOLDER="$1"

"$PYTHON_BIN" \
  "$FEATURE_ENTRYPOINT" \
  "$WORKSPACE_ROOT" \
  "$RUN_FOLDER"
