"""Stable, JSON-safe tracking metadata around raw RTMPose predictions."""

from dataclasses import dataclass
from typing import Optional


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
    image_path: str,
    detections: list[Detection],
    previous: Optional[TrackState],
    keypoint_threshold: float,
) -> tuple[dict, Optional[TrackState]]:
    """Build one frame result without changing the model's raw keypoint output."""
    if not detections:
        return {"image_path": image_path, "people": []}, None

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
        {"image_path": image_path, "people": people},
        TrackState(bbox=primary.bbox, keypoints=primary.keypoints),
    )
