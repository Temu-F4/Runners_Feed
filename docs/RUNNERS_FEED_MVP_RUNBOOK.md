# Runners Feed MVP 운영 및 개발 Runbook

이 문서는 Runners Feed MVP를 처음 보는 팀원도 현재 상태를 이해하고,
맥북에서 코드를 수정하고, OCI에 배포하고, 샘플 추론 결과를 확인할 수 있도록 만든 운영 문서다.

문서 기준일: 2026-08-26 (Asia/Seoul)

## 1. 현재 상태

### 완료된 기능

- OCI VM 구축
- Docker Compose 기반 FastAPI, PostgreSQL, Redis, Celery 실행
- RTMDet nano + RTMPose-M Halpe26 ONNX 실제 영상 추론
- 샘플 영상 500프레임 처리 및 렌더링 영상 생성
- inference 전용 Celery queue와 worker
- OCI Object Storage 원본 다운로드 및 결과 업로드
- PostgreSQL 작업 상태 저장
- API를 통한 작업 생성 및 상태·결과 조회
- inference worker non-root 실행
- GitHub main 병합 및 OCI main 배포

### 기준 Git commit

```text
744a936 merge: persist inference job lifecycle
```

### 마지막 전체 검증 Job

```text
Job ID: 583de735-fb74-48e5-b974-e2f69534a7b6
Input: poc/test1.mp4
Status: SUCCESS
Frames: 500
Elapsed: 약 94초
```

결과 Object Storage 경로:

```text
jobs/583de735-fb74-48e5-b974-e2f69534a7b6/details.json
jobs/583de735-fb74-48e5-b974-e2f69534a7b6/pose_predictions.json
jobs/583de735-fb74-48e5-b974-e2f69534a7b6/rendered.mp4
```

## 2. 각 환경의 역할

### 맥북

**WHAT**

코드를 수정하고 Git commit과 push를 수행하는 개발 컴퓨터다.

**WHY**

OCI에서 코드를 직접 수정하면 서버의 실제 실행 상태와 GitHub 코드가 달라지고,
서버 장애나 재생성 시 변경사항을 잃을 수 있다.

**HOW**

맥북 원본 저장소:

```text
/Users/jimmypak/OCI
```

맥북에서 수행하는 작업:

- 코드 및 문서 수정
- 문법·구성 검사
- Git branch 생성
- commit과 push
- main 병합

### GitHub

**WHAT**

팀 코드의 기준 원본과 변경 이력을 보관한다.

**WHY**

코드 복구, 팀 협업, 변경 비교, 재배포에 필요하다.

**HOW**

저장소:

```text
Temu-F4/Runners_Feed
```

원칙:

- 기능별 branch를 만든다.
- 검증 후 main에 merge한다.
- `.env`, private key, 모델, 영상, Runtime 결과는 push하지 않는다.

### OCI VM

**WHAT**

Docker 컨테이너와 추론 모델을 실행하는 서버다.

**WHY**

API, DB, queue, 모델 추론을 한 환경에서 MVP로 검증하기 위해 사용한다.

**HOW**

배포 checkout:

```text
/home/ubuntu/runners-feed-poc-deploy
```

모델·입력·결과 Runtime:

```text
/home/ubuntu/runners-feed-runtime
```

OCI에서 수행하는 작업:

- GitHub main 가져오기
- Docker image build
- 컨테이너 시작·재생성
- 로그와 health 확인
- 샘플·운영 작업 실행

OCI에서 직접 수정해도 되는 로컬 설정:

```text
/home/ubuntu/runners-feed-poc-deploy/.env
/home/ubuntu/.oci/
```

코드 파일은 OCI에서 직접 수정하지 않는다.

### OCI Object Storage

**WHAT**

원본 영상과 결과 파일을 VM 밖에 저장한다.

**WHY**

컨테이너나 VM이 재생성되어도 입력과 결과를 보존하고,
큰 영상 파일을 Git이나 PostgreSQL에 넣지 않기 위해 사용한다.

**HOW**

```text
bucket-t04-raw
  └─ poc/test1.mp4

bucket-t04-results
  └─ jobs/{job_id}/
       ├─ details.json
       ├─ pose_predictions.json
       └─ rendered.mp4
```

