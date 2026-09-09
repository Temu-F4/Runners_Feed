## 런팟 비동기 영상 분석 서버
작성: blueday98 (jwp)

RunPod에서 `sehyeon-57e4938` 모델로 영상 분석을 수행하기 위한 비동기 서버를 구현했습니다. OCI가 작업을 제출하면 RunPod은 HTTP 202와 `remote_job_id`를 즉시 반환하며, OCI는 해당 ID로 `queued`, `running`, `complete`, `failed` 상태를 조회합니다.

동일한 `attempt_id`가 재전달되면 기존 작업 ID를 반환해 GPU 추론이 중복 실행되지 않도록 했습니다. 작업 상태는 SQLite에 저장되며, CUDA 추론과 NVENC H.264 변환 후 산출물과 manifest를 OCI Object Storage에 업로드합니다.
