#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "사용법: $0 RUN_ID" >&2
  exit 2
fi

RUN_ID="$1"
export WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
export PYTHON_BIN="${PYTHON_BIN:-python}"

COACH_AGENT_ENABLED="${COACH_AGENT_ENABLED:-auto}"
if [[ "$COACH_AGENT_ENABLED" == "auto" ]]; then
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    COACH_AGENT_ENABLED="true"
  else
    COACH_AGENT_ENABLED="false"
  fi
fi

echo "COACH_STAGE_START=feature_extract"
/app/coach/scripts/features/features.sh "$RUN_ID"
"$PYTHON_BIN" /app/coach/scripts/model_contract/validate_artifacts.py \
  "$WORKSPACE_ROOT/run/$RUN_ID"
echo "COACH_STAGE_SUCCESS=feature_extract"

echo "COACH_STAGE_START=report_generate"
if [[ "$COACH_AGENT_ENABLED" == "true" ]]; then
  /app/coach/scripts/Agent/agent.sh "$RUN_ID"
else
  echo "Agent 실행 생략"
fi
"$PYTHON_BIN" /app/coach_adapter/report_adapter.py \
  "$WORKSPACE_ROOT/run/$RUN_ID"
"$PYTHON_BIN" /app/coach_adapter/skeleton_adapter.py \
  "$WORKSPACE_ROOT/run/$RUN_ID"
echo "COACH_STAGE_SUCCESS=report_generate"

echo "COACH_POSTPROCESS=PASS"
