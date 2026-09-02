# OCI Overview 대시보드 사용 설명서

이 문서는 Grafana의 `Runners Feed / OCI Overview` 대시보드에서 각 수치를
읽고 호스트 또는 컨테이너 이상 여부를 판단하는 방법을 설명한다.

```text
접속 주소: https://140.238.0.197/grafana/
Dashboard: Runners Feed / OCI Overview
기본 표시 범위: 최근 1시간
Dashboard 갱신: 1초
```

## 1. 먼저 알아둘 기준

- `Host` 또는 `Node Exporter`는 OCI VM 전체를 의미한다.
- `Container` 또는 `cAdvisor`는 Docker Compose service별 자원 사용량을 의미한다.
- Grafana 오른쪽 위 시간 범위를 변경하면 시계열 그래프의 조회 기간이 바뀐다.
- 범례를 클릭하면 특정 항목만 숨기거나 집중해서 볼 수 있다.
- 그래프 위에 마우스를 올리면 해당 시각의 실제 값을 확인할 수 있다.
- CPU와 network는 누적 counter가 아니라 일정 구간의 변화율인 `rate`로 표시한다.

대시보드에 보이는 대표 Compose service 이름은 다음과 같다.

| 표시 이름 | 역할 |
|---|---|
| `api` | FastAPI backend |
| `web` | 외부 HTTPS와 reverse proxy를 담당하는 Nginx |
| `frontend` | Next.js 화면 |
| `worker` | 일반 Celery worker |
| `inference-worker` | 영상 추론 Celery worker |
| `postgres` | 작업과 단계 데이터 DB |
| `redis` | Celery broker/result backend |
| `ollama` | 로컬 LLM/embedding service |
| `prometheus`, `grafana` | 모니터링 저장·시각화 |
| `node-exporter`, `cadvisor` | 호스트·컨테이너 metric 수집 |
| `alertmanager` | 알람 grouping·silence·routing |
| `host-metrics-collector` | 디렉터리·파일·프로세스 상세 metric 생성 |

사용자가 말하는 backend는 이 대시보드에서 주로 `api`, Nginx는 `web`으로
표시된다.

## 2. 최상단 Overview

### Overview / CPU

OCI VM 전체 CPU 사용률의 최근 1분 rate다.

| 색상 | 범위 | 해석 |
|---|---:|---|
| 초록 | 70% 미만 | 일반적으로 정상 |
| 노랑 | 70% 이상 80% 미만 | 부하 증가 관찰 |
| 빨강 | 80% 이상 | 알람 기준 도달 |

순간적으로 빨간색이 되더라도 5분 동안 계속 80% 이상이어야
`HostCpuUsageHigh` 알람이 firing 상태가 된다.

### Overview / Memory

`MemTotal`에서 `MemAvailable`을 제외한 비율이다. `MemAvailable`에는 즉시 회수할
수 있는 cache가 고려되므로 단순한 `MemFree`보다 실제 부족 여부를 판단하기 좋다.

- 초록: 70% 미만
- 노랑: 70% 이상 80% 미만
- 빨강: 80% 이상
- 80% 이상이 5분 지속되면 `HostMemoryUsageHigh`

### Overview / Root Disk

OCI VM의 `/` 파일시스템 사용률이다.

- 초록: 80% 미만
- 노랑: 80% 이상 90% 미만
- 빨강: 90% 이상
- 80~90%가 5분 지속되면 warning
- 90% 이상이 5분 지속되면 critical

이 gauge는 루트 파일시스템만 보여준다. 다른 mount는 아래의
`Filesystem Usage by Mount`에서 확인한다.

## 3. 수집기와 알람 상태

### Node Exporter / cAdvisor

- `UP`: Prometheus가 해당 exporter를 정상적으로 수집하고 있다.
- `DOWN`: 수집할 수 없는 상태다.
- 1분 동안 DOWN이면 각각 `NodeExporterDown`, `CAdvisorDown` critical 알람이
  발생한다.

서비스 컨테이너가 실제로 고장 난 것과 exporter가 DOWN인 것은 구분해야 한다.
cAdvisor DOWN은 컨테이너 metric을 읽을 수 없다는 뜻이지 모든 서비스가 동시에
중단됐다는 뜻은 아니다.

### VM Uptime

OCI VM이 마지막으로 부팅된 이후의 경과 시간이다. 예상하지 못하게 값이 작아지면
VM이 재부팅됐는지 확인한다.

### Firing Alerts

- `0`과 초록색: 현재 firing 알람 없음
- `1` 이상과 빨간색: 하단 `Pending / Firing Alerts`에서 이름과 대상을 확인

