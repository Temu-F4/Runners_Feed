#!/usr/bin/env bash
# ./coach/scripts/main.sh test1 --agent false --extract --device cpu
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "사용법: $0 RUN_ID [--agent true|false] [--extract] [--device cpu|cuda|mps]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
echo "COACH_STAGE_SUCCESS=feature_extract"
echo "COACH_STAGE_START=report_generate"
if [[ "$RUN_AGENT" == "true" ]]; then
    "$SCRIPT_DIR/Agent/agent.sh" "$RUN_FOLDER"
else
    echo "Agent 실행 생략"
fi
