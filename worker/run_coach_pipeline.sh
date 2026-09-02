#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "사용법: $0 RUN_ID" >&2
  exit 2
fi

RUN_ID="$1"
export WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
export PYTHON_BIN="${PYTHON_BIN:-python}"

COACH_DEVICE="${COACH_DEVICE:-cpu}"
COACH_AGENT_ENABLED="${COACH_AGENT_ENABLED:-auto}"
if [[ "$COACH_AGENT_ENABLED" == "auto" ]]; then
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    COACH_AGENT_ENABLED="true"
  else
    COACH_AGENT_ENABLED="false"
  fi
fi

/app/coach/scripts/main.sh \
  "$RUN_ID" \
  --agent "$COACH_AGENT_ENABLED" \
  --extract \
  --device "$COACH_DEVICE"

"$PYTHON_BIN" \
  /app/coach_adapter/report_adapter.py \
  "$WORKSPACE_ROOT/run/$RUN_ID"

echo "COACH_PIPELINE=PASS"