## 3. 전체 시스템 흐름

```text
Client
  │
  │ POST /jobs
  ▼
FastAPI
  ├─ PostgreSQL에 QUEUED 저장
  └─ Redis inference queue에 Celery task 전송
             │
             ▼
      inference-worker
        ├─ PostgreSQL PROCESSING
        ├─ Raw Bucket 영상 다운로드
        ├─ RTMDet 사람 검출
        ├─ RTMPose Halpe26 추론
        ├─ JSON 및 렌더링 영상 생성
        ├─ Results Bucket 업로드
        └─ PostgreSQL SUCCESS 또는 FAILED
             │
             ▼
Client
  └─ GET /jobs/{job_id}
```

## 4. 지금까지 한 작업: WHAT / WHY / HOW / RESULT

### 4.1 GitHub monorepo 구성

**WHAT**

FastAPI, Worker, Compose, 추론 코드를 하나의 저장소에서 관리했다.

**WHY**

MVP 단계에서 frontend/backend/model 저장소를 너무 일찍 분리하면
배포 버전과 설정을 맞추는 비용이 커지기 때문이다.

**HOW**

```text
api/
worker/
compose.yaml
compose.poc.yaml
```

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

**RESULT**

코드는 GitHub에 저장되고 인증정보·모델·영상은 서버에만 남는다.

### 4.2 RTMPose 영상 POC

**WHAT**

RTMDet nano로 사람을 검출하고 RTMPose-M Halpe26으로 26개 keypoint를 추론했다.

**WHY**

이미지 한 장이 아니라 실제 영상 전체가 현재 OCI CPU 환경에서 처리 가능한지 확인해야 했다.

**HOW**

```text
영상
→ 프레임 추출
→ 사람 검출
→ 자세 추론
→ pose_predictions.json
→ skeleton 렌더링
→ rendered.mp4
```

모델은 Git에 넣지 않고 OCI Runtime에 둔다.

```text
/home/ubuntu/runners-feed-runtime/models/detectors/
/home/ubuntu/runners-feed-runtime/models/pose/
```

**RESULT**

- 샘플 500프레임 처리 성공
- Halpe26 26개 keypoint 출력
- 약 90~94초 처리

### 4.3 Celery inference worker

**WHAT**

무거운 영상 추론을 API 요청과 분리된 Celery worker에서 실행했다.

**WHY**

API 프로세스에서 90초 동안 추론하면 HTTP 요청이 막히고 장애 복구가 어렵기 때문이다.

**HOW**

전용 queue:

```text
inference
```

전용 task:

```text
inference.run_object_storage
inference.run_video
```

`inference.run_video`는 로컬 수동 테스트용이고,
실제 API 흐름은 `inference.run_object_storage`를 사용한다.

**RESULT**

API는 즉시 Job ID를 반환하고 worker가 비동기로 추론한다.

### 4.4 Object Storage 연결

**WHAT**

Worker가 Raw Bucket에서 영상을 받고 Results Bucket에 결과를 올리도록 연결했다.

**WHY**

영상과 결과를 Docker 컨테이너 파일시스템에만 저장하면
컨테이너 교체 시 잃을 수 있기 때문이다.

**HOW**

OCI SDK config는 컨테이너에서 다음 경로로 통일했다.

```text
/.oci/config
/.oci/runners_feed_team4_api_key.pem
```

호스트 mount:

```yaml
- /home/ubuntu/.oci:/.oci:ro
```

**RESULT**

다운로드 → 추론 → 결과 3개 업로드가 성공했다.

### 4.5 non-root Worker

**WHAT**

Inference worker를 root가 아닌 OCI 호스트 UID/GID로 실행했다.

**WHY**

모델 코드나 라이브러리가 침해돼도 root 권한으로 컨테이너 전체를 제어하지 못하도록 하기 위해서다.

**HOW**

OCI `.env`:

```dotenv
INFERENCE_UID=1001
INFERENCE_GID=1001
```

Compose:

```yaml
user: "${INFERENCE_UID:-1000}:${INFERENCE_GID:-1000}"
```

**RESULT**

