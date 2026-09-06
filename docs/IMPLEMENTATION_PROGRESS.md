# 모델·모바일 통합 구현 기록

최종 업데이트: 2026-09-07
브랜치: `feat/model-mobile-v1`
기준 커밋: `d3753fc9c2c28c22492542e35d3f3cdb7c34534c`

## 사용자 결정

- GitHub `main`을 로컬의 기준본으로 사용한다.
- `sehyeon` 모델의 수치·계산 방식을 적용한다.
- OCI 실행에 필요한 서비스 어댑터는 유지한다.
- LLM 모델은 환경변수로 바꿀 수 있게 하고 기본값은 `gpt-5.6-luna`로 둔다.
- 모델러가 새 모델 코드를 전달하면 고정 계약을 통해 바로 교체할 수 있어야 한다.
- 비회원 분석과 Kakao 로그인 전환을 함께 지원한다.
- 모바일 앱은 `mobile/`에 Expo 기반으로 추가한다.

## 지금까지 완료

### Git 기준 정리

- 기존 로컬의 대규모 미커밋 변경을 제거했다.
- `origin/main` 최신 커밋으로 동기화했다.
- 새 작업 브랜치를 만들었다.

### `sehyeon` 수치 적용

`coach/scripts/features/utils.py`에 다음 원본 계산을 적용했다.

- peak 탐색 실패 시 거리 보정값 `distance - 2`, 최소값 `1`
- 잘못된 peak 교대 시 거리 보정값 `distance - 1`, 최소값 `1`
- 원본의 무릎 peak 순서 검증
- 원본의 스트라이드 순번 1~4 계산 방식
- 픽셀-미터 변환 기준을 스트라이드 2번 프레임으로 변경
- GCT 이벤트를 스트라이드 2·4 기준으로 변경
- GCT 탐색 구간을 종료 프레임 이후 10프레임으로 변경
- 발가락 이벤트 임계값을 `0.01m / m_per_pixel`로 변경

### 서비스와 모델의 분리

다음 코드는 모델러가 수정하지 않아도 되는 서비스 연결부다.

- 컨테이너의 `/workspace` 경로
- MP4/MOV 입력 탐색
- 단계 로그 `COACH_STAGE_*`
- H.264 결과 영상 변환
- 모델 결과 JSON 검증
- Object Storage, DB, Celery 연결

### 모델 교체 계약

다음 문서와 템플릿을 추가했다.

- `coach/scripts/model_contract/README.md`
- `coach/scripts/model_contract/model_manifest.example.json`
- `coach/scripts/model_contract/templates/hpe_entrypoint.py`
- `coach/scripts/model_contract/templates/feature_entrypoint.py`
- `coach/scripts/model_contract/validate_artifacts.py`
- `coach/scripts/model_contract/quality_gate.py`
- `coach/scripts/model_contract/quality_baseline.example.json`
- `coach/tests/fixtures/model-golden/`

모델러는 다음 네 가지를 제공하면 된다.

1. pose 엔트리포인트
2. feature 엔트리포인트
3. 출력 artifact 계약을 만족하는 샘플 결과
4. 모델 버전·가중치 SHA-256 manifest

파이프라인은 기본 엔트리포인트를 유지하면서 다음 환경변수로 교체할 수 있다.

```text
COACH_HPE_ENTRYPOINT
COACH_FEATURE_ENTRYPOINT
COACH_AGENT_ENTRYPOINT
```

모델 교체 전에 quality gate가 필수 artifact, feature ID, 단위·범위, 추적률,
처리시간 예산을 검사한다. worker 단계에서도 artifact validator가 실행되므로
출력 파일이 계약을 어기면 해당 작업은 성공으로 기록되지 않는다.

### 모바일 앱 구현

`mobile/`에 Expo SDK 57 + Expo Router 기반 앱을 추가했다.

- 비회원 Bearer 세션을 앱 시작 시 발급하고 SecureStore에 보관
- Kakao system-browser 로그인 후 일회용 exchange code를 native deep link로 교환
- 프로필 키 저장과 분석별 키 override
- 갤러리·카메라 MP4/MOV 선택, signed URL 업로드 진행률 표시
- 분석 stage polling, 실패·장시간 대기 상태, 결과 자동 이동
- 결과 feature 카드, 기준 범위가 없을 때의 명시적 빈 상태, 근거 상세 modal
- 분석 기록과 결과 영상 signed URL 열기

