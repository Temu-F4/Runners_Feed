# Runners Feed

러닝 영상을 분석해 자세 피드백을 제공하는 서비스입니다.

## RunPod 영상 분석

담당: `blueday98`

- RunPod은 전체 `video_analysis`를 상시 Pod API로 실행합니다.
- 작업 상태와 산출물은 기존 GPU attempt·manifest 계약으로 관리합니다.
- RunPod은 산출물을 OCI Object Storage에 직접 저장하고, OCI는 피처·점수·리포트와 최종 상태 등록을 담당합니다.

상세한 실행 구조와 운영 경계는 [`coach/README.md`](coach/README.md)를 참고하세요.
