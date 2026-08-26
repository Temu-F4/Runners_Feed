# Runners Feed MVP 구축 이력

이 문서는 Runners Feed MVP를 구축한 전 과정을 단계별로 기록한다.
각 단계는 `WHAT / WHY / WHERE / HOW / EXPECTED / CHANGES / VERIFY / ROLLBACK`
형식으로 작성하며, 문서 기준일은 2026-08-26이다.

비밀번호, API key, OCI private key, 서명 URL은 기록하지 않는다.

## 1. 맥북에서 OCI SSH 접속 구성

### WHAT

기존 OCI SSH private key를 맥북의 `~/.ssh/runners-feed-oci.key`에 두고
권한을 `600`으로 제한해 OCI VM에 접속했다.

### WHY

OCI에서 실행 중인 Docker와 코드를 맥북에서도 관리하기 위해 새로운 접속 환경이 필요했다.

### WHERE

- 맥북: `/Users/jimmypak/.ssh/runners-feed-oci.key`
- OCI 사용자: `ubuntu`
- 현재 OCI Public IP: `140.238.0.197`

### HOW

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/runners-feed-oci.key
ssh -i ~/.ssh/runners-feed-oci.key ubuntu@140.238.0.197
```

`OCI_PUBLIC_IP` 같은 예시 문자열이 아니라 실제 Public IP를 사용했다.
SSH 별칭 설정은 맥북의 `~/.ssh/config`에 만들며 OCI 서버 안에 만들지 않는다.

### EXPECTED

Ubuntu 로그인 배너가 나오고 `~/runners-feed` 또는 배포 checkout에 접근할 수 있어야 한다.

### CHANGES

- 맥북에 SSH private key 사본과 `known_hosts` 항목 생성
- OCI 코드와 컨테이너에는 변경 없음

### VERIFY

OCI에서 `docker compose ps`를 실행해 기존 컨테이너가 보이는 것을 확인했다.

### ROLLBACK

맥북 SSH 설정만 제거하면 된다. OCI의 `authorized_keys`나 기존 접속 키는 삭제하지 않는다.

## 2. GitHub monorepo와 개발 기준 확립

### WHAT

팀 저장소 `Temu-F4/Runners_Feed` 하나에서 API, Worker, 추론 코드,
Next.js, Nginx, Docker Compose를 함께 관리하도록 구성했다.

### WHY

MVP 단계에서 frontend/backend/model 저장소를 분리하면 버전과 배포 설정을 맞추는 비용이 커진다.
한 저장소로 전체 흐름을 먼저 안정화한 뒤 필요할 때 분리하는 편이 안전하다.

### WHERE

- 맥북 checkout: `/Users/jimmypak/OCI`
- GitHub: `Temu-F4/Runners_Feed`
- OCI checkout: `/home/ubuntu/runners-feed-poc-deploy`

### HOW

기능 branch에서 수정하고 검증 후 Pull Request로 `main`에 병합하는 방식을 사용했다.
`.gitignore`로 다음 항목을 제외했다.

```text
.env
*.key
*.pem
runtime/
models/
*.onnx
*.mp4
```

모델 팀의 `J-sehyeon/Oracle_Project`는 POC 코드의 출처로만 사용하고
현재 배포 저장소로는 사용하지 않는다.

### EXPECTED

GitHub에는 재배포 가능한 코드만 있고, 인증정보·모델·영상·실행 결과는 없어야 한다.

### CHANGES

- GitHub에 Runners Feed monorepo 구성
- 기능별 commit과 merge 이력 생성
- OCI 코드는 GitHub 기준으로 배포

### VERIFY

`git status`, `git diff --check`, 선택적 `git add`로 비밀파일이 stage되지 않는 것을 확인했다.

### ROLLBACK

기능별 commit 또는 merge commit을 기준으로 되돌린다.
이미 공개된 비밀정보는 Git revert로 해결하지 않고 즉시 폐기·회전해야 한다.

## 3. Docker Compose 기반 서비스 구성

### WHAT

FastAPI, PostgreSQL, Redis, 일반 Celery worker, inference worker를
Docker Compose로 실행하도록 구성했다.

### WHY

개별 설치보다 환경 차이를 줄이고, 서비스별 재시작과 재배포를 독립적으로 수행하기 위해서다.

### WHERE

- `compose.yaml`
- `compose.poc.yaml`
- OCI Docker Engine

### HOW

```text
postgres          작업 상태 DB
redis             Celery broker/result backend
api               FastAPI
worker            일반 Celery task
inference-worker  RTMPose 전용 task
frontend          Next.js
web               Nginx
certbot           인증서 도구용 profile
```

수동 모델 검증용 `inference-poc`는 `manual-poc` profile로 분리했다.

### EXPECTED

상시 서비스는 `up` 상태이고 PostgreSQL, Redis, API, Frontend는 health check를 통과해야 한다.

### CHANGES

- Docker image와 network 생성
- PostgreSQL/Redis named volume 생성
- API는 호스트 `127.0.0.1:8000`에만 bind

### VERIFY

`docker compose ps`와 각 health endpoint를 확인했다.

### ROLLBACK

문제가 있는 서비스만 이전 commit으로 build하고 `up -d --no-deps`로 교체한다.
DB volume은 명시적 백업 없이 삭제하지 않는다.

## 4. RTMPose Halpe26 영상 POC 이식

### WHAT

RTMDet nano 사람 검출과 RTMPose-M Halpe26 자세 추론 파이프라인을
모델 팀 POC에서 Worker 코드로 이식했다.

### WHY

이미지 한 장이 아니라 실제 영상의 프레임 추출, 추론, 추적, 렌더링까지
OCI CPU 환경에서 가능한지 검증해야 했다.

### WHERE

- 코드: `worker/inference/`
- 모델: `/home/ubuntu/runners-feed-runtime/models`
- 실행 결과: `/home/ubuntu/runners-feed-runtime/run/{job_id}`

### HOW

```text
MP4
→ 프레임 추출
→ 사람 검출
→ Halpe26 26개 keypoint 추론
→ pose tracking
→ details.json / pose_predictions.json
→ skeleton 렌더링
→ rendered.mp4
```

모델 파일은 크기와 라이선스·보안 문제로 Git에 넣지 않고 OCI Runtime에 유지했다.

### EXPECTED

샘플 500프레임을 모두 처리하고 JSON 두 개와 렌더링 MP4를 생성해야 한다.

### CHANGES

- POC 추론 코드와 inference Dockerfile 추가
- 실행 파일이 없는 경우 즉시 실패하도록 입력 검증 추가
- 수동 POC와 운영 Worker 설정 분리

### VERIFY

샘플 영상 500프레임 처리, Halpe26 26개 keypoint, 렌더링 영상 생성을 확인했다.

### ROLLBACK

기존 테스트 Worker는 유지되므로 inference 서비스만 내리거나 이전 image로 교체할 수 있다.
Runtime 모델과 결과는 별도 디렉터리에 있어 코드 rollback에 영향을 받지 않는다.

## 5. Celery 비동기 추론 연결

### WHAT

RTMPose 전체 파이프라인을 전용 Celery queue와 inference worker에서 실행하도록 연결했다.

### WHY

약 90초가 걸리는 추론을 FastAPI 요청 안에서 실행하면 HTTP 연결과 API worker가 장시간 점유된다.

### WHERE

- `worker/inference_celery_app.py`
- `worker/inference_tasks.py`
- Redis DB 1: broker
- Redis DB 2: result backend

### HOW

운영 task `inference.run_object_storage`를 `inference` queue로 보내고
worker concurrency를 1로 제한했다. 각 실행은 Celery task ID와 동일한 `job_id`를 사용한다.

### EXPECTED

API는 즉시 job ID를 반환하고 Worker가 독립적으로 추론을 완료해야 한다.

### CHANGES

- inference queue와 task route 추가
- 작업별 Runtime 디렉터리 도입
- task timeout과 prefetch 설정 추가

### VERIFY

Celery 로그에서 task received와 task succeeded를 확인했다.
샘플 처리시간은 약 90~94초였다.

### ROLLBACK

inference worker만 중지하면 신규 추론은 실행되지 않는다.
Redis, API, PostgreSQL과 기존 일반 worker는 계속 운영할 수 있다.

## 6. Object Storage 입출력 연결

### WHAT

Worker가 raw 버킷에서 입력 영상을 다운로드하고 results 버킷에 결과 3개를 업로드하도록 연결했다.

### WHY

컨테이너나 VM Runtime에만 영상을 저장하면 컨테이너 교체와 디스크 장애 시 결과를 잃을 수 있다.

### WHERE

- Raw bucket: `bucket-t04-raw`
- Results bucket: `bucket-t04-results`
- OCI 인증 mount: `/home/ubuntu/.oci` → `/.oci:ro`

### HOW

OCI SDK config 경로를 `/.oci/config`로 통일하고, config 안의 key 경로도
컨테이너에서 유효한 `/.oci/...pem` 경로로 맞췄다.

### EXPECTED

입력 다운로드 후 다음 객체가 생성되어야 한다.

```text
jobs/{job_id}/details.json
jobs/{job_id}/pose_predictions.json
jobs/{job_id}/rendered.mp4
```

### CHANGES

- API/Worker에 OCI SDK gateway 추가
- OCI config를 read-only mount
- 입력과 결과 bucket 역할 분리

### VERIFY

SDK 인증, bucket 조회, 원본 다운로드, 결과 업로드를 실제 OCI에서 확인했다.

### ROLLBACK

Object Storage task를 중지하고 수동 로컬 POC로 되돌릴 수 있다.
생성된 객체는 보관 정책 확인 전 자동 삭제하지 않는다.

## 7. Inference worker non-root 실행

### WHAT

Inference worker를 root가 아닌 OCI 호스트 UID/GID에 맞춘 사용자로 실행했다.

### WHY

모델 코드나 라이브러리 문제가 컨테이너 root 권한으로 확대되는 위험을 줄이기 위해서다.

### WHERE

- `worker/Dockerfile.inference`
- `compose.poc.yaml`
- OCI `.env`의 `INFERENCE_UID`, `INFERENCE_GID`

### HOW

Image에 app 사용자를 만들고 Compose의 `user` 설정을 호스트 UID/GID와 일치시켰다.
OCI 인증은 `/root` 대신 모든 실행 사용자에게 명확한 `/.oci` 경로로 mount했다.

### EXPECTED

컨테이너의 실행 UID는 0이 아니면서 모델과 Runtime 파일을 읽고 쓸 수 있어야 한다.

### CHANGES

- Worker 실행 사용자 변경
- Runtime mount 권한 정렬
- OCI credential 경로 정리

### VERIFY

Celery의 root 경고가 사라지고, non-root 상태에서 Object Storage 추론이 성공했다.

### ROLLBACK

이전 image로 되돌릴 수 있지만 root 실행은 보안상 임시 진단 외에는 사용하지 않는다.

## 8. PostgreSQL job lifecycle 저장

### WHAT

`inference_jobs` 테이블에 작업 상태, 시간, 입력 객체, 결과 객체, 오류 코드를 저장했다.

### WHY

Redis/Celery 결과만으로는 장기 조회, 장애 분석, 사용자 작업 목록을 안정적으로 제공하기 어렵다.

### WHERE

- `api/app/database.py`
- `worker/job_repository.py`
- PostgreSQL `inference_jobs`

### HOW

```text
QUEUED → PROCESSING → SUCCESS
                    └→ FAILED
