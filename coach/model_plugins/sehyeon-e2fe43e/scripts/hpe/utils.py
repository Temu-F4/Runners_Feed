# import
import os
import json
import argparse
from pathlib import Path
from typing import Optional
from collections import deque
from dataclasses import dataclass
from collections.abc import Sequence

import cv2
import time
import numpy as np
import pandas as pd
from tqdm import tqdm
from rtmlib import RTMDet, RTMPose, draw_skeleton


@dataclass(frozen=True)
class Detection:
    bbox: list[float]
    bbox_score: float
    keypoints: list[list[float]]
    keypoint_scores: list[float]


@dataclass(frozen=True)
class TrackState:
    bbox: list[float]
    keypoints: list[list[float]]


def _intersection_over_union(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _primary_index(detections: list[Detection], previous: Optional[TrackState]) -> int:
    if previous is None:
        return max(range(len(detections)), key=lambda index: detections[index].bbox_score)
    return max(
        range(len(detections)),
        key=lambda index: (
            _intersection_over_union(detections[index].bbox, previous.bbox),
            detections[index].bbox_score,
        ),
    )


def _person_record(
    detection: Detection,
    track_id: Optional[int],
    previous: Optional[TrackState],
    keypoint_threshold: float,
) -> dict:
    observed = [score >= keypoint_threshold for score in detection.keypoint_scores]
    imputed_keypoints: list[Optional[list[float]]] = [None] * len(detection.keypoints)
    if previous is not None:
        imputed_keypoints = [
            None if is_observed else previous.keypoints[index]
            for index, is_observed in enumerate(observed)
        ]
    return {
        "track_id": track_id,
        "bbox": detection.bbox,
        "bbox_score": detection.bbox_score,
        "keypoints": detection.keypoints,
        "keypoint_scores": detection.keypoint_scores,
        "observed": observed,
        "imputed_keypoints": imputed_keypoints,
    }


def build_frame_record(
    frame_num: int,
    detections: list[Detection],
    previous: Optional[TrackState],
    keypoint_threshold: float,
) -> tuple[dict, Optional[TrackState]]:
    """Build one frame result without changing the model's raw keypoint output."""
    if not detections:
        # return {"image_path": image_path, "people": []}, None
        return None, None

    primary_index = _primary_index(detections, previous)
    people = [
        _person_record(
            detection,
            0 if index == primary_index else None,
            previous if index == primary_index else None,
            keypoint_threshold,
        )
        for index, detection in enumerate(detections)
    ]
    primary = detections[primary_index]
    return (
        {"frame_num": frame_num, "people": people},
        TrackState(bbox=primary.bbox, keypoints=primary.keypoints),
    )

def _primary_person(frame_info: dict | None) -> dict | None:
    if frame_info is None:
        return None

    return next(
        (
            person
            for person in frame_info.get("people", [])
            if person.get("track_id") == 0
        ),
        None,
    )

def interpolate_center(
    frame_infos: Sequence[dict | None],
) -> dict | None:
    """
    5개 프레임 중 가운데 프레임(frame_infos[2])의
    저신뢰 키포인트를 보간한다.

    - 정상 좌표 3개 이상: 신뢰도 가중 2차 보간
    - 앞뒤 정상 좌표 2개: 선형 보간
    - 한쪽 좌표만 존재: 보간하지 않음
    - 가운데 frame_info를 직접 수정하고 반환
    """
    if len(frame_infos) != 5:
        raise ValueError(
            "interpolate_center()에는 정확히 5개 프레임이 필요합니다."
        )

    center_info = frame_infos[2]
    center_user = _primary_person(center_info)

    if center_info is None or center_user is None:
        return center_info

    center_keypoints = center_user["keypoints"]
    center_observed = center_user["observed"]
    keypoint_count = len(center_keypoints)

    if len(center_observed) != keypoint_count:
        raise ValueError(
            "가운데 프레임의 keypoints와 observed 길이가 다릅니다."
        )

    # 기존의 직전 좌표 대입 결과가 남아 있지 않도록 초기화
    center_user["imputed_keypoints"] = [None] * keypoint_count
    center_frame_num = int(center_info["frame_num"])

    for keypoint_index in range(keypoint_count):
        # 정상 관측된 가운데 좌표는 수정하지 않음
        if center_observed[keypoint_index]:
            continue

        times = []
        points = []
        weights = []

        for window_index, frame_info in enumerate(frame_infos):
            if window_index == 2:
                continue

            user = _primary_person(frame_info)
            if user is None:
                continue

            # 보간된 좌표가 아닌 observed raw 좌표만 사용
            if not user["observed"][keypoint_index]:
                continue

            point = np.asarray(
                user["keypoints"][keypoint_index],
                dtype=float,
            )

            if point.shape != (2,) or not np.all(np.isfinite(point)):
                continue

            times.append(
                float(frame_info["frame_num"] - center_frame_num)
            )
            points.append(point)
            weights.append(
                max(
                    float(
                        user["keypoint_scores"][keypoint_index]
                    ),
                    1e-6,
                )
            )

        if not times:
            continue

        times_array = np.asarray(times, dtype=float)
        points_array = np.asarray(points, dtype=float)

        has_left = np.any(times_array < 0)
        has_right = np.any(times_array > 0)

        # 양쪽 좌표가 없으면 보간이 아니라 외삽이 되므로 사용하지 않음
        if not (has_left and has_right):
            continue

        result = None

        # 정상 좌표가 3개 이상이면 2차함수 사용
        if len(times_array) >= 3:
            try:
                weights_array = np.asarray(weights, dtype=float)

                x_curve = np.polyfit(
                    times_array,
                    points_array[:, 0],
                    deg=2,
                    w=weights_array,
                )
                y_curve = np.polyfit(
                    times_array,
                    points_array[:, 1],
                    deg=2,
                    w=weights_array,
                )

                result = np.array([
                    np.polyval(x_curve, 0.0),
                    np.polyval(y_curve, 0.0),
                ])
            except (
                ValueError,
                FloatingPointError,
                np.linalg.LinAlgError,
            ):
                result = None

        if result is not None and not np.all(np.isfinite(result)):
            result = None

        # 2차 보간이 불가능하면 가장 가까운 앞뒤 좌표로 선형 보간
        if result is None:
            left_candidates = np.flatnonzero(times_array < 0)
            right_candidates = np.flatnonzero(times_array > 0)

            left_index = left_candidates[
                np.argmax(times_array[left_candidates])
            ]
            right_index = right_candidates[
                np.argmin(times_array[right_candidates])
            ]

            left_time = times_array[left_index]
            right_time = times_array[right_index]

            ratio = -left_time / (right_time - left_time)

            result = (
                points_array[left_index]
                + ratio
                * (
                    points_array[right_index]
                    - points_array[left_index]
                )
            )

        if np.all(np.isfinite(result)):
            center_user["imputed_keypoints"][
                keypoint_index
            ] = result.tolist()

    return center_info


def detect_image(model, image_path: Path) -> list[Detection]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"이미지를 읽지 못했습니다: {image_path}")

    det_s = time.perf_counter()
    bboxes = model(image)
    det_e = time.perf_counter()

    return image, bboxes, det_e - det_s


