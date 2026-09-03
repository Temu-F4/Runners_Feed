from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any


TARGET_FPS = 10.0


def _primary_person(frame: dict[str, Any]) -> dict[str, Any] | None:
    people = frame.get("people", [])
    if not isinstance(people, list):
        return None
    return next(
        (
            person
            for person in people
            if isinstance(person, dict) and person.get("track_id") == 0
        ),
        None,
    )


def _source_frame_index(frame: dict[str, Any], fallback: int) -> int:
    image_path = frame.get("image_path")
    if isinstance(image_path, str):
        try:
            return max(0, int(Path(image_path).stem) - 1)
        except ValueError:
            pass
    return fallback


def build_skeleton(run_dir: Path, target_fps: float = TARGET_FPS) -> dict:
    output_dir = run_dir / "outputs"
    details = json.loads(
        (output_dir / "details.json").read_text(encoding="utf-8")
    )
    predictions = json.loads(
        (output_dir / "pose_predictions.json").read_text(encoding="utf-8")
    )
    video = details.get("video", {})
    width = float(video.get("width") or 0)
    height = float(video.get("height") or 0)
    source_fps = float(video.get("fps") or 0)
    if width <= 0 or height <= 0 or source_fps <= 0:
        raise ValueError("Video width, height, and fps must be positive")
    if target_fps <= 0:
        raise ValueError("Target fps must be positive")

    minimum_gap = 1.0 / min(target_fps, source_fps)
    last_time = -minimum_gap
    frames = []
    source_frames = predictions.get("frames", [])
    if not isinstance(source_frames, list):
        raise ValueError("pose_predictions.json frames must be a list")

    for fallback, frame in enumerate(source_frames):
        if not isinstance(frame, dict):
            continue
        person = _primary_person(frame)
        if person is None:
            continue
        keypoints = person.get("keypoints", [])
        scores = person.get("keypoint_scores", [])
        if not isinstance(keypoints, list) or not isinstance(scores, list):
            continue

        frame_index = _source_frame_index(frame, fallback)
        timestamp = frame_index / source_fps
        if timestamp - last_time + 1e-9 < minimum_gap:
            continue

        compact_keypoints = []
        for keypoint, score in zip(keypoints, scores):
            if not isinstance(keypoint, list) or len(keypoint) < 2:
                continue
            compact_keypoints.append(
                [
                    round(min(1.0, max(0.0, float(keypoint[0]) / width)), 5),
                    round(min(1.0, max(0.0, float(keypoint[1]) / height)), 5),
                    round(min(1.0, max(0.0, float(score))), 4),
                ]
            )

        if compact_keypoints:
            frames.append(
                {
                    "t_ms": round(timestamp * 1000),
                    "keypoints": compact_keypoints,
                }
            )
            last_time = timestamp

    return {
        "schema_version": "skeleton-1.0",
        "pose_model": "halpe26",
        "coordinate_space": "normalized",
        "fps": min(target_fps, source_fps),
        "duration_ms": round(float(video.get("duration_seconds") or 0) * 1000),
        "frames": frames,
    }


def write_skeleton(run_dir: Path) -> Path:
    output_path = run_dir / "outputs" / "skeleton.json.gz"
    payload = json.dumps(
        build_skeleton(run_dir),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    with gzip.open(output_path, "wb", compresslevel=9) as output:
        output.write(payload)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(write_skeleton(args.run_dir))


if __name__ == "__main__":
    main()
