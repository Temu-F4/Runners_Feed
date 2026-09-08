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

API가 `gpu_dispatch` 큐에 작업을 넣으면 `gpu-dispatch-worker`가 GPU attempt를
생성하고 시도별 Object Storage signed URL을 발급한 뒤 상시 RunPod Pod API를
호출합니다. RunPod이 `video_analysis`를 끝내고 산출물과 manifest를
Object Storage에 직접 업로드하면, OCI의 `coach-worker`가 `postprocess` 큐에서
피처·점수·리포트 생성과 최종 DB 상태 등록을 수행합니다.

## RunPod `video_analysis` 운영 경계

담당: `blueday98`

- RunPod 범위는 디코딩, 객체 검출, 자세 추론, 추적, 렌더링·인코딩을
  포함한 전체 `video_analysis`입니다.
- 실행 방식은 Serverless `/run`·`/status`가 아닌 상시 Pod의
  `/v4/storage-video-analysis` API입니다.
- 작업 추적은 기존 GPU attempt·`video-analysis-manifest-2.0` 계약을 유지합니다.
- RunPod 산출물은 `pose_predictions.json`, `details.json`, `rendered.mp4`이며,
  manifest는 각 파일의 경로·크기·SHA-256과 GPU 실행 근거를 기록합니다.
- Redis·Celery·OCI Object Storage와 기존 모델 플러그인 형식은 그대로 유지합니다.

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
