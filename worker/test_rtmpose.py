from pathlib import Path
from urllib.request import urlretrieve
import time

from mmpose.apis import MMPoseInferencer


input_dir = Path("/data/input")
output_dir = Path("/data/output")
image_path = input_dir / "test-person.jpg"

input_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)

if not image_path.exists():
    print("[1/4] Downloading official MMPose test image...")
    urlretrieve(
        "https://raw.githubusercontent.com/open-mmlab/mmpose/main/"
        "tests/data/coco/000000000785.jpg",
        image_path,
    )

print("[2/4] Loading RTMPose Halpe26 on CPU...")
load_started = time.perf_counter()
inferencer = MMPoseInferencer(pose2d="body26", device="cpu")
load_seconds = time.perf_counter() - load_started

print("[3/4] Running inference...")
infer_started = time.perf_counter()
result = next(
    inferencer(
        str(image_path),
        out_dir=str(output_dir),
        show=False,
        draw_bbox=True,
    )
)
infer_seconds = time.perf_counter() - infer_started

predictions = result.get("predictions", [])
instances = predictions[0] if predictions and isinstance(predictions[0], list) else predictions

if not instances:
    raise RuntimeError("No person was detected.")

keypoints = instances[0].get("keypoints", [])

print("[4/4] Result")
print(f"Detected people: {len(instances)}")
print(f"Keypoints: {len(keypoints)}")
print(f"Model loading: {load_seconds:.2f} seconds")
print(f"Inference: {infer_seconds:.2f} seconds")

if len(keypoints) != 26:
    raise RuntimeError(f"Expected 26 keypoints, but received {len(keypoints)}.")

print("RTMPOSE_HALPE26_TEST=PASS")
