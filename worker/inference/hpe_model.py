# import
import os
import json
from pathlib import Path
import argparse

import cv2
import time
from tqdm import tqdm
from rtmlib import RTMDet, RTMPose

from inference.pose_track import Detection, build_frame_record

# Parser
parser = argparse.ArgumentParser()
parser.add_argument("poc_folder", type=Path)
parser.add_argument("run_folder", type=str)
parser.add_argument(
    "--device",
    choices=["cpu", "cuda", "mps"],
    default="cpu",
)

args = parser.parse_args()

POC_DIR = args.poc_folder
RUN_FOLDER = args.run_folder
DEVICE = args.device

# Roots
DETECTOR_ROOT = POC_DIR / 'models' / "detectors" / "rtmdet-nano-person-320x320"
POSE_ROOT = POC_DIR / 'models' / "pose" / "rtmpose-m-halpe26-384x288"
DATA_ROOT = POC_DIR / "run" / RUN_FOLDER
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

# Funtions
def _infer_image(image_path: Path) -> list[Detection]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"이미지를 읽지 못했습니다: {image_path}")

    det_s = time.perf_counter()
    bboxes = detector(image)
    det_e = time.perf_counter()

    # 중요: 빈 bbox를 RTMPose에 넘기지 않는다.
    if len(bboxes) == 0:
        return [], 0.0, 0.0

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

    return detections, det_e - det_s, pose_e - pose_s

def main():
    previous = None
    frames = []
    det_t, pose_t = 0.0, 0.0


    image_paths = sorted(INPUT_ROOT.glob("*.png"))

    for image_path in tqdm(image_paths, desc="HPE Model"):
        detections, _det_t, _pose_t = _infer_image(image_path)

        det_t += _det_t
        pose_t += _pose_t

        relative_image_path = image_path.resolve().relative_to(
            POC_DIR.resolve()
        )

        frame, previous = build_frame_record(
            image_path=str(relative_image_path),
            detections=detections,
            previous=previous,
            keypoint_threshold=0.5,
        )

        frames.append(frame)

    output_path = OUTPUT_ROOT / "pose_predictions.json"
    output_path.write_text(
        json.dumps({"frames": frames}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"저장 완료: {output_path}")
    print(f"소요 시간 \nDetection : {det_t:.2f}s avg[{det_t / len(image_paths):.4f}s/frames] | HPE : {pose_t:.2f}s avg[{pose_t / len(image_paths):.4f}s/frames]")


if __name__ == "__main__":
    main()
