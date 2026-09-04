# OCI Self-hosted Runner와 GHCR 기반 CI/CD 운영 가이드

## 1. 목적

이 문서는 Runners Feed의 Pull Request 검증, Docker 이미지 빌드, GHCR 배포,
OCI Production 반영과 실패 시 롤백 절차를 설명한다.

실제 구축 중 수행한 작업, 발생한 문제와 해결 과정, 검증 결과는
[OCI_GHCR_CICD_IMPLEMENTATION_LOG.md](./OCI_GHCR_CICD_IMPLEMENTATION_LOG.md)에
기록되어 있다.

CI와 CD는 서로 다른 OCI VM에서 실행한다.

```text
외부·내부 Pull Request
        |
        v
GitHub-hosted Runner
  - API unit test
  - Worker unit test
  - Frontend build
  - Compose validation
        |
        v main merge
OCI CI VM: 130.162.148.169
  - Docker image build
  - Built-image test
  - Private GHCR push
        |
        v
OCI Production VM: 140.238.0.197
  - SHA image pull
  - Docker Compose deployment
  - Health check
  - Automatic rollback
```

공개 저장소의 외부 코드를 Self-hosted Runner에서 직접 실행하지 않는다. PR은
GitHub-hosted Runner에서만 검사하고, OCI Runner는 보호된 `main`에 반영된 코드만
실행한다.

## 2. 구성 현황

### CI VM

| 항목 | 값 |
| --- | --- |
| Hostname | `vnic-t04-build` |
| Public IP | `130.162.148.169` |
| OS | Ubuntu 22.04 LTS x86_64 |
| Shape | VM.Standard.E4.Flex |
| CPU / Memory | 2 OCPU(4 vCPU) / 16GB |
| Boot Volume | 50GB |
| Docker | 29.8.0 |
| Docker Compose | 5.5.1 |
| Runner name | `oci-ci-e4` |
| Runner label | `oci-ci` |
| Runner account | `github-ci` |
| Runner directory | `/opt/actions-runner-ci` |

CI VM에는 Production `.env`, OCI Private Key와 모델 파일을 저장하지 않는다.
모델 파일은 Docker build context에서 제외되며 CI에서 실제 영상 추론을 실행하지
않는다.

### Production VM

| 항목 | 값 |
| --- | --- |
| Hostname | `vnic-t04-mvp` |
| Public IP | `140.238.0.197` |
| OS | Ubuntu 22.04 LTS x86_64 |
| Docker | 29.7.2 |
| Docker Compose | 5.5.0 |
| Runner name | `oci-prod-deploy` |
| Runner label | `oci-prod-deploy` |
| Runner account | `github-deploy` |
| Runner directory | `/opt/actions-runner-deploy` |
| Deployment state | `/var/lib/runners-feed-cd` |
| Production environment | `/etc/runners-feed/prod.env` |

Production Runner는 이미지 빌드와 PR 테스트를 수행하지 않는다. GHCR 이미지를
Pull하고 기존 Compose 서비스를 갱신하는 작업만 담당한다.

## 3. GitHub 설정

저장소와 이미지는 다음 공개 범위를 사용한다.

```text
Repository: public
GHCR packages: private
```

GitHub Actions가 처음 이미지를 Push하면 다음 Package가 생성된다.

```text
ghcr.io/temu-f4/runners-feed-api
ghcr.io/temu-f4/runners-feed-frontend
ghcr.io/temu-f4/runners-feed-web
ghcr.io/temu-f4/runners-feed-coach-worker
```

각 Package의 `Package settings -> Manage Actions access`에서
`Temu-F4/Runners_Feed`에 접근 권한이 있는지 확인한다. Package visibility는
Private으로 유지한다.

`production` Environment에는 다음 변수가 설정되어 있다.

```text
PRODUCTION_BASE_URL=https://140.238.0.197
```

Production 비밀번호와 OCI Key는 GitHub Secret으로 복사하지 않는다. GHCR 인증은
Job마다 발급되는 `GITHUB_TOKEN`을 사용한다.

### main 보호 규칙

다음 설정을 적용한다.

```text
Settings -> Branches 또는 Rules -> main
Require a pull request before merging
Require status checks to pass
Block force pushes
Block deletions
```