외부 `runners-feed-mobile-app` 참고 구성의 색상·타이포그래피·정보 순서를
React Native 토큰으로 옮겼다. 현재 모델 결과가 `feature1`만 제공하므로 앱은
추가 지표를 추정해 만들지 않고 실제 API feature만 렌더링한다.

### CI/CD 품질과 롤백

- PR CI에 모바일 typecheck와 model quality gate를 추가했다.
- release build 전에 golden artifact quality gate를 실행한다.
- `/api/health/model-quality`는 최근 작업의 성공률·실패율·결과 artifact 누락·
  장시간 처리 작업을 검사한다.
- `deploy/verify_release.sh`가 해당 endpoint의 `status=ok`를 확인한다.
- 검증 실패 시 `deploy/deploy_ghcr_release.sh`가 마지막 성공 immutable tag로
  자동 rollback을 시도한다.

기본 rollback guard는 최근 60분, 최소 완료 3건, 성공률 95% 미만, 실패율 10%
초과, 처리 3600초 초과다. 표본이 3건보다 적으면 `insufficient_sample`로
기록하고 자동 rollback하지 않는다. 운영 환경에서는 `.env`에서 기준을 조정할
수 있다.

## 용어 정리

### 서비스 어댑터란?

모델의 계산값을 바꾸는 코드가 아니다. 모델이 실행될 위치, 입력 파일 위치,
단계 측정, 결과 파일 보관, API 응답 변환을 담당한다. 모델러는 이 부분을
수정하지 않아도 된다.

### Luna란?

자세 keypoint나 러닝 수치를 계산하는 모델이 아니다. `feature_results.json`에
이미 계산된 값을 받아 한국어 코칭 문장을 만드는 선택적 LLM이다. 따라서 Luna가
꺼져도 자세 분석과 수치 결과는 동작한다.

현재 기본값은 `COACH_LLM_MODEL=gpt-5.6-luna`이며 `gpt-5-nano` 등 다른 모델로
환경변수만 바꿀 수 있다. 현재 OpenAI 공식 문서는 비용 중심 고빈도 작업에는
GPT-5.6 Luna를 권장하고, GPT-5 nano도 지원하지만 이전 세대 모델로 표시한다.

## 모델러 전달물 적용 절차

모델러가 코드를 전달하면 다음 순서로 반영한다.

1. 코드와 모델 manifest를 `coach/model_plugins/<model_id>/`에 추가한다.
2. 입력 영상 확장자와 `user_info.json`의 키·단위를 확인한다.
3. 필수 artifact를 생성하도록 엔트리포인트를 연결한다.
4. `validate_artifacts.py`와 worker 단위 테스트를 통과시킨다.
5. 승인된 골든영상으로 수치·추적률·처리시간을 비교한다.
6. 기준을 통과하면 환경변수로 새 엔트리포인트를 선택한다.
7. PR CI와 OCI 배포 검증을 통과시킨다.

모델러 코드는 API, DB, Expo 코드를 직접 수정하지 않는다. 새로운 지표가 추가되면
지표 ID, 단위, 계산식, 기준 범위, 신뢰도, 제한사항을 manifest와 결과 예시에
함께 기록한다.

## 남은 작업

- 실제 OCI에서 DB 백업·복구, Prometheus/Grafana/Alertmanager, maintenance 동작 확인
- 실제 Kakao Developers redirect URI와 Expo development/internal build 검증
- 모델러가 전달하는 실제 골든영상·manifest·가중치 SHA-256을 quality baseline에 반영
- Grafana에 새 model-quality metric panel을 추가하는 운영 대시보드 보강
- 14일 안정성 관찰 후 레거시 경로와 미사용 Docker image 정리
- API 전체 테스트는 로컬 OCI SDK 미설치로 일부 import가 막혀 있어 CI에서 최종 실행

## 자동 진행 기록

사용자가 부재 중에는 이 문서의 결정과 테스트 결과를 기준으로 구현을 계속하도록
승인했다. 외부 OCI 상태 변경·배포 실행은 하지 않았고, 코드·문서·CI 변경만
브랜치에 준비했다.

상세 계약은 [`MODEL_HANDOFF.md`](MODEL_HANDOFF.md)와
[`MOBILE_API.md`](MOBILE_API.md)에 정리했다.