`pending`은 조건에 도달했지만 정해진 지속 시간을 아직 채우지 않은 상태고,
`firing`은 지속 시간까지 충족한 상태다.

## 4. Node Exporter / OCI VM 상세

### Host CPU & Memory

CPU와 memory 사용률의 시간에 따른 변화를 같은 그래프에서 비교한다. 영상 작업을
실행한 시각에 CPU가 먼저 상승하고 memory가 함께 증가했는지 확인할 수 있다.

CPU는 1분 rate이므로 실제 작업이 끝난 직후에도 직전 고부하 sample이 계산 구간에
포함되어 최대 약 1분 동안 완만하게 내려갈 수 있다. 이것이 곧 작업이 계속 실행
중이라는 의미는 아니다. Job의 실제 완료 여부와 단계 시간은
`Runners Feed / Job Stage Performance`에서 확인한다.

### Filesystem Usage by Mount

실제 디스크 filesystem별 사용률이다. 각 막대의 `mountpoint`와 `device`를 함께
확인한다. `tmpfs`, Docker overlay와 `/run` 계열은 제외한다.

### Host Network Receive / Transmit

OCI VM의 물리 network interface별 초당 전송량이다.

- `receive`: VM으로 들어오는 bytes/sec
- `transmit`: VM에서 나가는 bytes/sec
- `lo`, Docker bridge, `veth` 같은 내부 virtual interface는 제외

영상 다운로드 시 receive가, Object Storage 결과 업로드 시 transmit이 증가할 수
있다. 값이 0에 가까운 것은 해당 시점에 통신량이 적다는 뜻이다.

## 5. 디렉터리·파일·프로세스 상세

### Largest Host Directories

아래 경로에서 용량이 큰 디렉터리 상위 20개를 표시한다.

```text
/home/ubuntu
/var/lib/docker
/var/log
/tmp
```

5분마다 갱신한다. 부모 디렉터리 용량에는 자식 디렉터리 용량이 포함되므로 여러
막대 값을 서로 더하면 안 된다. 예를 들어 `/home/ubuntu`와
`/home/ubuntu/runners-feed-runtime`은 포함 관계일 수 있다.

### Largest Host Files (>= 10 MiB)

다음 범위에서 10MiB 이상인 파일의 상위 20개를 5분마다 표시한다.

```text
/home/ubuntu
/var/log
/var/lib/docker/volumes
```

모델 blob, 영상 결과, PostgreSQL WAL, Prometheus WAL/chunk, system journal 등이
나올 수 있다. 이 패널은 원인을 찾는 용도이며, 크다는 이유만으로 파일을 직접
삭제하면 안 된다. Docker volume과 DB/WAL 파일은 반드시 각 서비스의 정리·보존
절차를 사용해야 한다.

### Top Process Memory (RSS)

호스트에서 실제 상주 메모리 RSS를 많이 사용하는 프로세스 상위 20개다.

```text
process 이름 / PID / 실행 파일 경로 / RSS bytes
```

15초마다 갱신한다. 파일이 memory를 사용하는 것이 아니라 해당 실행 파일로 시작된
프로세스가 memory를 사용한다. 같은 실행 파일이라도 PID가 다르면 별도 프로세스로
표시된다. 컨테이너 재시작 후에는 PID가 바뀔 수 있다.

## 6. cAdvisor / Docker Containers

### cAdvisor UP

cAdvisor 수집 상태다. 최상단 cAdvisor 상태와 같은 의미이며 컨테이너 상세 영역에서
즉시 확인할 수 있도록 한 번 더 표시한다.

### Compose Services

cAdvisor가 현재 관찰하는 `runners-feed` Docker Compose service 수다. 이 값은
worker scale-out 또는 모니터링 service 추가·삭제에 따라 달라질 수 있다.

### Container CPU Total

모든 `runners-feed` 컨테이너 CPU rate의 합이다. 이 값의 기준은 다음과 같다.

```text
CPU core 1개를 완전히 사용 = 100%
CPU core 2개를 완전히 사용 = 200%
```

따라서 100% 초과 자체가 장애는 아니다. 호스트 CPU 80% 알람과 혼동하지 않도록
이 패널에는 80% 경보색을 적용하지 않는다.

### Container Working Set

모든 대상 컨테이너의 `working_set_bytes` 합계다. 호스트 전체 memory에는 Docker
외부 프로세스와 kernel memory도 포함되므로 Overview Memory와 값이 일치하지 않는다.

### Container CPU Rate by Service

서비스별 최근 1분 CPU rate다. 예를 들어 다음처럼 각 서비스가 별도 선으로 나온다.

```text
api               4%
web               9%
inference-worker  85%
```

이는 Job 단계가 아니라 Docker Compose service 기준이다. Job 하나의 9단계
처리시간은 Job Stage Performance 대시보드에서 확인한다.