def estimate_pose(model, image, bboxes):
    pose_s = time.perf_counter()
    keypoints, keypoint_scores = model(image, bboxes=bboxes)
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

def render_and_write(entry: dict, writer) -> None:
    """
    deque에서 꺼낸 프레임을 렌더링하고 정확히 한 번 저장한다.

    entry:
        {
            "frame": np.ndarray,
            "frame_info": dict | None
        }
    """
    frame = entry["frame"]
    frame_info = entry.get("frame_info")

    user = _primary_person(frame_info)

    # HPE 결과 또는 대표 인물이 없으면 원본 프레임 저장
    if user is None:
        writer.write(frame)
        return

    raw_keypoints = np.asarray(
        user["keypoints"],
        dtype=np.float32,
    )
    render_scores = np.asarray(
        user["keypoint_scores"],
        dtype=np.float32,
    ).copy()

    observed = np.asarray(
        user.get(
            "observed",
            [True] * len(raw_keypoints),
        ),
        dtype=bool,
    )
    imputed_keypoints = user.get(
        "imputed_keypoints",
        [None] * len(raw_keypoints),
    )

    if (
        raw_keypoints.ndim != 2
        or raw_keypoints.shape[1] != 2
        or len(render_scores) != len(raw_keypoints)
        or len(observed) != len(raw_keypoints)
        or len(imputed_keypoints) != len(raw_keypoints)
    ):
        raise ValueError(
            f"frame_num={frame_info.get('frame_num')}: "
            "렌더링 키포인트 데이터 길이가 일치하지 않습니다."
        )

    render_keypoints = raw_keypoints.copy()

    for index, imputed in enumerate(imputed_keypoints):
        if observed[index] or imputed is None:
            continue

        point = np.asarray(imputed, dtype=np.float32)

        # 잘못된 보간값이면 raw 좌표와 원래 점수를 유지
        if point.shape != (2,) or not np.all(np.isfinite(point)):
            continue

        render_keypoints[index] = point

        # JSON 원본 confidence는 유지하고 렌더링에서만 표시
        render_scores[index] = 1.0

    rendered_frame = draw_skeleton(
        frame.copy(),
        render_keypoints[np.newaxis, :],
        render_scores[np.newaxis, :],
        openpose_skeleton=False,
        kpt_thr=0.3,
        radius=4,
        line_width=2,
    )

    writer.write(rendered_frame)

def enqueue_and_write(
    pending: deque,
    frame: np.ndarray,
    frame_info: dict | None,
    writer,
) -> None:
    pending.append({
        "frame": frame,
        "frame_info": frame_info,
    })

    if len(pending) < 5:
        return

    interpolate_center([
        item["frame_info"]
        for item in pending
    ])

    oldest = pending.popleft()
    render_and_write(oldest, writer)
    return oldest.get("frame_info")
