# Runners Feed Coach 파이프라인

RunPod의 GPU `video_analysis` 결과에서 러닝 지표와 서비스 리포트를 생성합니다.
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

API가 작업을 넣으면 `coach-worker`는 RunPod에 원본 영상의 HPE·대표 러너 추적·
5프레임 보간·렌더링을 요청합니다. OCI는 RunPod 산출물을 검증한 뒤 피처 계산,
리포트·스켈레톤 Adapter, Object Storage 업로드와 DB 상태 갱신만 수행합니다.
운영 경로에는 OCI 로컬 HPE fallback이 없습니다.

RunPod Pod가 실행 중일 때만 HTTP Proxy API를 직접 사용할 수 있습니다. Worker는 장시간
동기 HTTP 요청을 유지하지 않고 빠른 submit 응답의 `remote_job_id`를 저장한 뒤 별도
Celery countdown 작업으로 상태를 polling합니다. 계약 상세는
`docs/RUNPOD_SEHYEON_E2FE43E_HANDOFF.md`를 참고합니다.

서비스 피처 점수는 피처별로 고정합니다. `feature2`는 좋은 프레임/측정 가능 프레임,
`feature3`과 `feature4`는 좋은 프레임/영상 전체 프레임입니다. `feature1`은 논문 표본의
관찰 범위만 표시하고 종합 자세 점수에서는 제외합니다. confidence는 계산 확률이 아니라
초기 가정값이며 `confidence_assumed=true`, `confidence_pct=null`로 전달됩니다.

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
- `outputs/feature_results.service.json`
- `outputs/rendered.mp4`
- `outputs/report.json`
- `outputs/skeleton.json.gz`

`COACH_AGENT_ENABLED=auto`가 기본값입니다. `OPENAI_API_KEY`가 비어 있으면 자세 분석과
측정 결과는 정상 생성하고 AI 코칭 문서만 생략합니다.