실제 worker UID/GID는 `1001/1001`이다.
Celery가 이미지 내부 passwd에 이름이 없는 숫자 UID를 경고할 수 있지만 실제 root는 아니다.

### 4.6 작업 재실행 안전성

**WHAT**

각 작업이 `case_id`가 아니라 Celery `job_id` 전용 Runtime 폴더와 Object Storage 경로를 사용하게 했다.

**WHY**

같은 case를 다시 실행하거나 Worker가 중간에 종료돼 task가 재전달될 때
기존 출력 폴더와 충돌하는 문제를 막기 위해서다.

**HOW**

```text
/workspace/run/{job_id}/
jobs/{job_id}/
```

재전달된 같은 작업은 해당 Job ID의 불완전한 Runtime 폴더만 정리하고 다시 실행한다.

**RESULT**

서로 다른 작업 결과가 덮어써지지 않는다.

### 4.7 PostgreSQL 작업 상태

**WHAT**

`inference_jobs` 테이블을 만들고 작업 상태와 결과 경로를 저장했다.

**WHY**

Redis/Celery 결과만 사용하면 장기 보존, 검색, 사용자별 작업 목록, 장애 분석이 어렵기 때문이다.

**HOW**

상태:

```text
QUEUED → PROCESSING → SUCCESS
                    └→ FAILED
```

주요 필드:

```text
job_id
case_id
input_object_name
status
result_details_object
result_predictions_object
result_video_object
error_code
created_at
started_at
completed_at
updated_at
```

**RESULT**

API로 작업 생성부터 완료까지 상태와 시간을 조회할 수 있다.

### 4.8 작업 API

**WHAT**

작업 생성과 조회 API를 구현했다.

**WHY**

프론트엔드나 데모 클라이언트가 Celery를 직접 알지 않고도 추론을 요청해야 하기 때문이다.

**HOW**

```text
POST /jobs
GET  /jobs/{job_id}
```

현재 API는 OCI 내부 `127.0.0.1:8000`에서만 접근 가능하다.

**RESULT**

샘플 작업에서 다음 상태 전이가 실제로 확인됐다.

```text
QUEUED → PROCESSING → SUCCESS
```

## 5. Docker 서비스 역할

```text
postgres          작업 상태와 결과 메타데이터
redis             Celery broker와 결과 backend
api               FastAPI
worker            기존 일반 테스트 Celery worker
inference-worker  RTMPose 전용 Celery worker
inference-poc     수동 Docker 모델 테스트 전용
```

`inference-poc`는 삭제하지 않았다. 자동 실행되지 않도록 `manual-poc` profile로 분리했다.

## 6. API 사용 방법

### Health

```bash
curl http://127.0.0.1:8000/health
```

정상 출력:

```json
{"status":"ok"}
```

### PostgreSQL·Redis Health

```bash
curl http://127.0.0.1:8000/health/dependencies
```

정상 출력:

```json
{
  "status": "ok",
  "dependencies": {
    "postgres": "ok",
    "redis": "ok"
  }
}
```

### Object Storage Health

```bash
curl http://127.0.0.1:8000/health/storage
```

### 샘플 작업 생성

**WHERE**: OCI 서버

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "demo-sample",
    "input_object_name": "poc/test1.mp4"
  }'
```

응답의 `job_id`를 기록한다.

### 작업 상태 조회

```bash
curl http://127.0.0.1:8000/jobs/<JOB_ID>
```

완료 시 응답 예시:

```json
{
  "job_id": "<JOB_ID>",
  "status": "SUCCESS",
  "result_objects": {
    "details": "jobs/<JOB_ID>/details.json",
    "predictions": "jobs/<JOB_ID>/pose_predictions.json",
    "rendered_video": "jobs/<JOB_ID>/rendered.mp4"
  }
}
```

## 7. OCI 시작 방법

### 7.1 VM 시작

**WHERE**: OCI Console

```text
Compute → Instances → 대상 VM → Start
```

상태가 `Running`이 될 때까지 기다린다.

### 7.2 SSH 접속

**WHERE**: 맥북

```bash
ssh -i ~/.ssh/runners-feed-oci.key ubuntu@<OCI_PUBLIC_IP>
```

### 7.3 최신 main 가져오기

**WHERE**: OCI 서버

OCI checkout은 초기 single-branch fetch 설정 때문에 명시적으로 main을 가져온다.

```bash
cd ~/runners-feed-poc-deploy

