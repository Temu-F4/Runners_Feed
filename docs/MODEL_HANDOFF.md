# Modeler handoff checklist

새 모델을 전달할 때 API·DB·React Native 코드를 수정하지 않고 아래 산출물만
제공하면 된다. 그러면 서비스 어댑터의 환경변수만 바꿔 모델을 선택할 수 있다.

## 반드시 제공할 파일

```text
coach/model_plugins/<model_id>/
├── hpe.py                         # pose 엔트리포인트
├── feature_extract.py             # feature 엔트리포인트
├── model_manifest.json             # 버전·입력·가중치 SHA-256
├── quality_baseline.json           # 골든 기준·허용 범위
└── tests/                          # 모델 단위 테스트
```

## 엔트리포인트 CLI

Pose 단계는 아래 세 인자를 받고 `outputs/`에 세 파일을 만든다.

```bash
python hpe.py WORKSPACE_ROOT RUN_ID VIDEO_PATH
```

필수 출력:

```text
outputs/output.mp4
outputs/details.json
outputs/pose_predictions.json
```

Feature 단계는 아래 두 인자를 받고 `feature_results.json`을 만든다.

```bash
python feature_extract.py WORKSPACE_ROOT RUN_ID
```

필수 출력 예시:

```json
{
  "feature1": {
    "value": 0.046,
    "unit": "ratio",
    "measurement_source": "2d_pose"
  }
}
```

`details.json.video`에는 `width`, `height`, `fps`, `frame_count`를 넣고,
`pose_predictions.json.frames`에는 프레임별 `people`과 `track_id`를 넣는다.
측정 불가 값은 `null`, 숫자에는 `NaN`/`Infinity`를 사용하지 않는다.

## 전달 전 실행

```bash
python coach/scripts/model_contract/validate_artifacts.py <golden-run-dir>
python coach/scripts/model_contract/quality_gate.py \
  <golden-run-dir> <model_plugins>/<model_id>/quality_baseline.json
```

검사 항목은 필수 artifact, 지표 ID, 단위, 허용 수치 범위, 추적률 하한,
처리시간 예산이다. 결과가 기준을 통과하지 않으면 배포하지 않는다.

## 반영 절차

1. 모델러 PR에 위 디렉터리와 테스트를 추가한다.
2. 모델 manifest에 코드 commit, 가중치 SHA-256, 입력 키·단위를 기록한다.
3. 승인된 골든영상 결과와 quality baseline을 함께 리뷰한다.
4. 운영 환경에서 `COACH_HPE_ENTRYPOINT`, `COACH_FEATURE_ENTRYPOINT`를 새
   엔트리포인트로 지정한다.
5. PR CI와 release quality gate를 통과한 뒤 immutable release로 배포한다.

모델 계산·수치가 아닌 `/workspace` 경로, 단계 로그, Object Storage, DB,
Celery, API 응답 형식은 서비스가 관리한다. 새 지표가 생기면 feature ID,
단위, 계산식, 기준 범위, confidence, limitation, evidence ID를 함께 전달한다.
