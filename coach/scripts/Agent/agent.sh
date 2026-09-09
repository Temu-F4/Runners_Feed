#!/usr/bin/env bash
set -euo pipefail

echo "Agent 진입"

FEATURES_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(cd "$FEATURES_DIR/.." && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"
COACH_MODEL_ID="${COACH_MODEL_ID:-sehyeon-57e4938}"
MODEL_PLUGIN_ROOT="${COACH_MODEL_PLUGIN_ROOT:-$CODE_COACH_DIR/model_plugins/$COACH_MODEL_ID}"
AGENT_ENTRYPOINT="${COACH_AGENT_ENTRYPOINT:-$MODEL_PLUGIN_ROOT/scripts/Agent/Running_coach.py}"

## 파이썬 import 경로 지정
export PYTHONPATH="$MODEL_PLUGIN_ROOT:$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f "$AGENT_ENTRYPOINT" ]]; then
  echo "Agent 엔트리포인트를 찾지 못했습니다: $AGENT_ENTRYPOINT" >&2
  exit 1
fi

cd "$CODE_COACH_DIR"

RUN_FOLDER="$1"

"$PYTHON_BIN" \
  "$AGENT_ENTRYPOINT" \
  "$WORKSPACE_ROOT" \
  "$RUN_FOLDER"

"$PYTHON_BIN" \
  "$CODE_COACH_DIR/scripts/model_contract/structure_narrative.py" \
  "$WORKSPACE_ROOT/run/$RUN_FOLDER"
