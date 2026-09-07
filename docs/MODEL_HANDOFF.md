# 모델러 전달 및 즉시 적용 규격

이 문서의 목적은 모델 계산 코드와 서비스 코드를 분리해, 새 모델을 전달받았을
때 API·DB·Expo를 다시 구현하지 않고 플러그인 선택만으로 적용하는 것이다.

## 현재 기준 모델

- model ID: `sehyeon-dcc2d7d`
- 원본 저장소: `Oracle_Project/sehyeon`
- 원본 commit: `dcc2d7d7a7eaacb8b2828745d31a5b375c5b893b`
- 플러그인: `coach/model_plugins/sehyeon-dcc2d7d/`
- feature: `feature1`, 골반 수직 이동/사용자 키, 단위 `ratio`

원본 Python 파일은 플러그인 안에 보존한다. OCI 실행에 필요한 경로, 입력 탐색,
H.264 변환, 단계 기록, Object Storage, DB, Celery는 플러그인 밖의 wrapper가
담당한다.

## 전달 디렉터리

```text
coach/model_plugins/<model_id>/
├── model_manifest.json
├── quality_baseline.json
└── scripts/
    ├── hpe/
    │   ├── hpe.py
    │   ├── hpe_model.py
    │   └── pose_track.py
    ├── features/
    │   ├── feature_extract.py
    │   ├── utils.py
    │   └── papers.py
    └── Agent/
        ├── Running_coach.py
        └── prompts.py
```

파일 구성이 다르면 먼저 다음 차이를 알려야 한다.

- 실행 인자와 working directory
- 입력 영상 확장자와 `user_info.json` 키·단위
- 모델 가중치 형식·경로·SHA-256
- 출력 파일명과 JSON schema
- feature ID·단위·계산식의 추가/삭제/변경
- CPU/GPU, 메모리, 예상 처리시간
- 외부 API와 secret 필요 여부

이 차이를 확인하기 전에는 기존 API 계약에 억지로 맞추지 않는다.

## 고정 실행 계약

Pose 엔트리포인트:

```bash
python hpe.py WORKSPACE_ROOT RUN_ID VIDEO_PATH --device cpu
```

필수 출력:

```text
run/<RUN_ID>/outputs/output.mp4
run/<RUN_ID>/outputs/details.json
run/<RUN_ID>/outputs/pose_predictions.json
```

Feature 엔트리포인트:

```bash
python feature_extract.py WORKSPACE_ROOT RUN_ID
```

필수 출력:

```text
run/<RUN_ID>/outputs/feature_results.json
```

`details.json.video`에는 `width`, `height`, `fps`, `frame_count`가 필요하다.
`pose_predictions.json.frames`는 비어 있으면 안 된다. feature는 최소한
`value`와 비어 있지 않은 `unit`을 포함해야 한다. 숫자에는 `NaN`과
`Infinity`를 사용할 수 없으며 측정 불가는 `null`로 표현한다.

앱에서 feature 카드와 근거 상세를 표시하려면 `feature_results.json`의 각
feature에 다음 선택 필드를 추가할 수 있다. 모델이 제공하지 않는 필드는
adapter가 임의로 만들지 않고 앱에서 미제공 상태로 표시한다.

```json
{
  "feature1": {
    "value": 0.046,
    "unit": "ratio",
    "representative_value": 0.046,
    "aggregation": "stance-phase median",
    "reference_range": {
      "kind": "reference",
      "min": 0.03,
      "max": 0.06,
      "unit": "ratio",
      "criterion_version": "criterion-1",
      "evidence_ids": ["evidence-1"]
    },
    "series": [
      {"frame_index": 1, "timestamp_ms": 33, "value": 0.045, "confidence_pct": 91}
    ],
    "verdict": "review",
    "confidence_pct": 91,
    "confidence_level": "medium",
    "interpretation": "측정값이 일부 구간에서 관찰됩니다.",
    "coaching_action": null,
    "limitation": "측면 촬영 기준입니다.",
    "evidence_ids": ["evidence-1"]
  }
}
```