```

API가 QUEUED를 만들고 Worker가 PROCESSING과 SUCCESS/FAILED를 갱신한다.

### EXPECTED

API 재시작이나 Celery result 만료 이후에도 job 상태와 결과 경로를 조회할 수 있어야 한다.

### CHANGES

- inference job 테이블과 index 생성
- API/Worker DB 연결 추가
- job별 생성·시작·완료 시간 기록

### VERIFY

실제 E2E job에서 PROCESSING과 SUCCESS 및 결과 객체 3개가 PostgreSQL에 기록된 것을 확인했다.

### ROLLBACK

코드는 이전 버전으로 되돌릴 수 있지만 생성된 DB table/record는 자동 삭제하지 않는다.
Schema 삭제는 백업 후 별도 승인으로 수행한다.

## 9. 업로드·작업·결과 URL API

### WHAT

브라우저 직접 업로드, 업로드 완료 확인, job 생성·조회, 결과 영상 임시 URL API를 구현했다.

### WHY

큰 MP4를 FastAPI가 중계하지 않고 Object Storage에 직접 올리고,
비공개 결과를 제한된 시간 동안만 브라우저가 재생할 수 있어야 했다.

### WHERE

- `api/app/main.py`
- `api/app/object_storage.py`
- Nginx 경유 공개 경로 `/api/*`

### HOW

```text
POST /uploads
PUT  {temporary upload URL}
POST /uploads/complete
POST /jobs
GET  /jobs/{job_id}
POST /jobs/{job_id}/result-url
```

MP4 형식, 최대 250 MiB, 생성된 `uploads/{uuid}.mp4` 경로,
실제 객체 크기와 Content-Type을 서버에서 다시 검사한다.

### EXPECTED

브라우저가 API key와 OCI private key를 알지 않고도 전체 업로드와 결과 재생을 수행해야 한다.

### CHANGES

- 제한시간이 있는 upload/result PAR 생성
- 업로드 객체 검증
- 공개 API 요청/응답 추가

### VERIFY

권한 probe, 실제 업로드, job 생성, 결과 URL에서 MP4 바이트 읽기를 확인했다.

### ROLLBACK

API와 프론트를 이전 commit으로 되돌릴 수 있다.
이미 생성된 PAR은 만료시간 후 사용할 수 없으며 private key는 공개되지 않는다.

## 10. Next.js 프론트와 Nginx API gateway

### WHAT

Next.js 화면에서 MP4 선택, 진행 상태, job polling, 결과 영상 재생을 제공하고
Nginx가 프론트와 API를 하나의 주소로 제공하도록 구성했다.

### WHY

사용자는 터미널이나 Celery를 알지 않고 브라우저에서 전체 분석을 수행해야 한다.
API key는 브라우저에 노출하면 안 된다.

### WHERE

- `frontend/`
- `nginx/templates/default.conf.template`
- OCI port 80/443

### HOW

```text
Browser
  → Nginx /
      → Next.js :3000
  → Nginx /api/*
      → X-API-Key를 서버에서 추가
      → FastAPI :8000
```

Next.js는 production standalone image로 실행하며 3000은 Docker network 내부에서만 사용한다.

### EXPECTED

사용자가 한 화면에서 파일 업로드부터 결과 영상 재생까지 완료해야 한다.

### CHANGES

- Next.js App Router frontend 추가
- Nginx reverse proxy와 보안 header 추가
- API key를 OCI `.env`에만 저장

### VERIFY

Frontend health, Nginx API 200, 직접 API 무인증 401, Next static asset 200을 확인했다.

### ROLLBACK

Nginx/Frontend만 이전 image로 교체할 수 있다.
FastAPI, DB, Worker는 독립적으로 계속 운영할 수 있다.

## 11. Let’s Encrypt IP HTTPS와 자동 갱신

### WHAT

도메인 없이 현재 Public IP `140.238.0.197`에 Let’s Encrypt 인증서를 발급하고
HTTP를 HTTPS로 전환했다.

### WHY

영상 업로드와 결과 URL을 평문 HTTP로 전송하지 않고,
브라우저가 신뢰하는 암호화 연결로 제공하기 위해서다.

### WHERE

- 인증서: `/home/ubuntu/runners-feed-certbot/conf`
- ACME webroot: `/home/ubuntu/runners-feed-certbot/www`
- 자동 갱신: OCI systemd

### HOW

HTTP ACME challenge를 먼저 확인한 뒤 staging 발급, 운영 발급 순서로 진행했다.
Nginx 443 설정과 80→443 redirect를 추가하고 systemd timer가 12시간마다 갱신을 확인한다.

### EXPECTED

- `https://140.238.0.197` → 200
- `http://140.238.0.197` → 308 HTTPS redirect
- 인증서 SAN → `IP Address:140.238.0.197`
- 자동 갱신 dry-run 성공

### CHANGES

- OCI 443 listener 사용
- Certbot image/profile와 인증서 mount 추가
- systemd service/timer 설치
- 인증서 파일은 Git이 아닌 OCI 호스트에 저장

### VERIFY

공개 TLS 검증, SAN, HTTPS home/API 200, HTTP redirect 308,
Certbot renewal dry-run, systemd timer active를 확인했다.

### ROLLBACK

Nginx를 HTTP-only commit으로 되돌리고 web 컨테이너만 재생성할 수 있다.
timer는 `systemctl disable --now runners-feed-cert-renew.timer`로 중지한다.
인증서 파일은 즉시 삭제할 필요가 없다.

## 12. 샘플 데이터 운영 E2E 검증

### WHAT

OCI의 기존 `test1.mp4`를 공개 HTTPS 업로드 API부터 결과 영상 접근까지 새로 실행했다.

### WHY

개별 서비스 테스트가 아니라 사용자가 사용하는 전체 운영 흐름이 실제로 연결됐음을 증명하기 위해서다.

### WHERE

- 입력: `/home/ubuntu/runners-feed-runtime/run/test1/test1.mp4`
- 공개 서비스: `https://140.238.0.197`
- Job ID: `9267fa8d-e4b4-47c4-9862-4dc442dc748e`

### HOW

```text
HTTPS upload URL 발급
→ 11,109,011 byte MP4 업로드
→ 업로드 검증
→ job 생성
→ RTMPose 추론
→ 결과 3개 업로드
→ result URL 발급
→ rendered MP4 첫 바이트 확인
```

### EXPECTED

`PROCESSING → SUCCESS`, 결과 영상 HTTP 200 또는 206, `E2E=PASS`가 되어야 한다.

### CHANGES

- Raw bucket에 샘플 입력 객체 1개
- PostgreSQL에 job 1개
- Results bucket에 결과 객체 3개
- 임시 검사 프로그램은 실행 후 삭제

### VERIFY

- Job status: `SUCCESS`
- Worker elapsed: 약 91.06초
- Result video HTTP: `206`
- Docker 서비스: 정상

### ROLLBACK

운영 코드 변경은 없으므로 rollback이 필요 없다.
생성된 샘플 job과 결과는 검증 증거로 유지하고 보관 정책에 따라 나중에 정리한다.

## 13. 현재 구조

```text
Browser
  │ HTTPS :443
  ▼
Nginx
  ├─ /       → Next.js frontend
  └─ /api/*  → FastAPI + server-side API key
                    │
                    ├─ PostgreSQL: job lifecycle
                    ├─ Redis: Celery queue
                    ├─ Object Storage: raw/results
                    └─ inference-worker: RTMPose
```

## 14. 현재 남은 작업

### 지금 필요한 작업

1. `feat/ip-https` Pull Request를 `main`에 병합
2. OCI checkout을 병합된 `main`으로 복귀
3. 기존 운영 runbook의 오래된 완료/미구현 항목 갱신
4. PostgreSQL 백업과 복구 테스트
5. Object Storage와 Runtime 보관·삭제 정책
6. 최소 로그·장애 확인 절차

### 시연 이후로 미뤄도 되는 작업

- 도메인 구매와 DNS 연결
- 다중 인물 대상 선택 보완
- 검출 실패 프레임 보완
- peak memory 측정
- 서버 분리와 자동 확장
- 고급 중앙 모니터링
- GitHub Actions 자동 배포

## 15. 공통 작업 보고 규칙

앞으로 모든 작업은 실행 전과 완료 후 다음 항목을 빠짐없이 기록한다.

```text
WHAT     무엇을 바꾸는가
WHY      왜 필요한가
WHERE    맥북/OCI/GitHub/OCI Console 중 어디인가
HOW      어떤 파일·명령·흐름으로 수행하는가
EXPECTED 정상 결과와 완료 조건은 무엇인가
CHANGES  파일·서비스·DB·외부 상태 중 무엇이 바뀌는가
VERIFY   성공을 어떻게 확인하는가
ROLLBACK 실패 시 어디까지 어떻게 되돌리는가
```
