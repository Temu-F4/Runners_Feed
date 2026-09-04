# OCI·GHCR CI/CD 구축 작업 기록

이 문서는 Runners Feed 프로젝트에 OCI CI VM, OCI Production 배포 Runner,
private GHCR 기반 CI/CD를 구성하면서 실제로 수행한 작업과 검증 결과를 시간
순서대로 기록한다. 최종 운영 방법은 [OCI_GHCR_CICD_RUNBOOK.md](./OCI_GHCR_CICD_RUNBOOK.md)를
참고한다.

## 1. 작업 목표와 기준 구조

작업 시작일: 2026-09-04 (Asia/Seoul)

목표는 다음 구조를 구성하는 것이었다.

```text
외부·내부 PR
    -> GitHub-hosted Runner에서 테스트
    -> main 병합
    -> OCI CI VM에서 Docker 이미지 빌드·테스트
    -> private GHCR Push
    -> OCI Production VM에서 SHA 이미지 Pull·배포
    -> Health Check 실패 시 직전 SHA 롤백
```

공개 저장소의 PR 코드를 OCI Self-hosted Runner에서 실행하지 않도록 PR CI와
Production 배포를 분리했다. OCI Runner는 보호된 `main`의 Release 작업만
실행하도록 구성했다.

## 2. 작업 진행 기록

### 2.1 기존 프로젝트와 OCI 상태 확인

- OCI Production VM의 프로젝트 기준 경로를 확인했다.
- 로컬 프로젝트에는 OCI의 `/home/ubuntu/runners-feed-poc-deploy` 전체 구조를
  동기화했다.
- 동기화 과정에서 파일 내용 변경이 아니라 실행 권한 차이로 많은 파일이 변경된
  것처럼 보이는 상태가 있었다.
- Git의 `core.filemode`를 `false`로 설정해 권한 차이와 실제 소스 변경을
  분리했다.
- OCI에서 가져온 기존 추론 POC 파일은 이번 CI/CD 커밋에 포함하지 않고
  미추적 상태로 보존했다.

### 2.2 CI VM 생성 및 확인

사용자가 생성한 CI VM을 다음과 같이 확인했다.

| 항목 | 결과 |
| --- | --- |
| Public IP | `130.162.148.169` |
| Shape | `VM.Standard.E4.Flex` |
| OCPU / Memory | 2 OCPU / 16GB |
| OS / Architecture | Ubuntu 22.04 LTS / x86_64 |
| Boot Volume | 50GB |
| 초기 여유 디스크 | 약 46GB |

확인 결과 모델 파일을 빌드하거나 실제 영상 추론을 수행하지 않는 CI 구조에서는
50GB가 현재 프로젝트에 충분했다. CI VM에는 Production `.env`, OCI private key,
모델 파일을 복사하지 않았다.

### 2.3 CI VM Docker와 Runner 구성

- Docker Engine과 Docker Compose를 설치했다.
- 설치 후 버전은 Docker `29.8.0`, Compose `5.5.1`, buildx `0.37.0`이었다.
- GitHub Actions Runner `v2.337.0`을 `/opt/actions-runner-ci`에 설치했다.
- 별도 OS 계정 `github-ci`를 만들고 Docker 실행 권한을 부여했다.
- Runner 이름은 `oci-ci-e4`, label은 `oci-ci`로 등록했다.
- systemd 서비스가 등록되어 재부팅 후에도 자동 실행되도록 했다.
- GitHub API에서 Runner 상태가 `online`, `busy=false`임을 확인했다.

Runner 의존성 설치 중 일부 Ubuntu 패키지의 `t64` 버전을 먼저 찾지 못하는
메시지가 있었지만, 현재 Ubuntu 22.04에서 사용 가능한 호환 패키지 설치로
완료되었고 Runner 서비스에는 문제가 없었다.

### 2.4 Production 배포 Runner 구성

기존 Production VM `140.238.0.197`에는 다음을 구성했다.

- 별도 OS 계정 `github-deploy` 생성
- Docker group 권한 부여
- GitHub Actions Runner `v2.337.0` 설치
- Runner 경로 `/opt/actions-runner-deploy`
- Runner 이름 및 label `oci-prod-deploy`
- 배포 상태 경로 `/var/lib/runners-feed-cd`
- 자동 배포용 환경변수 파일 `/etc/runners-feed/prod.env`
- 환경변수 파일 권한 `root:github-deploy`, mode `0640`

기존 Production `.env`를 안전한 경로에 복사했으며, 비밀번호나 키 값은 로그에
출력하지 않았다. 기존 PostgreSQL, Redis, Object Storage, 인증서와 모델 파일은
그대로 유지했다.

### 2.5 Compose와 Docker 이미지 변경

기존 Compose 서비스에 다음 이미지 명명 규칙을 추가했다.

