# Project Status

마지막 갱신: 2026-10-02 (Asia/Seoul)

이 문서는 새 Codex 작업과 팀원이 현재 상태를 빠르게 파악하기 위한 인계 문서다.
작업을 시작할 때 `LAB_PLAN.md`, `STAGE_CONTRACTS.md`, 이 문서를 순서대로 읽는다.

## 현재 기준점

- Branch: `main`
- Latest verified commit: `ba90796 Add external API-only RCE proof flow`
- Repository: `https://github.com/seung-ukk/vuln-mlops`
- Container: `ghcr.io/seung-ukk/vuln-mlops`
- 현재 작업 트리: 문서 추가 전 기준 clean

## 완료된 작업

### Application

- FastAPI 기반 ModelGate UI/API
- Pod-local MLflow Tracking/Registry
- 비동기 validation worker
- SQLite job queue
- health/readiness endpoint
- non-root container image와 restricted security context

### Stage 1 SSRF

- MLflow webhook redirect SSRF 경로
- Docker-internal synthetic canary
- marker-only safe PoC
- 외부 MLflow 노출 없이 ModelGate API를 통한 검증

### Stage 1 RCE

- 외부 model ZIP upload API
- 업로드 크기, 압축 해제 크기, 파일 수 제한
- path traversal, duplicate path, encrypted entry, symbolic link 차단
- 정확히 하나의 `MLmodel` manifest 요구
- MLflow Logged Model 게시 및 `models:/m-...` URI 반환
- 외부 API-only statsmodels deserialization marker PoC
- UUID 기반 고정 proof API
- proof API를 통한 임의 파일 내용 반출 차단

### Delivery

- GitHub Actions Python test
- GitHub Actions container build와 GHCR publish
- `main`, `latest`, `sha-*`, `v*` tag policy
- Compose와 Kubernetes deployment 환경변수 반영
- GHCR anonymous pull 검증

## 최근 검증 결과

- Python tests: `14 passed`
- Python compileall: passed
- Docker Compose config validation: passed
- Kubernetes/GitHub Actions YAML parse: passed
- 외부 benign upload -> register -> validate: passed
- 외부 malicious marker upload -> deserialize -> fixed proof: passed
- RCE validation status: `succeeded`
- test listener cleanup on ports 5000/8080: verified
- GitHub Actions for commit `0cc5acd`: test/container succeeded
- commit `ba90796`의 CI 결과는 다음 작업 시작 시 다시 확인한다.

## 현재 구현 상태

| Milestone | 상태 | 다음 조건 |
| --- | --- | --- |
| Stage 1A SSRF | 완료 | controlled redirector는 전체 랩에서 배포 |
| Stage 1B RCE | 완료 | Kubernetes에서 SA identity 연결 |
| Stage 2 RBAC | 미구현 | contract 및 negative test 우선 작성 |
| Stage 3 Monitoring | 미구현 | Stage 2 완료 후 시작 |
| Stage 4 Argo CD | 미구현 | Stage 3 credential contract 확정 후 시작 |
| Stage 5 Runtime | 미구현 | 전용 node group 설계 필요 |
| Stage 6 CSI/IAM | 미구현 | AWS threat model과 tag policy 필요 |
| Terraform/EKS | 미구현 | Stage 1~4 로컬 체인 안정화 후 시작 |

## 다음 작업: Stage 2 RBAC Chaining

다음 Codex 작업의 범위는 Stage 2 하나로 제한한다.

### 구현 순서

1. `lab/stages/stage-02-rbac/` 구조 생성
2. namespace와 두 ServiceAccount 정의
3. `modelgate` SA가 사용할 최소 Role/RoleBinding 정의
4. `monitoring-runner`가 특정 Secret 한 개만 읽도록 정의
5. Job 생성 경로 설계
6. 임의 ServiceAccount/image/securityContext를 막는 admission policy 추가
7. NetworkPolicy로 Kubernetes API와 필요한 Stage 2 endpoint만 허용
8. positive attack-path 테스트 작성
9. shortcut negative 테스트 matrix 작성
10. kind에서 반복 가능한 smoke test 작성

### Stage 2 완료 조건

- `modelgate` SA는 Stage 2 Secret을 직접 읽지 못한다.
- 의도된 Job을 생성하여 `monitoring-runner` identity로 Secret을 읽을 수 있다.
- 다른 ServiceAccount, namespace, image, privileged/hostPath workload는 거부된다.
- RoleBinding 생성, token minting, pod exec, node access는 거부된다.
- 성공 및 거부 결과가 자동 테스트로 재현된다.
- `STAGE_CONTRACTS.md`와 실제 권한이 일치한다.

## 아직 결정이 필요한 항목

- Stage 2 admission 구현: Kubernetes ValidatingAdmissionPolicy 또는 Kyverno
- 로컬 Kubernetes 표준: kind cluster 버전
- Stage 2 Job image: 별도 최소 lab-runner 이미지 또는 기존 ModelGate 이미지
- Flag 발급/채점 서비스의 최초 도입 시점
- 전체 lab orchestration을 이 저장소에 유지할지 별도 저장소로 분리할 시점
- Stage 3에서 Prometheus 단독 또는 Prometheus+Grafana 조합 사용 여부

결정 전 기본 방향:

- 외부 admission dependency를 줄이기 위해 우선 ValidatingAdmissionPolicy를 검토한다.
- Job image는 공격 도구가 과도하게 포함되지 않은 최소 전용 이미지를 선호한다.
- Stage 2 개발 Flag는 placeholder를 사용하고 배포 시 무작위 발급 구조로 교체한다.

## 작업 규칙

새 작업은 다음 순서를 따른다.

1. Git status와 최신 commit 확인
2. 세 설계 문서 읽기
3. 현재 milestone 범위를 벗어나는 변경 금지
4. 기존 취약한 MLflow pin을 임의로 업그레이드하지 않음
5. 코드 변경과 테스트를 함께 작성
6. positive/negative 검증을 모두 실행
7. `STATUS.md`의 완료 항목, 검증 결과, 다음 작업 갱신
8. 사용자가 요청하지 않은 commit/push는 수행하지 않음

## 기본 검증 명령

PowerShell:

```powershell
cd C:\Users\yoseb\Desktop\vuln-mlops

.\.venv\Scripts\python.exe -m compileall -q modelgate poc tests
.\.venv\Scripts\python.exe -m pytest -q
docker compose config --quiet
git diff --check
git status --short
```

Docker Desktop이 실행되고 현재 사용자에게 Docker pipe 접근 권한이 있을 때:

```powershell
docker compose build
docker compose up -d
docker compose ps
```

## 새 Codex 작업 시작용 요청 예시

```text
C:\Users\yoseb\Desktop\vuln-mlops를 작업 루트로 사용해.
먼저 docs/LAB_PLAN.md, docs/STAGE_CONTRACTS.md, docs/STATUS.md를 모두 읽고
현재 Git 상태와 최근 테스트 결과를 확인해. 이번 작업에서는 Stage 2 RBAC
Chaining만 구현해. intended path와 shortcut negative tests를 함께 만들고,
Stage 3 이후 구성이나 Terraform은 수정하지 마. 구현 후 테스트를 실행하고
docs/STATUS.md를 갱신해.
```

