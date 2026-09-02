import json
import argparse
from pathlib import Path

import cv2
from tqdm.auto import tqdm


def compose_video(
    details_path: Path,
    rendered_dir: Path,
    output_path: Path,
) -> None:
    # details.json 읽기
    try:
        with details_path.open("r", encoding="utf-8") as file:
            details = json.load(file)
    except Exception as e:
        print('='*60)
        print("inputs 폴더 삭제 후 다시 실행시켜주세요")
        print('='*60)
        raise e

    video_info = details.get("video")

    if video_info is None:
        raise ValueError("details.json에 video 정보가 없습니다.")

    fps = float(video_info["fps"])
    width = int(video_info["width"])
    height = int(video_info["height"])

    if fps <= 0:
        raise ValueError(f"올바르지 않은 FPS입니다: {fps}")

    # 렌더링된 프레임 검색
    image_paths = sorted(rendered_dir.glob("*.png"))

    if not image_paths:
        raise FileNotFoundError(
            f"렌더링된 PNG 이미지를 찾지 못했습니다: {rendered_dir}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # MP4 인코더 설정
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    writer = cv2.VideoWriter(
        str(output_path),
        fourcc,
        fps,
        (width, height),
    )

    if not writer.isOpened():
        raise RuntimeError(f"영상 출력 파일을 열지 못했습니다: {output_path}")

    try:
        for image_path in tqdm(image_paths, desc="Composing video"):
            frame = cv2.imread(str(image_path))

            if frame is None:
                raise RuntimeError(
                    f"이미지를 읽지 못했습니다: {image_path}"
                )

            frame_height, frame_width = frame.shape[:2]

            if (frame_width, frame_height) != (width, height):
                raise ValueError(
                    f"프레임 해상도가 다릅니다: {image_path}\n"
                    f"기대값: {width}x{height}, "
                    f"실제값: {frame_width}x{frame_height}"
                )

            writer.write(frame)

    finally:
        writer.release()

    duration = len(image_paths) / fps

    print(f"영상 합성 완료: {output_path.resolve()}")
    print(f"FPS: {fps}")
    print(f"해상도: {width}x{height}")
    print(f"프레임 수: {len(image_paths)}")
    print(f"영상 길이: {duration:.2f}초")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="details.json과 렌더링된 이미지로 무음 MP4를 생성합니다."
    )

    parser.add_argument(
        "details",
        type=Path,
        help="details.json 경로",
    )
    parser.add_argument(
        "rendered",
        type=Path,
        help="렌더링된 PNG 폴더",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="출력 MP4 경로",
    )

    args = parser.parse_args()

    compose_video(
        details_path=args.details,
        rendered_dir=args.rendered,
        output_path=args.output,
    )