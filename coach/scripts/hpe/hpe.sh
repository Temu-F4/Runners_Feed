#!/usr/bin/env bash
set -euo pipefail

echo "HPE 진입"

HPE_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(cd "$HPE_DIR/.." && pwd)"
CODE_COACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CODE_COACH_DIR}"
PYTHON_BIN="${PYTHON_BIN:-$CODE_COACH_DIR/.venv/bin/python}"

echo "coach 코드 위치: $CODE_COACH_DIR"
echo "coach 작업공간: $WORKSPACE_ROOT"

## 파이썬 import 경로 지정
export PYTHONPATH="$CODE_COACH_DIR${PYTHONPATH:+:$PYTHONPATH}"

cd "$CODE_COACH_DIR"

RUN_FOLDER="$1"
RUN_DIR="$WORKSPACE_ROOT/run/$RUN_FOLDER"

OUTPUT_DIR="$RUN_DIR/outputs"

mkdir -p "$OUTPUT_DIR"

shift

VIDEO_PATH=$(find "$RUN_DIR" \
    -maxdepth 1 \
    -type f \
    \( -iname "*.mp4" -o -iname "*.mov" \) \
    -print \
    -quit)

if [[ -z "$VIDEO_PATH" ]]; then
    echo "MP4 또는 MOV 파일을 찾지 못했습니다: $RUN_DIR"
    exit 1
fi

echo "영상 발견: $VIDEO_PATH"
printf '\n영상 분석 및 렌더링\n'
echo "COACH_STAGE_START=video_analysis"
"$PYTHON_BIN" \
  "$HPE_DIR/hpe.py" \
  "$WORKSPACE_ROOT" \
  "$RUN_FOLDER" \
  "$VIDEO_PATH" \
  "$@"

if [[ ! -f "$OUTPUT_DIR/output.mp4" ]]; then
    echo "분석 결과 영상을 찾지 못했습니다: $OUTPUT_DIR/output.mp4"
    exit 1
fi

ffmpeg \
  -y \
  -hide_banner \
  -loglevel error \
  -stats \
  -i "$OUTPUT_DIR/output.mp4" \
  -c:v libx264 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$OUTPUT_DIR/rendered.mp4"
echo "COACH_STAGE_SUCCESS=video_analysis"
