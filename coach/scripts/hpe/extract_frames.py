import time
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

import cv2


def extract_frames(video_path: Path, output_dir: Path) -> int:
    if output_dir.exists() and any(output_dir.glob("*.png")):
        print(f"기존 프레임이 있습니다: {output_dir}\ndetail.json 생성을 원하시면 {output_dir}을 삭제해주세요.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise RuntimeError(f"영상을 열지 못했습니다: {video_path}")

    count = 0

    try:
        # 영상 정보 기록
        fps = float(video.get(cv2.CAP_PROP_FPS))
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))

        while True:
            success, frame = video.read()
            if not success:
                break

            count += 1
            cv2.imwrite(str(output_dir / f"{count:08d}.png"), frame)
    finally:
        video.release()
    duration_seconds = (
        frame_count / fps
        if fps > 0
        else None
    )

    # 영상 정보 저장
    video_info = {
        "filename": video_path.name,
        "relative_path": str(video_path.relative_to(video_path.parents[2])),
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

    details_path = output_dir.parent / "outputs" / "details.json"

    details_path.write_text(
        json.dumps(
            details,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    start = time.perf_counter()
    count = extract_frames(args.video, args.output)
    end = time.perf_counter()

    print(f"{count}개 프레임 저장 완료: {args.output} | 지연 시간 : {end - start:.2f}s")