git fetch origin \
  refs/heads/main:refs/remotes/origin/main

git switch main
git merge --ff-only refs/remotes/origin/main
```

### 7.4 Docker 시작

```bash
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  up -d
```

### 7.5 상태 확인

```bash
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  ps
```

정상 서비스:

```text
postgres          healthy
redis             healthy
api               healthy
worker            Up
inference-worker  Up
```

`inference-poc`는 평상시 실행되지 않는 것이 정상이다.

## 8. 수동 POC 실행 방법

**WHAT**

Celery와 API를 통하지 않고 Docker 안에서 추론 파이프라인만 검사한다.

**WHY**

모델 코드나 Docker image 문제인지 API·queue 문제인지 분리해서 진단할 수 있다.

**HOW**

```bash
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile manual-poc \
  run --rm inference-poc test1
```

평상시 `up -d`에는 포함하지 않는다.

## 9. 결과를 맥북으로 가져오는 방법

Job ID를 알고 있을 때:

```bash
mkdir -p ~/OCI/runtime/demo/<JOB_ID>

scp -i ~/.ssh/runners-feed-oci.key \
  ubuntu@<OCI_PUBLIC_IP>:/home/ubuntu/runners-feed-runtime/run/<JOB_ID>/outputs/details.json \
  ubuntu@<OCI_PUBLIC_IP>:/home/ubuntu/runners-feed-runtime/run/<JOB_ID>/outputs/pose_predictions.json \
  ubuntu@<OCI_PUBLIC_IP>:/home/ubuntu/runners-feed-runtime/run/<JOB_ID>/outputs/rendered.mp4 \
  ~/OCI/runtime/demo/<JOB_ID>/
```

`runtime/`은 Git에서 제외되므로 결과 영상이 실수로 push되지 않는다.

## 10. 코드 수정과 배포 표준 절차

### 10.1 맥북에서 기능 branch 생성

```bash
cd ~/OCI
git switch main
git pull --ff-only origin main
git switch -c feat/<FEATURE_NAME>
```

### 10.2 수정 전 확인

```bash
git status --short
```

기존 사용자 변경을 덮어쓰지 않는다.

### 10.3 검사

Python 예시:

```bash
python3 -c 'from pathlib import Path; p=Path("path/to/file.py"); compile(p.read_text(), str(p), "exec"); print("PASS")'
```

Compose 검사:

```bash
POSTGRES_DB=test \
POSTGRES_USER=test \
POSTGRES_PASSWORD=test \
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  config --quiet
```

Git 공백 검사:

```bash
git diff --check
```

### 10.4 선택적 stage

```bash
git add <수정한 파일만 명시>
```

초기·보안 작업에서는 `git add .`를 사용하지 않는다.

### 10.5 commit과 push

```bash
git commit -m "feat: describe change"
git push -u origin feat/<FEATURE_NAME>
```

### 10.6 검증 후 main 병합

팀 리뷰가 가능하면 GitHub Pull Request를 사용한다.

로컬 merge 예시:

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff feat/<FEATURE_NAME> -m "merge: describe change"
git push origin main
```

### 10.7 OCI 배포

```bash
cd ~/runners-feed-poc-deploy

git fetch origin \
  refs/heads/main:refs/remotes/origin/main

git switch main
git merge --ff-only refs/remotes/origin/main
```

변경된 서비스만 빌드하고 재생성한다.

API와 inference worker 예시:

```bash
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  build api inference-worker

docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  up -d --no-deps --force-recreate api inference-worker
```

## 11. 안전한 종료

### Docker 정상 종료

**WHERE**: OCI 서버

```bash
cd ~/runners-feed-poc-deploy

docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  stop
```

### SSH 종료

```bash
exit
```

### VM Stop

**WHERE**: OCI Console

```text
Compute → Instances → 대상 VM → Stop
```

`Terminate`는 VM 삭제이므로 누르지 않는다.

터미널에서 `shutdown`만 하면 OCI Console의 Compute 상태·과금이 중지되지 않을 수 있으므로
OCI Console에서도 반드시 Stop 상태를 확인한다.

