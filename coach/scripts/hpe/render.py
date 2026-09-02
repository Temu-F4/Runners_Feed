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

    # inputs의 이미지 수와 hpe json의 frame수가 다르다. 왜냐하면 bbox가 화면 안에 들어온 순간부터 hpe를 저장하기 때문이다.
    # 따라서 이미지 저장은 i로 하고 json과의 이미지-hpe 일치는 j로 실행한다.
    j = 0
    for i, image_path in enumerate(tqdm(image_paths, desc="Rendering")):
        img = cv2.imread(image_path)

        # 인덱싱 범위 오류 해결
        if j == len(data["frames"]):
            cv2.imwrite(RENDER_PATH / f"{i+1:08d}.png", img)
            continue

        # 객체 인식 안되면 원본 이미지 입력
        if data["frames"][j]["image_path"].split('/')[-1] != str(image_path).split('/')[-1]:
            cv2.imwrite(RENDER_PATH / f"{i+1:08d}.png", img)
            continue

        user = data["frames"][j]["people"][0]
        j += 1

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