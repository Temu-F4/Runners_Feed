# import
import os
import json
from pathlib import Path
import argparse

import cv2
import time
from tqdm import tqdm
from rtmlib import RTMDet, RTMPose

from scripts.hpe.pose_track import Detection, build_frame_record

# Parser
parser = argparse.ArgumentParser()
parser.add_argument("coach_folder", type=Path)
parser.add_argument("run_folder", type=str)
parser.add_argument(
    "--device",
    choices=["cpu", "cuda", "mps"],
    default="cpu",
)

args = parser.parse_args()

COACH_DIR = args.coach_folder
RUN_FOLDER = args.run_folder
DEVICE = args.device

# Roots
DETECTOR_ROOT = COACH_DIR / 'models' / "detectors" / "rtmdet-nano-person-320x320"
POSE_ROOT = COACH_DIR / 'models' / "pose" / "rtmpose-m-halpe26-384x288"
DATA_ROOT = COACH_DIR / "run" / RUN_FOLDER
INPUT_ROOT = DATA_ROOT / "inputs"
OUTPUT_ROOT = DATA_ROOT / "outputs"

os.makedirs(OUTPUT_ROOT, exist_ok=True)


# model
detector = RTMDet(
    onnx_model=DETECTOR_ROOT/"end2end.onnx",
    model_input_size=(320, 320),
    det_mode="human",
    score_thr=0.3,
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

# import json
with open(OUTPUT_ROOT / "details.json", "r", encoding="utf-8") as f:
    details = json.load(f)

width = details["video"]["width"]

# Funtions
def detect_image(image_path: Path) -> list[Detection]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"이미지를 읽지 못했습니다: {image_path}")

    det_s = time.perf_counter()
    bboxes = detector(image)
    det_e = time.perf_counter()

    return image, bboxes, det_e - det_s

def estimate_pose(image, bboxes):
    pose_s = time.perf_counter()
    keypoints, keypoint_scores = pose_model(image, bboxes=bboxes)
    pose_e = time.perf_counter()

    detections = []
    for bbox, person_kpts, person_scores in zip(
        bboxes, keypoints, keypoint_scores
    ):
        detections.append(
            Detection(
                bbox=[float(value) for value in bbox[:4]],
                bbox_score=1.0,  # 아래의 bbox score 주의사항 참고
                keypoints=[
                    [float(x), float(y)]
                    for x, y in person_kpts
                ],
                keypoint_scores=[
                    float(score) for score in person_scores
                ],
            )
        )

    return detections, pose_e - pose_s

def main():
    previous = None
    frames = []
    det_time, pose_time = 0.0, 0.0

    image_paths = sorted(INPUT_ROOT.glob("*.png"))

    for image_path in tqdm(image_paths, desc="HPE Model"):

        image, bboxes, det_t = detect_image(image_path)

        det_time += det_t

        if len(bboxes) == 0:
            continue

        outside_range = (
            bboxes[0][0] < 10
            or bboxes[0][2] > width - 10
        )


        if outside_range:
            if len(frames) < 20:
                # 객체가 인식된 직후 인식 오류가 날 경우
                frames.clear()
                continue
            # 거울 오류 해결
            break
        detections, pose_t = estimate_pose(image, bboxes)

        pose_time += pose_t

        relative_image_path = image_path.resolve().relative_to(
            COACH_DIR.resolve()
        )

        frame, previous = build_frame_record(
            image_path=str(relative_image_path),
            detections=detections,
            previous=previous,
            keypoint_threshold=0.5,
        )

        # 객체 검출 안된 데이터 기록 x
        if frame is None:
            continue

        frames.append(frame)

    output_path = OUTPUT_ROOT / "pose_predictions.json"
    output_path.write_text(
        json.dumps({"frames": frames}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"저장 완료: {output_path}")
    print(f"소요 시간 \nDetection : {det_time:.2f}s avg[{det_time / len(frames):.4f}s/frames] | HPE : {pose_time:.2f}s avg[{pose_time / len(frames):.4f}s/frames]")


if __name__ == "__main__":
    main()
