# Runners Feed Coach 파이프라인

입력 MP4에서 자세 추정, 프레임 추적, 러닝 지표 추출, 렌더링 영상을 생성합니다.
OpenAI API 키가 설정된 경우에만 선택적으로 AI 코칭 문서를 추가합니다.

## OCI 서비스 실행

운영 서비스는 저장소 루트의 `compose.yaml`과 `compose.coach.yaml`을 함께 사용합니다.

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  --profile coach \
  up -d --build
```

API가 `coach` 큐에 작업을 넣으면 `coach-worker`가 OCI Object Storage에서 영상을
내려받아 처리하고 결과 JSON과 렌더링 영상을 다시 업로드합니다.

## 수동 실행

`runtime/run/<RUN_ID>` 안에 MP4 한 개와 `user_info.json`을 준비한 뒤 실행합니다.

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  --profile manual-coach \
  run --rm coach-manual <RUN_ID>
```

필수 결과는 다음과 같습니다.

- `outputs/details.json`
- `outputs/pose_predictions.json`
- `outputs/feature_results.json`
- `outputs/rendered.mp4`
- `outputs/report.json`

`COACH_AGENT_ENABLED=auto`가 기본값입니다. `OPENAI_API_KEY`가 비어 있으면 자세 분석과
측정 결과는 정상 생성하고 AI 코칭 문서만 생략합니다.