```text
ghcr.io/temu-f4/runners-feed-api:sha-<commit>
ghcr.io/temu-f4/runners-feed-frontend:sha-<commit>
ghcr.io/temu-f4/runners-feed-web:sha-<commit>
ghcr.io/temu-f4/runners-feed-coach-worker:sha-<commit>
```

- 로컬 기본값은 `runners-feed-<service>:local`이다.
- Release에서는 commit SHA 기반 불변 태그를 사용한다.
- 이미지에 `org.opencontainers.image.created`, `revision`, `source` 라벨을
  추가했다.
- `main` alias도 보조적으로 Push하지만 Production 배포에는 사용하지 않는다.
- Production Compose는 `--no-build --no-deps`로 대상 서비스만 갱신한다.
- PostgreSQL, Redis, monitoring 서비스와 volume은 배포 대상에서 제외했다.

### 2.6 GitHub Actions Workflow 구현

추가한 Workflow는 다음 두 개다.

#### PR CI

`.github/workflows/pr-ci.yml`

- GitHub-hosted `ubuntu-latest`에서 실행
- API unit test
- Worker deterministic unit test
- Frontend `npm ci` 및 production build
- Production Compose profile config 검증
- 배포 성공·실패 롤백 스크립트 모의 테스트

#### Release와 Production 배포

`.github/workflows/release-deploy.yml`

- `main` Push 또는 수동 실행에서 시작
- OCI CI Runner `oci-ci`에서 이미지 빌드
- 빌드된 API·Worker 이미지 내부 테스트
- private GHCR에 SHA 태그 Push
- OCI Production Runner `oci-prod-deploy`에서 SHA 이미지 배포
- `/`, `/api/health`, `/api/health/dependencies`, `/api/health/storage` 확인
- 실패 시 마지막 성공 SHA 이미지로 자동 롤백

### 2.7 배포·롤백 스크립트 구현

`deploy/deploy_ghcr_release.sh`에 다음 안전장치를 넣었다.

- `sha-`로 시작하는 40자리 commit 태그만 허용
- Production 환경변수 파일 읽기 권한 확인
- Compose config 검증
- 이미지 Pull 후 `--no-build --no-deps --wait` 배포
- 네 가지 HTTP Health Check
- 마지막 성공 버전을 `/var/lib/runners-feed-cd/last-successful.env`에 원자적으로 기록
- 실패 시 이전 immutable SHA 재배포
- 롤백에 성공해도 GitHub Job은 실패로 남겨 문제를 숨기지 않음

### 2.8 GitHub Environment와 보호 규칙

- `production` Environment를 만들었다.
- `PRODUCTION_BASE_URL=https://140.238.0.197` 변수를 등록했다.
- Environment는 보호된 branch에서만 배포되도록 설정했다.
- `main`에 PR 필수 규칙을 적용했다.
- API tests, Worker tests, Frontend build, Compose config를 필수 체크로 지정했다.
- 관리자도 직접 Push와 force push를 할 수 없도록 설정했다.
- 대화 해결이 되지 않은 PR은 병합할 수 없도록 설정했다.

## 3. 검증 과정과 발생한 문제

### 3.1 정적 검사 도구 호출 문제

처음 컨테이너에서 `actionlint`를 실행할 때 다음 문제가 있었다.

- Git metadata가 없는 임시 디렉터리에서 실행해 프로젝트를 찾지 못함
- 임시 디렉터리 권한이 컨테이너 사용자에게 읽기 불가
- 사용자 정의 Runner label을 인식하지 못함
- Shell script에서 ShellCheck 경고 발생

해결 내용:

- Workflow 파일 경로를 명시해 `actionlint`를 실행했다.
- 검사 디렉터리 읽기 권한을 조정했다.
- `.github/actionlint.yaml`에 `oci-ci`, `oci-prod-deploy` label을 등록했다.
- ShellCheck의 변수 선언 관련 경고를 수정했다.

최종적으로 `actionlint`와 `shellcheck`가 모두 통과했다.

### 3.2 배포 롤백 동작 검증

처음에는 실제 GHCR 이미지를 배포하지 않고 Docker와 curl을 모킹하는 테스트를
작성했다.

- 성공 태그 배포 후 상태 파일 기록 확인
- 실패 태그 배포 확인
- 이전 SHA 자동 롤백 확인
- 롤백 성공 후에도 원래 Job이 실패 상태를 유지하는지 확인

성공 메시지:

```text
Deployment success and rollback tests passed
```

### 3.3 Production에서 발견한 기존 502 문제

새 CI/CD 배포 전 Production URL을 동일한 Health Check로 확인했을 때 네
엔드포인트가 502를 반환했다.

원인은 다음과 같았다.

- API와 Frontend 컨테이너는 Healthy 상태였다.
- 장시간 실행 중인 Nginx가 컨테이너 재생성 전의 예전 IP를 upstream으로 계속
  사용하고 있었다.
- Nginx 로그에 `connect() failed (111: Connection refused)`가 기록되어 있었다.

