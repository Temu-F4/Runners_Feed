# import
import os
import time
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

import cv2
import numpy as np
from tqdm import tqdm
from rtmlib import RTMDet, RTMPose, draw_bbox, draw_skeleton

from scripts.hpe.pose_track import Detection, build_frame_record
from scripts.hpe.hpe_model import estimate_pose


# Parser
parser = argparse.ArgumentParser()
parser.add_argument("coach_folder", type=Path)
parser.add_argument("run_folder", type=str)
parser.add_argument("video", type=Path)
parser.add_argument(
    "--device",
    choices=["cpu", "cuda", "mps"],
    default="cpu",
)

args = parser.parse_args()

COACH_DIR = args.coach_folder
RUN_FOLDER = args.run_folder
VIDEO_PATH = args.video
DEVICE = args.device

# Roots
DETECTOR_ROOT = COACH_DIR / 'models' / "detectors" / "rtmdet-nano-person-320x320"
POSE_ROOT = COACH_DIR / 'models' / "pose" / "rtmpose-m-halpe26-384x288"
DATA_ROOT = COACH_DIR / "run" / RUN_FOLDER
OUTPUT_ROOT = DATA_ROOT / "outputs"


output_path = OUTPUT_ROOT / "output.mp4"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


# model
detector = RTMDet(
    onnx_model=DETECTOR_ROOT/"end2end.onnx",
    model_input_size=(320, 320),
    det_mode="human",
    score_thr=0.6,      # 객체 감지 정밀도
    nms_thr=0.45,
    backend="onnxruntime",
    device=DEVICE,
)

pose_model = RTMPose(
    onnx_model=POSE_ROOT/"end2end.onnx",
    model_input_size=(288, 384),
    backend="onnxruntime",
    device=DEVICE,
    to_openpose=False,
)


# video

capture = cv2.VideoCapture(str(VIDEO_PATH))
if not capture.isOpened():
    raise RuntimeError(f"입력 영상을 열지 못했습니다: {VIDEO_PATH}")

# 영상 정보 기록
fps = float(capture.get(cv2.CAP_PROP_FPS))
frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

writer = cv2.VideoWriter(
    str(output_path),
    cv2.VideoWriter_fourcc(*"mp4v"),
    fps,
    (width, height)
)
if not writer.isOpened():
    raise RuntimeError(f"출력 영상을 열지 못했습니다: {output_path}")

count = -1

try:
    # 기존 로직의 구현
    previous = None
    frames = []
    det_time, pose_time = 0.0, 0.0
    flag = True

    start = time.perf_counter()
    while True:
        count += 1
        # 이미지 로드
        success, frame = capture.read()
        if not success:
            break

        if flag:
            # HPE model 진입
            det_s = time.perf_counter()
            bboxes = detector(frame)
            det_e = time.perf_counter()

            det_time += det_e - det_s

            if len(bboxes) == 0:
                try:
                    if outside_range == False:
                        while not len(bboxes):
                            detector.score_thr -= 0.1
                            bboxes = detector(frame)
                            if detector.score_thr <= 0:
                                raise RuntimeError("객체가 사라졌습니다.")
                        detector.score_thr = 0.4
                    else: raise Exception
                except:
                    writer.write(frame)
                    continue

            outside_range = (
                bboxes[0][0] < 10
                or bboxes[0][2] > width - 10
            )
            
            if outside_range:
                writer.write(frame)
                if len(frames) < 20:
                    # 객체가 인식된 직후 인식 오류가 날 경우
                    # raise RuntimeError ########
                    continue
                # 거울 오류 해결
                flag = False
                continue

            detections, pose_t = estimate_pose(pose_model, frame, bboxes)
            pose_time += pose_t

            frame_info, previous = build_frame_record(
                frame_num=count,
                detections=detections,
                previous=previous,
                keypoint_threshold=0.5,
            )

            if frame_info is None:
                writer.write(frame)
                continue

            frames.append(frame_info)

            # rendering
            user = frame_info["people"][0]
        
            keypoints = np.asarray(user["keypoints"], dtype=np.float32)[np.newaxis, :]
            scores = np.asarray(user['keypoint_scores'], dtype=np.float32)[np.newaxis, :]

            frame = draw_skeleton(
                frame.copy(),
                keypoints,
                scores,
                openpose_skeleton=False,
                kpt_thr=0.3,
                radius=4,
                line_width=2,
            )
            detector.score_thr = 0.4

        writer.write(frame)
finally:
    capture.release()
    writer.release()
    total_time = time.perf_counter() - start

duration_seconds = (
    frame_count / fps
    if fps > 0
    else None
)

output_path = OUTPUT_ROOT / "pose_predictions.json"
output_path.write_text(
    json.dumps({"frames": frames}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"저장 완료: {output_path}")
print(f"소요 시간 \nDetection : {det_time:.2f}s avg[{det_time / len(frames):.4f}s/frames] | HPE : {pose_time:.2f}s avg[{pose_time / len(frames):.4f}s/frames]")

# 영상 정보 저장
video_info = {
    "filename": VIDEO_PATH.name,
    "relative_path": str(VIDEO_PATH.relative_to(VIDEO_PATH.parents[2])),
    "duration_seconds": duration_seconds,
    "fps": fps,
    "frame_count": frame_count,
    "width": width,
    "height": height,
}

details = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "model": {
        "detector": "RTMDet-nano",
        "pose": "RTMPose-M Halpe-26",
        "backend": "onnxruntime",
    },
    "video": video_info,
}

details_path = OUTPUT_ROOT.parent / "outputs" / "details.json"

details_path.write_text(
    json.dumps(
        details,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print(f"영상 입력, Human Pose Estimation, rendering 전체 소요 시간: {total_time:.2f}s")