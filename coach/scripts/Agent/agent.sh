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
AGENT_ENTRYPOINT="${COACH_AGENT_ENTRYPOINT:-$CODE_COACH_DIR/scripts/Agent/generate_narrative.py}"

## 파이썬 import 경로 지정
export PYTHONPATH="$MODEL_PLUGIN_ROOT:$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f "$AGENT_ENTRYPOINT" ]]; then
  echo "Agent 엔트리포인트를 찾지 못했습니다: $AGENT_ENTRYPOINT" >&2
  exit 1
fi

cd "$CODE_COACH_DIR"

RUN_FOLDER="$1"

RUN_DIR="$WORKSPACE_ROOT/run/$RUN_FOLDER"

write_unavailable() {
  "$PYTHON_BIN" - "$RUN_DIR" "$1" <<'PY'
import json, sys
from pathlib import Path
run_dir, code = Path(sys.argv[1]), sys.argv[2]
payload = {
    "status": "unavailable",
    "model": None,
    "prompt_version": "sehyeon-narrative-v2",
    "overall_summary": None,
    "priority_actions": [],
    "maintain_actions": [],
    "disclaimer": "러닝 동작 참고용이며 의료 진단이나 부상 예측이 아닙니다.",
    "validator_version": "service-narrative-2",
    "error_code": code,
}
(run_dir / "outputs" / "running_report.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
PY
}

if ! "$PYTHON_BIN" "$AGENT_ENTRYPOINT" "$RUN_DIR"; then
  echo "Agent 요청 실패: 기본 측정 결과는 계속 생성합니다." >&2
  write_unavailable "llm_request_failed"
elif ! "$PYTHON_BIN" "$CODE_COACH_DIR/scripts/model_contract/structure_narrative.py" "$RUN_DIR"; then
  echo "Agent 검증 실패: 기본 측정 결과는 계속 생성합니다." >&2
  write_unavailable "narrative_validation_failed"
fi