코칭 문장은 자유 Markdown만으로 전달하지 말고 가능하면
`outputs/running_report.json`으로 전달한다. `status`, `model`, `summary`,
`priority_actions`, `maintain_actions`, `disclaimer`, `validator_version`를
포함하며, 각 action은 `feature_id`와 `text`를 반드시 가져야 한다. 기존
`running_report.md`는 요약 문장 호환용으로 계속 지원한다.

## manifest와 baseline

`model_manifest.json`에 반드시 기록할 내용:

- 고유 model ID와 contract version
- 원본 Git commit
- 세 엔트리포인트
- 입력 파일과 사용자 키의 단위
- 출력 artifact
- feature ID·단위·설명
- 모든 모델 가중치 경로와 SHA-256

`quality_baseline.json`에 반드시 기록할 내용:

- 필수 feature ID
- tracking coverage 하한
- 처리시간 상한
- feature별 최소·최대·단위
- `approval_status: approved`

범위는 한 영상의 우연한 결과가 아니라 승인된 영상의 반복 실행 결과를 토대로
정한다. 기존 지표의 의미나 단위를 바꾸면 같은 feature ID를 재사용하지 말고
새 ID 또는 명시적인 schema version을 사용한다.

## GitHub에 넣지 않는 golden 입력

개인 영상과 사용자 정보는 저장소에 commit하지 않는다. Production에는 다음
형태로 별도 배치한다.

```text
/opt/runners-feed/model-golden/<model_id>/
├── input.mp4
└── user_info.json
```

예시 사용자 정보:

```json
{
  "user": {
    "height": 1.75
  }
}
```

## 모델러가 전달 전에 실행할 검사

```bash
python coach/scripts/model_contract/validate_artifacts.py <golden-run-dir>
python coach/scripts/model_contract/quality_gate.py \
  <golden-run-dir> \
  coach/model_plugins/<model_id>/quality_baseline.json
```

가중치 SHA-256도 manifest와 대조한다. 같은 입력을 최소 3회 실행해 feature 값,
tracking coverage, 처리시간의 변동을 함께 전달한다.

## 서비스 반영 순서

1. 새 디렉터리를 `coach/model_plugins/<model_id>/`에 추가한다.
2. 원본 파일과 commit을 대조한다.
3. contract validator와 quality gate를 실행한다.
4. 모델러 승인 golden 자료를 Production의 별도 경로에 배치한다.
5. GitHub Production variable `COACH_MODEL_ID`와 `MODEL_GOLDEN_DIR`을 바꾼다.
6. `MODEL_CANARY_REQUIRED=1`을 설정한다.
7. PR CI를 통과시키고 immutable release를 배포한다.
8. 배포 전 canary, 배포 직후 검증, 60분 watchdog을 통과시킨다.
9. 새 배포일부터 14일 안정성 관찰을 시작한다.

새 feature를 앱에 표시하는 기본 경로는 동적이므로 ID·label·value·unit은 바로
노출된다. 기준 범위, confidence, limitation, evidence가 필요하면 해당 값을
report adapter 계약에 맞춰 함께 제공해야 한다.

## 변경이 필요한 경우

다음은 모델 코드 수정이 아니라 adapter 변경이 필요한 사유다.

- 원본이 `Coach/run` 고정 경로만 받는 경우: `/workspace/run` 인자로 변환
- 원본이 비밀키 이름을 코드에 고정한 경우: 환경변수와 secret으로 분리
- 원본 결과 영상 codec이 Android 호환이 아닌 경우: H.264로 후처리
- 출력 파일명/schema가 다른 경우: 기존 계약으로 변환하는 adapter 추가
- 새 런타임 의존성이 있는 경우: worker image requirements 변경

이 변경은 원본 플러그인과 별도 파일에 두고, 변경 이유와 입력·출력 차이를 PR에
기록한다.
