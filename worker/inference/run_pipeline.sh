#!/usr/bin/env bash
set -euo pipefail

CASE_ID="${1:-test1}"

WORKSPACE_DIR="/workspace"
RUN_DIR="$WORKSPACE_DIR/run/$CASE_ID"
INPUT_DIR="$RUN_DIR/inputs"
OUTPUT_DIR="$RUN_DIR/outputs"

mkdir -p "$INPUT_DIR" "$OUTPUT_DIR"

VIDEO_PATH="$(
  find "$RUN_DIR" \
    -maxdepth 1 \
    -type f \
    -iname '*.mp4' \
    -print \
    -quit
)"

if [[ -z "$VIDEO_PATH" ]]; then
  echo "MP4 파일을 찾지 못했습니다: $RUN_DIR"
  exit 1
fi

echo "분석 영상: $VIDEO_PATH"

python -m inference.extract_frames \
  "$VIDEO_PATH" \
  "$INPUT_DIR"

python -m inference.hpe_model \
  "$WORKSPACE_DIR" \
  "$CASE_ID" \
  --device cpu

python -m inference.report \
  "$OUTPUT_DIR/details.json" \
  "$OUTPUT_DIR/pose_predictions.json" \
  "$OUTPUT_DIR/report.json"

python -m inference.render \
  "$INPUT_DIR" \
  "$OUTPUT_DIR"

python -m inference.compose_video \
  "$OUTPUT_DIR/details.json" \
  "$OUTPUT_DIR/rendered" \
  "$OUTPUT_DIR/_rendered.mp4"

ffmpeg \
  -y \
  -hide_banner \
  -loglevel error \
  -stats \
  -i "$OUTPUT_DIR/_rendered.mp4" \
  -c:v libx264 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$OUTPUT_DIR/rendered.mp4"

echo "RTMPOSE_VIDEO_POC=PASS"
echo "결과 폴더: $OUTPUT_DIR"
