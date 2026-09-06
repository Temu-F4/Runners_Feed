# Coach model contract

이 계약은 모델러가 구현한 자세·특징 모델을 Runners Feed 파이프라인에
교체 가능한 형태로 연결하기 위한 기준이다. 모델러는 API, PostgreSQL,
Celery, Expo 코드를 수정하지 않는다.

## 입력

모델 실행 시 파이프라인은 다음 인자를 전달한다.

```text
python hpe_entrypoint.py WORKSPACE_ROOT RUN_ID VIDEO_PATH
python feature_entrypoint.py WORKSPACE_ROOT RUN_ID
```

실행 디렉터리는 다음과 같다.

```text
WORKSPACE_ROOT/run/RUN_ID/
├── input.mp4                 # 또는 모델이 지원하는 .mov 입력
├── user_info.json             # {"user": {"height": meters}}
└── outputs/
```

입력 영상은 원본을 변경하거나 외부로 전송하지 않는다. 영상 형식·키·단위가
다르면 모델 manifest에 명시하고 어댑터에서 변환한다.

## 필수 출력

첫 번째 엔트리포인트는 다음 파일을 생성해야 한다.

```text
outputs/output.mp4
outputs/details.json
outputs/pose_predictions.json
```

두 번째 엔트리포인트는 다음 파일을 생성해야 한다.

```text
outputs/feature_results.json
```

`feature_results.json`의 최소 형식은 다음과 같다.

```json
{
  "feature_id": {
    "value": 0.123,
    "unit": "ratio",
    "measurement_source": "2d_pose"
  }
}
```

측정할 수 없는 값은 `null`로 표시할 수 있지만 `NaN`, `Infinity`, 빈 문자열은
사용하지 않는다. 지표를 새로 추가할 때는 ID, 단위, 계산식, 입력 조건,
신뢰도 산정 방법, 기준 범위, 제한사항을 함께 제출한다.

## 실행·보안 규칙

- 프로세스 종료 코드 `0`은 필수 산출물이 모두 생성된 경우에만 사용한다.
- DB와 Object Storage를 직접 호출하지 않는다.
- API 키와 사용자 토큰을 로그에 출력하지 않는다.
- 모델 파일은 Git에 커밋하지 않는다.
- 모델 파일의 경로와 SHA-256은 `model_manifest.json`에 기록한다.
- 모델 계산 로직과 서비스 경로·단계 로그·결과 변환 로직을 분리한다.

## 교체 절차

1. `coach/scripts/model_contract/model_manifest.example.json`을 복사해 새
   manifest를 만든다.
2. 새 엔트리포인트를 이 계약에 맞춰 추가한다.
3. `python coach/scripts/model_contract/validate_artifacts.py RUN_DIR`가
   통과하도록 단위 테스트를 작성한다.
4. 승인된 골든영상으로 결과값·추적률·처리시간을 비교한다.
5. PR에서 모델러 커밋, manifest, 골든 기준 변경을 함께 검토한다.
6. 승인 후에만 `COACH_HPE_ENTRYPOINT`와
   `COACH_FEATURE_ENTRYPOINT`를 새 경로로 지정한다.

품질 기준 예시는 `quality_baseline.example.json`에 있다. 다음 명령은 artifact
계약뿐 아니라 필수 지표 ID, 추적률 하한, 지표 단위·범위, 처리시간 예산을 함께
검사한다.

```bash
python coach/scripts/model_contract/quality_gate.py \
  coach/tests/fixtures/model-golden \
  coach/scripts/model_contract/quality_baseline.example.json
```

실제 모델러 골든 실행 결과를 받을 때는 첫 번째 경로를 해당 실행 디렉터리로
바꾸고, 두 번째 기준 파일을 모델 버전에 맞게 PR에 포함한다. 기준을 낮추는
변경은 모델 코드와 함께 리뷰해야 한다.

기존 `hpe.sh`, `features.sh`, `agent.sh`는 기본 엔트리포인트를 사용하면서
환경변수로 교체 경로를 받을 수 있다. 따라서 모델러 코드가 이 계약을 지키면
기존 API와 모바일 앱은 변경하지 않아도 된다.
