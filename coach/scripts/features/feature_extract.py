import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks, savgol_filter
from typing import Pattern

from utils import *

# Parser
parser = argparse.ArgumentParser()
parser.add_argument("coach_folder", type=Path)
parser.add_argument("run_folder", type=str)
args = parser.parse_args()

COACH_DIR = args.coach_folder
RUN_FOLDER = args.run_folder
RUN_DIR = COACH_DIR / "run" / RUN_FOLDER

# 루트 디렉토리 바로 아래의 pose_predictions.json 지정
OUTPUTS_DIR = RUN_DIR / "outputs"

user = RUN_DIR / "user_info.json"
with user.open(mode="r", encoding='utf-8') as file:
    user_data = json.load(file)

hpe = OUTPUTS_DIR / "pose_predictions.json"
with hpe.open(mode="r", encoding='utf-8') as file:
    pose_data = json.load(file)

details = OUTPUTS_DIR / "details.json"
with details.open(mode="r", encoding='utf-8') as file:
    detail_data = json.load(file)

ps = PoseSequence(pose_data, detail_data, user_data)

# 피처 추출을 위한 값 계산
ps.cal_stride()
ps.pixel2m()

def feature1(ps: PoseSequence):
    strides = ps.gct()

    # 각 스트라이드별로 골반의 수직 진동 평균
    res = 0
    for i in range(len(strides)):
        start, end = strides[i]
        res += ps.df["hip_center_y"][start:end].agg(['min', 'max']).diff()['max']

    # APO: Amplitude of pelvis oscillation : 골반 진동 진폭
    apo_pixel = res / len(strides)
    return apo_pixel * ps.m_per_pixel / ps.user['height']

def feature2(ps: PoseSequence):
    ps.df[['left_shoulder_x','left_shoulder_y', 'right_shoulder_x', 'right_shoulder_y']]

if __name__ == "__main__":
    features = {
        'feature1': {
            "value": feature1(ps=ps),
            "unit": "ratio",
            "measurement_source": "2d_pose"
        }
    }

    feature_path = OUTPUTS_DIR / "feature_results.json"
    feature_path.write_text(
            json.dumps(
                features,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
    )