해결 내용:

1. Production Nginx 설정 문법을 확인했다.
2. Nginx를 무중단 reload했다.
3. 네 엔드포인트가 HTTP 200으로 복구된 것을 확인했다.
4. `api`와 `frontend` upstream을 변수 기반 `proxy_pass`로 변경했다.
5. Docker DNS resolver 주기를 5초로 설정하고 `resolver_timeout`을 추가했다.
6. 임시 Docker network에서 upstream 컨테이너 IP를 교체한 뒤 Nginx가 새 IP로
   연결하는지 확인했다.

최종 동적 DNS 검증 결과:

```text
NGINX_DYNAMIC_DNS_OK old=172.18.0.2 new=172.18.0.5 code=404
```

여기서 `404`는 임시 테스트 서버에 index 파일이 없어서 발생한 응답이며,
Nginx가 upstream에 연결하지 못했을 때의 `502`가 아니므로 DNS 재연결 자체는
성공한 것으로 판단했다. 실제 Production Health Check는 네 항목 모두 200이었다.

### 3.4 최신 main 기준점 불일치

로컬 `origin/main` 참조가 실제 원격 `main`보다 뒤처져 있었다. 로컬 fetch
설정이 특정 feature branch만 추적하고 있었기 때문이다.

해결 내용:

- 원격 `main`을 명시적으로 fetch했다.
- CI/CD 커밋을 최신 `main` 위로 rebase했다.
- 최신 소스 기준으로 이미지 빌드와 테스트를 다시 수행했다.

## 4. 최종 검증 결과

### 로컬·CI VM 검증

| 검증 항목 | 결과 |
| --- | --- |
| Bash 문법 검사 | 통과 |
| actionlint | 통과 |
| shellcheck | 통과 |
| Compose production profile config | 통과 |
| Deployment success/rollback 모의 테스트 | 통과 |
| API image tests | 17개 통과 |
| Worker image tests | 13개 통과 |
| Frontend production build | 통과 |
| 4개 운영 이미지 실제 빌드 | 통과 |
| OCI 이미지 revision label 확인 | 4개 모두 통과 |
| Nginx upstream IP 교체 테스트 | 통과 |

최신 CI VM 빌드 후 디스크 상태:

```text
Disk: 49G total / 18G used / 31G available / 37%
```

### GitHub 검증

- PR: [Temu-F4/Runners_Feed#3](https://github.com/Temu-F4/Runners_Feed/pull/3)
- Branch: `feat/oci-ghcr-cicd`
- Commit: `bbf096399ae6ab111ce12ada15d2d439a1907d1d`
- PR 상태: Open, mergeable
- API tests: Passed
- Worker tests: Passed
- Frontend build: Passed
- Compose config: Passed

### OCI 최종 상태

- CI Runner `oci-ci-e4`: Online, systemd active
- Production Runner `oci-prod-deploy`: Online, systemd active
- Production `/`: HTTP 200
- Production `/api/health`: HTTP 200
- Production `/api/health/dependencies`: HTTP 200
- Production `/api/health/storage`: HTTP 200

## 5. 아직 수행하지 않은 작업

다음 작업은 의도적으로 남겨두었다.

- PR 병합
- 최초 GHCR private package 생성
- 최초 SHA 이미지 Production 배포
- 최초 배포 후 `last-successful.env` 생성 확인
- 영상 업로드부터 Coach 분석 결과 조회까지 실제 E2E 검증

PR 병합은 GHCR Push와 Production 변경을 동시에 발생시키므로, 검토 후 별도
승인을 받아 수행한다. 최초 배포는 GHCR에 직전 성공 SHA가 아직 없기 때문에
자동 이미지 롤백 대상이 없다. 최초 배포가 성공하면 이후부터 자동 롤백 상태가
축적된다.

## 6. 현재 커밋에 포함하지 않은 파일

OCI 동기화 과정에서 발견된 기존 추론 POC 관련 미추적 파일은 이번 CI/CD 커밋에
포함하지 않았다. 해당 파일은 로컬 작업 디렉터리에 보존되어 있으며, 이번
커밋에는 다음 CI/CD 관련 파일만 포함했다.

- `.github/workflows/`
- `deploy/deploy_ghcr_release.sh`
- `deploy/test_deploy_ghcr_release.sh`
- `docs/OCI_GHCR_CICD_RUNBOOK.md`
- 이미지 태그·메타데이터를 반영한 Compose와 Dockerfile
- Nginx upstream DNS 재해석 수정

## 7. 최종 판단

CI/CD 기반 구축과 자동 검증 구조는 구현·검증 완료 상태다. 현재 남은 단계는
코드 문제가 아니라 최초 Production 전환 승인이다. PR 체크와 보호 규칙을 모두
통과한 뒤 병합하면 private GHCR 이미지 생성과 OCI 자동 배포 흐름을 시작할 수
있다.
