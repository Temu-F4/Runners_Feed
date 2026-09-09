# RunPod 상시 Pod 서버

작성: blueday98

팀 비동기 계약의 별도 배포 단위다. POST `/v4/storage-video-analysis`는 202와 작업 ID를 반환하고 GET `/v4/storage-video-analysis/{remote_job_id}`는 상태를 반환한다. 두 경로 모두 Bearer 인증을 요구한다.

## 실행

저장소 루트에서 `docker build -f runpod/Dockerfile -t runners-feed-runpod:local .`로 빌드한다. 현재 Docker 이미지는 실제 GPU에서 빌드·실행 검증하기 전의 후보다.

Pod에는 GPU 한 개와 HTTP 8000 포트를 지정한다. GPU는 CUDA 및 NVENC를 지원해야 한다. `/workspace/runpod-state`를 영속 볼륨에 두고 `/models`에 manifest가 지정한 두 ONNX 파일을 설치한다. 가중치는 시작할 때 SHA-256으로 검증한다.

필수 비밀 환경 설정은 `RUNPOD_SHARED_TOKEN`(24자 이상), `MODEL_RELEASE`(OCI 검증 대상과 동일)이다. 선택 설정은 `COACH_MODEL_ROOT`, `RUNPOD_STATE_DIR`다. 값은 저장소나 채팅에 올리지 않는다. OCI 운영 설정은 별도 배포 승인 전 변경하지 않는다.

직접 실행은 `uvicorn runpod.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 --no-access-log`를 사용한다. 영속 디렉터리당 프로세스는 하나만 허용한다.

## 실행·재전달 정책

- SQLite 트랜잭션과 attempt 고유 키로 동시 재전달에도 같은 remote_job_id를 반환한다. 입력·모델 등 불변 내용이 바뀐 같은 attempt는 409다.
- 한 GPU에서 한 작업씩 실행한다. POST는 GPU 분석이 끝나기를 기다리지 않는다.
- 완료·실패 기록을 자동 삭제하지 않는다. 재시작 때 queued는 이어서 처리하고 running은 WorkerInterrupted 실패로 전환한다. 같은 attempt를 자동 재추론하지 않는다. 검토 후 새 attempt로 재시도한다.
- 서명 URL은 작업 수행에 필요한 비밀이므로 SQLite가 있는 볼륨도 비밀 저장소로 취급한다. 재전달 URL로 기존 작업을 덮어쓰지 않는다. URL이 만료되면 실패 후 새 attempt가 필요하다.
- 원본 HPE 소스를 변경하지 않고 CUDA로 실행한다. 실제 detector·pose ONNX 세션의 CUDA provider를 확인하고 런타임 CPU fallback을 비활성화한다. 일부 shape 연산의 CPU 배치는 금지하지 않는다.
- 원본 output.mp4를 NVENC H.264/yuv420p rendered.mp4로 변환하고 OCI 계약 검증 함수를 재사용한다. 산출물 세 개를 올린 뒤 pose_manifest.json을 마지막에 올린다.
- timing의 upload/worker_total은 manifest 자체 PUT 직전까지 측정한다.
- `/health`는 준비 상태이며 실제 영상 성공 증거를 대체하지 않는다.

## 검증 및 현재 한계

`python -m unittest runpod.test_state`로 동시 재전달·충돌·재시작·완료 재조회 정책을 검증한다. CUDA/가중치/OCI 서명 URL을 사용하는 실제 시험은 별도다. 실제 영상의 POST→GET complete→manifest 검사→OCI 후처리→모바일 결과, 진행 중 및 완료 후 같은 attempt 재전달을 모두 확인해야 한다.

서버 종료가 추론 완료와 겹치거나 manifest 게시 후 상태 저장 전에 중단되면 failed로 보수적으로 처리한다. 이 경우 산출물이 존재할 수 있으나 같은 attempt를 재추론하지 않는다. 디스크 보관 용량·작업 보관 기간은 운영 전 확정해야 한다. GPU 실측, 이미지 빌드, OCI·모바일 E2E 및 모델 품질 승인은 아직 완료되지 않았다.