## 12. 보안 원칙

절대 Git에 포함하지 않는다.

```text
.env
*.key
*.pem
.oci/
실제 영상
ONNX/PT/PTH 모델
Runtime 결과
```

확인 명령:

```bash
git status --short
git check-ignore -v .env
```

Private key를 Public GitHub, 메일, 메신저, iCloud 공유 폴더에 올리지 않는다.

키나 비밀번호가 한 번이라도 Public GitHub에 push되면 파일 삭제만으로 해결되지 않는다.
즉시 키를 폐기·회전하고 Git 기록도 정리해야 한다.

## 13. 문제 진단

### API가 응답하지 않음

```bash
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  ps

docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  logs --tail=100 api
```

### Worker가 작업을 받지 않음

```bash
docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  logs --tail=100 inference-worker
```

확인할 내용:

```text
Connected to redis://redis:6379/1
queue: inference
celery ready
```

### OCI 인증 오류

키 내용은 출력하지 않는다.

```bash
test -r /home/ubuntu/.oci/config && echo CONFIG=PASS
test -r /home/ubuntu/.oci/runners_feed_team4_api_key.pem && echo KEY=PASS
```

컨테이너 경로:

```text
/.oci/config
/.oci/runners_feed_team4_api_key.pem
```

### PostgreSQL 상태 확인

```bash
curl http://127.0.0.1:8000/health/dependencies
```

### Docker service 이름을 터미널에 입력하지 않기

다음은 명령어가 아니라 서비스 이름이다.

```text
postgres
redis
api
worker
inference-worker
```

실행·확인은 반드시 `docker compose ...` 명령으로 한다.

## 14. 알려진 제한사항

### 렌더링 누락 프레임

사람이 검출되지 않은 프레임은 현재 렌더링 단계에서 빠질 수 있다.
그 결과 영상 길이와 프레임 타이밍이 달라질 수 있다.

현재 샘플은 500프레임 모두 검출되어 시연에는 영향이 없었다.

### 다중 인물 대상 선택

여러 사람이 있는 프레임에서 렌더링 코드가 항상 추적 대상이 아닌 첫 번째 사람을 선택할 수 있다.

### 최대 메모리 미측정

처리 시간은 측정했지만 peak memory는 아직 측정하지 않았다.

### 외부 접속 미구현

API는 현재 다음 주소에만 bind되어 있다.

```text
127.0.0.1:8000
```

외부 웹·프론트에서는 아직 직접 접근할 수 없다.

### 결과 URL 미구현

API는 Object Storage 객체 이름을 반환하지만 브라우저에서 바로 열 수 있는 서명 URL은 반환하지 않는다.

### 업로드 API 미구현

샘플 객체는 미리 Raw Bucket에 올려져 있다.
사용자가 영상을 올릴 수 있는 Pre-Authenticated Request 또는 Pre-Signed Upload URL API는 아직 없다.

### 정식 DB migration 미구현

현재 API 시작 시 `CREATE TABLE IF NOT EXISTS`로 MVP 테이블을 만든다.
운영 단계에서는 Alembic 같은 migration 도구가 필요하다.

### 고급 모니터링·백업 미구현

중앙 로그, 알림, PostgreSQL 백업, Object Storage Lifecycle 정책은 아직 없다.

## 15. 앞으로 할 작업: WHAT / WHY / HOW

### 우선순위 1: 결과 다운로드 URL API

**WHAT**

`GET /jobs/{job_id}`가 결과 객체 이름과 함께 일정 시간 유효한 다운로드 URL을 반환한다.

**WHY**

현재 프론트엔드는 `jobs/.../rendered.mp4`라는 객체 이름만 받아서는 영상을 재생할 수 없다.

**HOW**

- OCI Object Storage Pre-Authenticated Request 또는 backend download endpoint 사용
- Job이 `SUCCESS`일 때만 URL 생성
- URL 만료시간 설정
- 다른 Job의 결과를 조회하지 못하도록 사용자 권한 검사

### 우선순위 2: 영상 업로드 API

**WHAT**

프론트가 Raw Bucket에 영상을 직접 업로드할 수 있는 제한된 업로드 URL을 발급한다.

