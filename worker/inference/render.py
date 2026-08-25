import time
import json
import argparse
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm
from rtmlib import draw_bbox, draw_skeleton

def render(img_dir: Path, output_dir: Path) -> None:
    # 이미지를 for문으로 반복
    # 각 이미지별로 해당되는 hpe데이터를 입력하고 저장

    # 예외 처리
    RENDER_PATH = output_dir / "rendered"
    if RENDER_PATH.exists() and any(RENDER_PATH.glob("*.png")):
        print(f"이미 렌더링된 작업물입니다.: {RENDER_PATH}")
        return 0

    # import json
    with open(output_dir / "pose_predictions.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    
    RENDER_PATH.mkdir(parents=True, exist_ok=True)
    image_paths = sorted(img_dir.glob("*.png"))

    for i, image_path in enumerate(tqdm(image_paths, desc="Rendering")):
        img = cv2.imread(image_path)

        # 예외 처리
        if len(image_paths) != len(data["frames"]):
            print("이미지 수와 모델의 출력 프레임 데이터 수가 맞지 않음. 확인 필요.")
            raise Exception
        if data["frames"][i]["people"] == []:
            # 사람이 화면에 잡히지 않음
            continue
        user = data["frames"][i]["people"][0]
        keypoints = np.asarray(user["keypoints"], dtype=np.float32)[np.newaxis, :]
        scores = np.asarray(user['keypoint_scores'], dtype=np.float32)[np.newaxis, :]

        result = draw_skeleton(
            img.copy(),
            keypoints,
            scores,
            openpose_skeleton=False,
            kpt_thr=0.3,
            radius=4,
            line_width=2,
        )
        cv2.imwrite(RENDER_PATH / f"{i+1:08d}.png", result)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("frames", type=Path)
    parser.add_argument("hpe_data", type=Path)
    args = parser.parse_args()

    start = time.perf_counter()
    render(args.frames, args.hpe_data)
    end = time.perf_counter()

    print(f"이미지 렌더링 완료.\n소요 시간 : {end - start:.2f}s")