필수 Status Check는 첫 PR CI 실행 후 다음 네 개를 선택한다.

```text
API tests
Worker tests
Frontend build
Compose config
```

## 4. Workflow 동작

### PR CI

`.github/workflows/pr-ci.yml`은 `main` 대상 Pull Request에서 실행한다.

- API: Python 3.11 단위 테스트
- Worker: Python 3.12 결정적 단위 테스트
- Frontend: Node 22 `npm ci`, `npm run build`
- Compose: `compose.yaml + compose.coach.yaml --profile coach` 검증
- Secret, OCI Credential과 Self-hosted Runner를 사용하지 않음
- 같은 PR에 새 Commit이 Push되면 이전 실행 취소

### Release와 배포

`.github/workflows/release-deploy.yml`은 `main` Push 또는 수동 실행에서 동작한다.

1. `oci-ci-e4`가 네 개의 이미지를 빌드한다.
2. 빌드된 API·Worker 이미지 내부에서 단위 테스트를 다시 실행한다.
3. `sha-<40자리 commit>` 태그로 GHCR에 Push한다.
4. 편의상 같은 이미지를 `main` 태그로도 Push한다.
5. `oci-prod-deploy`가 SHA 태그를 Pull한다.
6. Production Compose가 `--no-build --no-deps`로 대상 서비스만 갱신한다.
7. Health Check 성공 후 SHA를 마지막 정상 버전으로 기록한다.

Production 배포는 반드시 SHA 태그를 사용한다. 이동 가능한 `main` 태그는 사람이
이미지를 확인할 때만 사용하고 배포 입력으로 사용하지 않는다.

## 5. Production 환경 파일

자동 배포는 다음 파일을 읽는다.

```text
/etc/runners-feed/prod.env
```

권한은 `root:github-deploy`, mode `0640`으로 유지한다. 현재 파일은 기존
`/home/ubuntu/runners-feed-poc-deploy/.env`의 안전한 사본이다.

기존 `.env`를 수정했다면 자동 배포용 파일도 명시적으로 동기화한다.

```bash
sudo install \
  -o root \
  -g github-deploy \
  -m 0640 \
  /home/ubuntu/runners-feed-poc-deploy/.env \
  /etc/runners-feed/prod.env
```

파일 내용을 터미널, GitHub Actions 로그 또는 문서에 출력하지 않는다.

자동 배포에 필요한 이미지 변수는 Workflow가 주입한다.

```text
IMAGE_PREFIX=ghcr.io/temu-f4/runners-feed
IMAGE_TAG=sha-<commit>
```

## 6. 배포 성공 조건

`deploy/deploy_ghcr_release.sh`는 다음 검사를 모두 통과해야 배포를 성공으로
기록한다.

```text
docker compose config --quiet
GHCR image pull
docker compose up --no-build --wait
GET /
GET /api/health
GET /api/health/dependencies
GET /api/health/storage
```

Compose 대상은 다음과 같다.

```text
compose.yaml
compose.coach.yaml
profile: coach
services: api, frontend, web, coach-worker
```

PostgreSQL, Redis, Grafana, Prometheus와 Volume은 삭제하거나 재생성 대상으로
지정하지 않으며 `--no-deps`로 의존 서비스의 암묵적 재생성도 막는다. API의
`/health`가 Healthy가 되기 전에 시작 시점 SQL migration이 완료되어야 한다.

## 7. 롤백

마지막 성공 SHA는 다음 파일에 기록된다.

```text
/var/lib/runners-feed-cd/last-successful.env
```

신규 배포 또는 Health Check가 실패하면 스크립트가 직전 SHA 이미지를 Pull하고
동일한 Compose 명령으로 자동 복귀한다. 롤백 후에도 Job은 실패로 종료해 GitHub에
실패 사실을 남긴다.

수동으로 기존 SHA를 재배포하려면 GitHub에서 다음 순서로 실행한다.

```text
Actions
-> Release GHCR and deploy OCI
-> Run workflow
```

현재 Workflow의 수동 실행은 선택한 Git revision을 다시 빌드한다. 이미 존재하는
SHA를 빌드 없이 재배포하는 기능이 필요하면 별도 수동 Rollback Workflow를 추가한다.

