import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks, savgol_filter
from typing import Pattern

class PoseSequence:
    def __init__(self, pose_data: dict, detail_data: dict, user_data: dict):
        """
        json 데이터를 불러온 뒤 바로 이 클래스의 인자로 입력하면 됩니다.
        y좌표는 0의 기준이 위에서 아래로 바뀝니다.
        """
        # bbox, keypoints들의 y좌표 반전.
        df = hpe2pd(pose_data)
        _cols = df.columns[df.columns.str.contains("_y|up|down")]
        df.loc[:, _cols] = detail_data["video"]["height"] - df[_cols]

        # direction
        dir_index = 0 if (df["nose_x"] - df["neck_x"])[0] > 0 else 1

        self.df = df
        self.details = detail_data
        self.user = user_data["user"]
        self.direction = "left" if dir_index else "right"
        self.strides = None
        self.m_per_pixel = None

    def cal_stride(self) -> None:
        """
        self.stride에 1스트라이드의 시작, 끝 프레임 기록
        """
        if self.strides is not None:
            print('이미 stride가 계산되어 있습니다.')
            print('Stride :', self.strides)
            return

        dir = self.direction

        left_knee_angle = self.joint_angle(f"{dir}_knee", negative=True)
        y = np.asarray(left_knee_angle, dtype=float)
        y_smooth = savgol_filter(
            y,
            window_length=5,
            polyorder=2
        )
        alpha = 0
        distance = self.details["video"]['fps'] // 6
        for i in range(10):
            if i == 9: print("러닝 패턴 분석 시도 횟수가 10회를 넘었습니다.")

            # 데이터 범위에 비례해 prominence 설정
            signal_range = np.percentile(y_smooth, 95) - np.percentile(y_smooth, 5)
            prominence = signal_range * (0.10 + alpha)    # 곱해지는 숫자가 클수록 큰 봉우리만 검출

            # 최댓값
            max_indices, max_properties = find_peaks(
                y_smooth,
                prominence=prominence,
                distance=distance,
            )

            # 최솟값: 신호에 -를 붙여서 봉우리로 변환
            min_indices, min_properties = find_peaks(
                -y_smooth,
                prominence=prominence,
                distance=distance,
            )

            _max = {
                "frame": max_indices,
                "value": y_smooth[max_indices],
                "class": np.ones_like(max_indices)
            }
            _min = {
                "frame": min_indices,
                "value": y_smooth[min_indices],
                "class": np.zeros_like(min_indices)
            }
            extremum = pd.concat([pd.DataFrame(_max), pd.DataFrame(_min)]).sort_values('frame')

            # 올바른 스트라이드 검출
            if len(extremum) < 4:
                print("러닝 리듬 분석에 실패했습니다.")
                alpha -= 0.02
                distance = max(1, distance - 2)
                continue

            flag = False
            for i in range(1, len(extremum)):
                previous = extremum["class"].iloc[i - 1]
                current = extremum["class"].iloc[i]

                if {previous, current} != {0, 1}:
                    print(
                        f"예외: {i-1}, {i}행의 값이 {previous}, {current}입니다.\n올바른 스트라이드가 검출되지 않았습니다. 검출 파라미터 변경 필요."
                    )
                    alpha += 0.02
                    distance = max(1, distance - 1)
                    flag = True
                    break
            if flag:
                continue

            start_index = (0 if y_smooth[max_indices[0]] > y_smooth[max_indices[1]] else 1)
            for i in range(len(max_indices) // 2 - 1):
                if not y_smooth[max_indices[2 * i + start_index]] > y_smooth[max_indices[2 * i + 1 + start_index]]:
                    raise RuntimeError("무릎 각도에서 예상치 못한 예외 발생.")

            start_frame = max_indices[start_index]
            start_position = np.flatnonzero(
                extremum["frame"].to_numpy() == start_frame
            )[0]

            # start_frame 행이 1이 되도록 1~4 반복
            extremum.index = (
                (np.arange(len(extremum)) - start_position) % 4
            ) + 1

            self.strides = extremum
            return extremum

    def pixel2m(self):
        """
        사용자의 키 정보를 사용해 1pixel을 m단위로 변경한다.
        이 때 사용하는 이미지는 TD시점이다.
        """
        def _point(df, name):
            return df[[f"{name}_x", f"{name}_y"]].to_numpy(dtype=float)
        def _distance(a, b):
            return np.linalg.norm(a - b, axis=0)

        # 사용할 이미지 선택
        image = self.df.loc[np.asarray(self.strides.loc[2]['frame']).reshape(-1)[0]]

        ankle = _point(image, f"{self.direction}_ankle")
        knee = _point(image, f"{self.direction}_knee")
        hip = _point(image, f"{self.direction}_hip")

        hip_center = _point(image, "hip_center")
        neck = _point(image, "neck")
        head = _point(image, "head")

        leg_length = (
            _distance(ankle, knee)
            + _distance(knee, hip)
        )
        torso_length = _distance(hip_center, neck)
        head_length = _distance(neck, head)

        height_px = leg_length + torso_length + head_length
        self.m_per_pixel = self.user['height'] / height_px
        print(f"사용자의 키를 기반으로 계산한 픽셀당 meter는 {self.m_per_pixel} / pixel 입니다.")

        return height_px


    def gct(self):
        """
        {side}의 heel이 지면에 접촉하고 big_toe가 지면에서 떼어지는 순간까지의 인덱스 출력
        next는 스트라이드의 구간을 한 단계 미뤄야 할 가능성이 있기 때문에 그 때의 설계를 위해 남긴 더미.
        """
        _df = self.strides.loc[[2, 4]].sort_values('frame')
        if _df.index[0] == 4:
            _df = _df.iloc[1:]
        if len(_df) % 2:
            _df = _df.iloc[:-1]

        steps = [
            _df.iloc[i:i + 2]["frame"].to_list()
            for i in range(0, len(_df), 2)
        ]

        if self.m_per_pixel is None:
            self.pixel2m()

        res = []
        for start, end in steps:
            df = self.df.loc[start:end+10]   # 무릎 각도와 y값을 동시 반영, end는 3프레임의 여유를 두었다.

            heel = f"{self.direction}_heel"
            td = int(df[f"{heel}_y"].idxmin())

            toe = f"{self.direction}_big_toe"
            min_value = df[f"{toe}_y"].min()

            inside = df[f"{toe}_y"].between(min_value, min_value + 0.01 / self.m_per_pixel)
            _to = df.index[~inside & inside.shift(1, fill_value=False)].to_numpy()
            # 최소값 도달 이후 첫 번째 프레임
            try:
                to = int(_to[_to > df[f"{toe}_y"].idxmin()][-1])
            except:
                continue

            assert td < to, print(res, td, to)# "지면 착지 분석에 오류가 발생했습니다. 카메라 흔들림이 있었는지 확인 부탁드립니다."
            res.append([td, to])
        return res

    def joint_angle(self, keypoint, smooth=False, negative=False):
        """관절각을 계산한다. negative=True이면 180° - 관절각을 반환한다.
        keypoint는 두 가지 형식이 가능하다.
        1. 좌 우 무릎 혹은 팔꿈치
        2. 원하는 3개의 keypoint -> 중간 keypoint의 각도 출력
        Examples:
            ps.joint_angle("left_knee", negative=True)
            ps.joint_angle(("left_hip", "left_knee", "left_ankle"), negative=True)
        """

        # knee_flexion_angle과 동일하게 근위 관절, 원위 관절 순서로 둔다.
        joint_list = {
            "left_knee": ("left_hip", "left_ankle"),
            "right_knee": ("right_hip", "right_ankle"),
            "left_elbow": ("left_shoulder", "left_wrist"),
            "right_elbow": ("right_shoulder", "right_wrist"),
        }

        if keypoint not in joint_list:
            try:
                start_name, keypoint, end_name = keypoint
            except:
                raise RuntimeError("keypoint의 입력 형식 확인 부탁드립니다.")
        else:
            start_name, end_name = joint_list[keypoint]

        def _point(name):
            return self.df[
                [f"{name}_x", f"{name}_y"]
            ].to_numpy(dtype=float)

        center = _point(keypoint)

        # 중심 관절에서 양쪽 관절로 향하는 벡터
        start = _point(start_name) - center
        end = _point(end_name) - center

        # 내적은 각도의 크기, 외적은 회전 방향 계산에 사용
        dot = np.sum(start * end, axis=1)
        cross = (
            start[:, 0] * end[:, 1]
            - start[:, 1] * end[:, 0]
        )

        # 반시계방향 기준 각도 계산.
        signed_angle = np.degrees(np.arctan2(cross, dot))

        # 관절이 접히는 방향에 따라 각도 방향 변경
        if signed_angle.mean() < 0:
            signed_angle = -signed_angle

        # arctan의 치역 문제 해결
        result = signed_angle + np.where(signed_angle >= 0, 0.0, 360)

        if negative: result = 180 - result
        result[np.isclose(result, 0.0, atol=1e-8)] = 0.0

        if smooth:
            result = savgol_filter(
                np.asarray(result, dtype=float),
                window_length=5,
                polyorder=2
            )

        return result

    # def stride_length(self):



Halpe_26_keypoints = {
    0: "nose",
    1: "left_eye",
    2: "right_eye",
    3: "left_ear",
    4: "right_ear",
    5: "left_shoulder",
    6: "right_shoulder",
    7: "left_elbow",
    8: "right_elbow",
    9: "left_wrist",
    10: "right_wrist",
    11: "left_hip",
    12: "right_hip",
    13: "left_knee",
    14: "right_knee",
    15: "left_ankle",
    16: "right_ankle",
    17: "head",
    18: "neck",
    19: "hip_center",
    20: "left_big_toe",
    21: "right_big_toe",
    22: "left_small_toe",
    23: "right_small_toe",
    24: "left_heel",
    25: "right_heel",
}

def hpe2pd(pose_data: dict) -> pd.DataFrame:
    """
    hpe json 데이터를 pandas DataFrame으로 변경
    Returns:
        pd.DataFrame has bbox(4), keypoints(26)
    """
    rows = []

    for frame in pose_data["frames"]:
        row = {}

        if frame['people'] == []:
            # 사람이 포착되지 않음.
            continue
        primary = next(
            (
                person
                for person in frame["people"]
                if person.get("track_id") == 0
            ),
            None,
        )
        if primary is None: continue

        raw_keypoints = primary["keypoints"]

        observed = primary.get(
            "observed",
            [True] * len(raw_keypoints),
        )

        imputed_keypoints = primary.get(
            "imputed_keypoints",
            [None] * len(raw_keypoints),
        )

        if not (
            len(raw_keypoints)
            == len(observed)
            == len(imputed_keypoints)
        ):
            raise ValueError(
                f"frame_num={frame.get('frame_num')}: "
                "keypoint 데이터 길이가 일치하지 않습니다."
            )

        for index, raw_xy in enumerate(raw_keypoints):
            if observed[index]:
                x, y = raw_xy
            elif imputed_keypoints[index] is not None:
                x, y = imputed_keypoints[index]
            else:
                # 기존 파이프라인 호환을 위한 fallback
                x, y = raw_xy

            keypoint_name = Halpe_26_keypoints[index]
            row[f"{keypoint_name}_x"] = x
            row[f"{keypoint_name}_y"] = y

        rows.append(row)

    return pd.DataFrame.from_records(rows)

def vel_acc(df: pd.DataFrame, keypoints: list[str] = None,fps: float = 60.0):
    """
    정해진 형식의 df에서 구하고자 하는 키포인트의 속력(vel)과 가속력(acc)를 구한다.
    Returns:
        pd.DataFrame
    """
    if fps <= 0:
        raise ValueError("fps는 0보다 커야 합니다.")

    if keypoints is None:
        keypoints = list(Halpe_26_keypoints.values())

    dt = 1 / fps

    res = pd.DataFrame()

    for key in keypoints:
        vx = df[f"{key}_x"].diff() / dt
        vy = df[f"{key}_y"].diff() / dt
        ax = vx.diff() / dt
        ay = vy.diff() / dt
        res[f"{key}_vel"] = np.hypot(vx, vy)
        res[f"{key}_acc"] = np.hypot(ax, ay)

    return res.iloc[2:]

def visualize_frame(_df: pd.DataFrame, points: list[int]=None) -> None:
    if type(_df) == pd.Series:
        _df = _df.to_frame()

    fig, axes = plt.subplots(figsize=(12, 6))
    for col in _df.columns:
        axes.plot(_df[col], label=col, linewidth=1.5)
        if points:
            for point in points:
                axes.scatter(point, _df.loc[point, col])
    axes.set_title("Time Series Analysis")
    axes.set_xlabel("Time (s)")
    axes.set_ylabel("pixel")
    axes.legend()
    axes.grid(alpha=0.3)

    fig.tight_layout()
    plt.show()

def visualize_xy(_df: pd.DataFrame) -> None:
    if type(_df) == pd.Series:
        raise RuntimeError("x, y가 주어져야 합니다.")
    columns = set('_'.join(col.split('_')[:-1]) for col in _df.columns)

    fig, axes = plt.subplots(figsize=(12, 6))
    for col in columns:
        axes.plot(_df[f"{col}_x"], _df[f"{col}_y"], label=col, linewidth=1.5)
    axes.set_title("Trace Analysis")
    axes.set_xlabel("x")
    axes.set_ylabel("y")
    axes.legend()
    axes.grid(alpha=0.3)

    fig.tight_layout()
    plt.show()

def show_video_frames(
    video_path,
    frames,
    hpe_start_frame=0,
    *,
    columns=2,
):
    """
    HPE 기준 프레임을 원본 영상 프레임으로 변환해 출력한다.

    Args:
        video_path:
            원본 영상 경로
        frames:
            HPE 기준 프레임 번호.
            정수, 리스트, 또는 ps.gct()의 [[td, to], ...] 형식
        hpe_start_frame:
            원본 영상에서 HPE 분석이 시작된 프레임 번호
        columns:
            이미지 출력 열 개수

    Returns:
        list[np.ndarray]:
            RGB 형식의 프레임 이미지
    """
    video_path = Path(video_path)

    if not video_path.is_file():
        raise FileNotFoundError(
            f"영상 파일이 없습니다: {video_path}"
        )

    try:
        hpe_frames = np.asarray(
            frames,
            dtype=float,
        ).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "frames는 정수 또는 정수 배열이어야 합니다."
        ) from exc

    if hpe_frames.size == 0:
        raise ValueError("확인할 프레임이 없습니다.")

    if (
        not np.all(np.isfinite(hpe_frames))
        or not np.all(hpe_frames == np.floor(hpe_frames))
    ):
        raise ValueError("프레임 번호는 유한한 정수여야 합니다.")

    hpe_frames = hpe_frames.astype(int)

    # HPE 기준 프레임 → 원본 영상 프레임
    video_frames = hpe_frames + int(hpe_start_frame)

    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise RuntimeError(
            f"영상을 열지 못했습니다: {video_path}"
        )

    images = []

    try:
        frame_count = int(
            capture.get(cv2.CAP_PROP_FRAME_COUNT)
        )
        fps = float(
            capture.get(cv2.CAP_PROP_FPS)
        )

        invalid = video_frames[
            (video_frames < 0)
            | (video_frames >= frame_count)
        ]

        if invalid.size:
            raise IndexError(
                f"영상 프레임 범위를 벗어났습니다: "
                f"{invalid.tolist()} "
                f"(유효 범위: 0~{frame_count - 1})"
            )

        for video_frame in video_frames:
            capture.set(
                cv2.CAP_PROP_POS_FRAMES,
                int(video_frame),
            )

            success, bgr_image = capture.read()

            if not success:
                raise RuntimeError(
                    f"{video_frame}번 프레임을 읽지 못했습니다."
                )

            rgb_image = cv2.cvtColor(
                bgr_image,
                cv2.COLOR_BGR2RGB,
            )
            images.append(rgb_image)

    finally:
        capture.release()

    columns = max(
        1,
        min(int(columns), len(images)),
    )
    rows = int(np.ceil(len(images) / columns))

    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(5 * columns, 4 * rows),
    )
    axes = np.atleast_1d(axes).reshape(-1)

    for axis, image, hpe_frame, video_frame in zip(
        axes,
        images,
        hpe_frames,
        video_frames,
    ):
        seconds = (
            video_frame / fps
            if fps > 0
            else float("nan")
        )

        axis.imshow(image)
        axis.set_title(
            f"HPE {hpe_frame} → "
            f"video {video_frame} "
            f"({seconds:.3f}s)"
        )
        axis.axis("off")

    for axis in axes[len(images):]:
        axis.axis("off")

    figure.tight_layout()
    plt.show()

    return images
