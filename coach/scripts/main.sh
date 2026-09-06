#!/usr/bin/env bash
# ./coach/scripts/main.sh test1 --agent false --device cpu
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "사용법: $0 RUN_ID [--agent true|false] [--device cpu|cuda|mps]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"

RUN_FOLDER="$1"
shift

RUN_AGENT="${COACH_AGENT_ENABLED:-true}"

if [[ "${1:-}" == "--agent" ]]; then
    RUN_AGENT="${2:-true}"
    shift 2
fi


"$SCRIPT_DIR/hpe/hpe.sh" "$RUN_FOLDER" "$@"
echo "COACH_STAGE_START=feature_extract"
"$SCRIPT_DIR/features/features.sh" "$RUN_FOLDER"
"$PYTHON_BIN" \
    "$SCRIPT_DIR/model_contract/validate_artifacts.py" \
    "${WORKSPACE_ROOT}/run/${RUN_FOLDER}"
echo "COACH_STAGE_SUCCESS=feature_extract"
echo "COACH_STAGE_START=report_generate"
if [[ "$RUN_AGENT" == "true" ]]; then
    "$SCRIPT_DIR/Agent/agent.sh" "$RUN_FOLDER"
else
    echo "Agent 실행 생략"
fi