DB migration은 자동으로 되돌리지 않는다. 자동 이미지 롤백을 위해 migration은
기존 코드와 호환되는 테이블·컬럼 추가 방식으로 작성한다. 컬럼 삭제나 이름 변경은
두 번 이상의 Release로 분리한다.

## 8. Runner 운영

### 상태 확인

CI VM:

```bash
sudo systemctl status \
  actions.runner.Temu-F4-Runners_Feed.oci-ci-e4.service
docker version
docker compose version
df -h /
```

Production VM:

```bash
sudo systemctl status \
  actions.runner.Temu-F4-Runners_Feed.oci-prod-deploy.service
docker version
docker compose version
docker ps
```

GitHub에서는 다음 경로에서 Online 상태를 확인한다.

```text
Repository Settings -> Actions -> Runners
```

### CI 디스크 관리

50GB 디스크를 유지하므로 사용률을 주기적으로 확인한다.

```bash
df -h /
docker system df
```

사용률 70%부터 원인을 확인하고, 오래된 BuildKit 캐시만 정리한다.

```bash
docker buildx prune --filter 'until=168h' --force
```

Production VM에서는 자동으로 `docker system prune`, Volume 삭제 또는 전체 이미지
정리를 실행하지 않는다.

## 9. 장애 대응

### Workflow가 대기 상태

- GitHub Settings에서 Runner가 Online인지 확인한다.
- 대상 Job의 `runs-on` label과 Runner label이 같은지 확인한다.
- VM에서 Runner systemd 서비스를 재시작한다.

### GHCR Push 또는 Pull 실패

- Workflow Job의 `packages: write` 또는 `packages: read` 권한을 확인한다.
- Package의 Actions repository access를 확인한다.
- GHCR Package가 Private인지 확인한다.
- Runner에서 `https://ghcr.io` HTTPS 아웃바운드가 가능한지 확인한다.

### Production Health Check 실패

```bash
docker compose \
  --env-file /etc/runners-feed/prod.env \
  -f compose.yaml \
  -f compose.coach.yaml \
  --profile coach \
  logs --tail=150 api frontend web coach-worker
```

GitHub Actions 로그에서 자동 롤백 성공 여부와 이전 SHA를 확인한다. 롤백까지
실패하면 신규 배포를 반복하지 말고 기존 컨테이너, PostgreSQL, Redis와 인증서
상태를 먼저 확인한다.

컨테이너는 Healthy인데 Nginx가 `502 Bad Gateway`를 반환한다면 Nginx가 재생성 전
컨테이너 IP를 기억하고 있는지 확인한다. 현재 설정은 Docker DNS를 5초마다 다시
조회하므로 일시적인 502는 자동 해소되어야 한다. 즉시 복구가 필요하면 설정 검증 후
무중단 reload를 수행한다.

```bash
docker exec runners-feed-web-1 nginx -t
docker exec runners-feed-web-1 nginx -s reload
```

## 10. 최초 전환 체크리스트

- [ ] OCI에서 운영 중인 코드 변경을 검토하고 GitHub branch에 커밋
- [ ] CI/CD Workflow와 Compose 이미지 설정을 PR로 `main`에 병합
- [ ] PR의 네 개 필수 Check 통과
- [ ] `oci-ci-e4`, `oci-prod-deploy` Runner Online 확인
- [ ] `production` Environment 변수 확인
- [ ] `/etc/runners-feed/prod.env` 권한과 최신 상태 확인
- [ ] 첫 GHCR Package 네 개가 Private인지 확인
- [ ] 첫 SHA 배포와 Health Check 통과
- [ ] `/var/lib/runners-feed-cd/last-successful.env` 생성 확인
- [ ] 실행 컨테이너의 이미지 SHA 확인
- [ ] 영상 한 건의 업로드, 분석, 결과 조회 E2E 확인
- [ ] 배포 SHA, Job ID, 수행 시각과 결과 기록

현재 OCI에서만 존재하고 GitHub에 Commit되지 않은 파일은 Workflow가 빌드할 수
없다. 자동 배포를 활성화하기 전에 운영 기준 소스가 `main`에 포함되어야 한다.