**WHY**

큰 영상을 FastAPI 서버가 직접 받아 전달하면 API 메모리·대역폭 부하가 커진다.

**HOW**

```text
POST /uploads
→ 업로드 URL과 object_name 반환
→ 프론트가 Object Storage에 직접 업로드
→ POST /jobs로 분석 시작
```

검사 항목:

- 허용 확장자와 Content-Type
- 최대 파일 크기
- 사용자별 object prefix
- 업로드 완료 여부

### 우선순위 3: Nginx·도메인·HTTPS

**WHAT**

외부에서 API를 안전하게 호출할 수 있도록 443 포트를 연다.

**WHY**

현재 `127.0.0.1:8000`은 VM 내부에서만 접근 가능하다.

**HOW**

- Nginx reverse proxy
- 도메인 DNS 연결
- Let's Encrypt TLS 인증서
- OCI Security List/NSG에서 80·443만 허용
- Uvicorn 8000 포트는 계속 외부에 직접 공개하지 않음

### 우선순위 4: 인증과 권한

**WHAT**

누가 어떤 Job과 결과에 접근할 수 있는지 통제한다.

**WHY**

외부 공개 후 인증이 없으면 누구나 영상 작업을 생성해 비용과 개인정보 문제가 발생할 수 있다.

**HOW**

- 초기 MVP API key 또는 사용자 JWT
- Job에 user_id 추가
- 생성·조회·다운로드 권한 검사
- rate limit
- 키 회전 절차

### 우선순위 5: 테스트와 GitHub Actions

**WHAT**

PR마다 API·DB·Worker 검사를 자동 실행한다.

**WHY**

현재 GitHub PR의 `Checks`가 0개이므로 문법·구성·회귀를 사람이 직접 확인해야 한다.

**HOW**

- Python unit test
- API integration test
- PostgreSQL·Redis service container
- Docker Compose config 검사
- private key·secret scan
- 실제 모델 추론은 큰 모델 없이 작은 fixture 또는 별도 수동 gate로 분리

### 우선순위 6: 모델 후처리 보완

**WHAT**

검출 실패 프레임과 다중 인물 대상 선택을 수정한다.

**WHY**

실제 사용자 영상에서는 사람이 가려지거나 여러 명이 등장할 수 있다.

**HOW**

- 미검출 프레임도 원본 프레임을 출력해 전체 프레임 수 유지
- `track_id == 0`인 사람을 렌더링
- 출력 프레임 수와 원본 프레임 수 일치 검사
- 다중 인물·미검출 fixture 테스트

### 우선순위 7: 운영 안정성

**WHAT**

로그, 모니터링, 백업, 보관기간을 설정한다.

**WHY**

장애를 빠르게 발견하고 DB·영상 손실과 무한 저장 비용을 막기 위해서다.

**HOW**

- Docker·API·Worker 중앙 로그
- FAILED Job 알림
- CPU·메모리·디스크 측정
- PostgreSQL 정기 백업과 복구 테스트
- Raw·Results Bucket Lifecycle 정책
- Runtime 임시 폴더 정리 정책

## 16. AI 작업 진행 보고 원칙

앞으로 모든 변경은 실행 전에 다음 형식으로 설명한다.

### WHAT

무엇을 만들거나 바꾸는지 설명한다.

### WHY

왜 지금 필요한지, 하지 않으면 어떤 문제가 생기는지 설명한다.

### WHERE

다음 중 정확한 실행 환경을 표시한다.

```text
[맥북]
[OCI 서버]
[GitHub]
[OCI Console]
```

### HOW

실행할 명령, 수정 파일, 데이터 흐름을 설명한다.

### EXPECTED

정상 출력과 완료 조건을 설명한다.

### CHANGES

변경되는 파일·서비스·DB·외부 상태를 전부 나열한다.

### VERIFY

성공 여부를 확인할 검사 명령과 결과를 설명한다.

### ROLLBACK

실패 시 되돌릴 범위와 방법을 설명한다.

설명한 범위 밖의 파일이나 서비스를 변경해야 한다는 사실을 작업 중 발견하면,
먼저 중단하고 추가 범위를 설명한 뒤 진행한다.