### Container Memory: usage_bytes vs working_set_bytes

각 서비스마다 두 선이 표시된다.

| 값 | 의미 |
|---|---|
| `usage` | page cache를 포함한 cgroup 전체 memory 사용량 |
| `working set` | 비활성 file cache를 제외한 활성 사용량에 가까운 값 |

일반적으로 `usage`가 `working set`보다 크다. 작업이 끝난 후 `working set`은
내려갔지만 `usage`가 더 오래 높다면 해제 가능한 file cache가 남아 있을 가능성이
있다. 두 값이 모두 계속 상승할 때는 memory leak 또는 작업 데이터 유지 여부를
추가 조사한다.

### Container Network Receive / Transmit

서비스별 초당 수신·송신량이다. 누적 전송량이 아니라 최근 1분의 rate다.

- API 요청·입력 다운로드: 관련 service receive 증가 가능
- Object Storage 결과 업로드: `inference-worker` transmit 증가 가능
- Grafana 조회: `grafana`, `prometheus` 내부 통신 증가 가능

## 7. Prometheus Alerts 읽는 법

현재 설정된 알람은 다음과 같다.

| Alert | 발생 조건 | 지속 시간 | 등급 |
|---|---|---:|---|
| `NodeExporterDown` | Node Exporter 수집 실패 | 1분 | critical |
| `CAdvisorDown` | cAdvisor 수집 실패 | 1분 | critical |
| `HostCpuUsageHigh` | 호스트 CPU 80% 이상 | 5분 | warning |
| `HostMemoryUsageHigh` | 호스트 memory 80% 이상 | 5분 | warning |
| `HostDiskUsageWarning` | disk 80% 이상 90% 미만 | 5분 | warning |
| `HostDiskUsageCritical` | disk 90% 이상 | 5분 | critical |

`Pending / Firing Alerts`가 `No data`인 것은 알람이 하나도 없을 때 정상이다. 이
패널의 `No data`는 metric 누락을 뜻하지 않는다. 최상단 exporter 상태가 UP이고
`Firing Alerts`가 0인지 함께 확인한다.

현재 Alertmanager receiver는 `dashboard-only`다. 알람 상태는 Grafana와
Alertmanager에서 확인할 수 있지만 Discord·Slack·Telegram·email 메시지는 아직
발송하지 않는다. 외부 수신 채널을 정한 후 credential을 OCI secret 환경에 별도로
구성해야 한다.

## 8. 상황별 빠른 판단 예시

### 영상 처리가 끝났는데 CPU 선이 바로 내려가지 않음

1. Job Stage Performance에서 Job 상태가 `SUCCESS`인지 확인한다.
2. Container CPU는 1분 rate이므로 약간 늦게 내려가는 것은 정상일 수 있다.
3. 1분 이상 특정 service CPU가 계속 높으면 해당 container log와 실행 task를 본다.

### Memory usage는 높은데 working set은 낮음

page cache 차이일 가능성이 높다. 호스트 memory가 80% 미만이고 working set이
안정적이면 즉시 장애로 판단하지 않는다.

### 디스크 사용률이 높음

1. `Filesystem Usage by Mount`에서 어느 mount인지 확인한다.
2. `Largest Host Directories`에서 큰 영역을 찾는다.
3. `Largest Host Files`에서 구체적인 파일을 확인한다.
4. 파일 종류에 맞는 안전한 보존·정리 절차를 정한 후 삭제한다.

### 디렉터리·파일·프로세스 패널이 No data

배포 직후에는 collector의 첫 결과를 기다린다. 프로세스는 약 15초, storage는
최초 조사 완료 후 표시되며 이후 5분마다 갱신된다. 계속 비어 있으면 다음 명령으로
서비스와 metric을 확인한다.

```bash
cd /home/ubuntu/runners-feed-poc-deploy

docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  ps host-metrics-collector node-exporter prometheus

docker compose \
  -f compose.yaml \
  -f compose.poc.yaml \
  --profile poc \
  logs --tail=100 host-metrics-collector node-exporter prometheus
```

## 9. 대시보드를 볼 때의 안전 원칙

- dashboard 수치만 보고 DB, Docker volume, model 또는 영상 파일을 바로 삭제하지 않는다.
- 높은 값이 순간 spike인지 지속 상태인지 시간 범위를 넓혀 확인한다.
- 호스트 수치와 컨테이너 수치를 함께 비교한다.
- Job별 성능 문제는 OCI Overview가 아니라 Job Stage Performance에서 단계별로 본다.
- critical 알람은 원인 확인 후 조치하며 모니터링 exporter만 재시작해 알람을 숨기지 않는다.
