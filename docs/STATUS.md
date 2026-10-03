# Project Status

마지막 갱신: 2026-10-04 (Asia/Seoul)

이 문서는 새 Codex 작업과 팀원이 현재 상태를 빠르게 파악하기 위한 인계 문서다.
작업을 시작할 때 `LAB_PLAN.md`, `STAGE_CONTRACTS.md`, 이 문서를 순서대로 읽는다.

## 현재 기준점

- Branch: `codex/stage2-5-checkpoint`
- Latest verified implementation commit: `28bba29 feat(lab): add stage 5 runtime socket chain`
- Repository: `https://github.com/seung-ukk/vuln-mlops`
- Container: `ghcr.io/seung-ukk/vuln-mlops`
- 현재 작업 트리: Stage 2~5 구현을 Stage별 커밋으로 보존했으며 Terraform/EKS는 미구현

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

### Stage 2 RBAC Chaining

- `stage-02-rbac` restricted namespace와 `monitoring-runner` ServiceAccount
- `modelgate` SA의 SelfSubjectRulesReview 및 Stage 2 Job create/get/watch 권한
- Job Pod 조회와 stdout proof 확인에 필요한 pods get/list, pods/log get 권한
- `monitoring-runner`의 `stage-02-flag` 단일 resourceName get 권한
- Kubernetes 1.37.0과 digest 고정 `kubectl` 1.37.0 runner
- ValidatingAdmissionPolicy로 Job 이름, SA, image, command/args, security context 고정
- 임의 image, SA, env/envFrom, Secret/hostPath volume, privileged/host namespace 차단
- Stage 2 default-deny 및 DNS/Kubernetes API 전용 egress
- namespace-scoped Metadata audit policy와 kind audit evidence 검증
- PowerShell/Bash kind smoke test와 intended/shortcut 정적 계약 테스트

### Stage 3 Monitoring Stack Trust Abuse

- Prometheus 3.14.0과 Grafana 13.2.2 digest 고정 배포
- namespace 한정 Kubernetes service discovery RBAC
- Grafana anonymous Viewer datasource proxy를 통한 Prometheus 조회
- metric에는 topology와 opaque credential reference만 노출
- broker에서 repository/branch/path 제한 synthetic Git credential과 Flag 교환
- default-deny 및 `monitoring-runner` client 전용 NetworkPolicy
- Secret/workload/node/exec 권한 및 외부 Service/Ingress shortcut 거부 테스트

### Stage 4 Argo CD / GitOps Privilege Escalation

- Argo CD 3.5.3과 Gitea 1.27.3-rootless digest 고정 배포
- Stage 3 synthetic credential을 단일 lab repository에 연결
- `stage4-lab` branch와 `runtime-builder/` path만 허용하는 pre-receive hook
- AppProject의 repository, destination namespace, Deployment kind 제한
- 기존 `runtime-builder`에 대한 auto-sync와 synthetic Flag annotation
- controller mutation을 `runtime-builder`의 update/patch로 제한
- namespaced dynamic cache용 read-only wildcard와 정확한 필요성 문서화
- ValidatingAdmissionPolicy로 다른 workload, hostPath, privileged/host namespace 거부
- default-deny NetworkPolicy와 namespace 한정 cluster destination
- Git commit SHA, Argo revision, Kubernetes audit evidence 검증

### Stage 5 Runtime Socket -> Escape Worker

- `stage-05-runtime` namespace와 전용 escape worker label/taint 경계
- `runtime-builder` 하나에만 containerd socket과 reviewed `crictl` client 노출
- digest 고정 Debian workload, non-privileged security context, no SA token, default-deny network
- Argo CD mutation을 기존 `runtime-builder`의 update/patch로 제한
- ValidatingAdmissionPolicy로 node, image, socket/client path, volume/container shape 고정
- 기존 CRI sandbox에 다음 `runtime-builder` attempt를 주입하는 intended path
- node에만 존재하는 synthetic proof를 기존 Pod `tmp` emptyDir로 제한 복사
- containerd CRI operation ID와 namespace-scoped Kubernetes exec audit evidence 검증
- 다른 workload/hostPath/node/privileged 변경과 create/delete shortcut 거부

### Delivery

- GitHub Actions Python test
- GitHub Actions container build와 GHCR publish
- `main`, `latest`, `sha-*`, `v*` tag policy
- Compose와 Kubernetes deployment 환경변수 반영
- GHCR anonymous pull 검증

## 최근 검증 결과

- Python tests: `50 passed`
- Python compileall: passed
- Docker Compose config validation: passed
- Stage 2 Kustomize render: passed
- Stage 2 kind acceptance: passed (Kubernetes 1.37.0)
- Stage 2 intended Job -> `monitoring-runner` -> Flag 획득: passed
- Stage 2 direct Secret/RBAC/token/exec/node/other namespace shortcuts: denied
- Stage 2 wrong SA/image/privileged/hostPath/Secret volume/env shortcuts: denied
- Stage 2 Kubernetes audit evidence: verified
- Stage 3 Kustomize render: passed
- Stage 3 kind datasource discovery/credential exchange: passed
- Stage 3 Secret/workload/node/exec shortcuts: denied
- Stage 4 Kustomize render: passed
- Stage 4 kind Git commit -> Argo reconciliation: passed (Kubernetes 1.37.0)
- Stage 4 proof annotation, Git/Argo revision, audit evidence: verified
- Stage 4 다른 branch/path push와 다른 workload patch: denied
- Stage 4 Deployment/Secret/Role create shortcuts: denied
- Stage 5 Kustomize render: passed
- Stage 5 kind Git commit -> Argo reconciliation -> containerd CRI proof: passed (Kubernetes 1.37.0)
- Stage 5 proof는 escape worker에만 존재하고 control-plane에는 없음: verified
- Stage 5 containerd socket은 현재 `runtime-builder` Pod 하나에만 노출: verified
- Stage 5 다른 workload update, create/delete, node/hostPath/privileged shortcuts: denied
- Stage 5 containerd CRI operation과 Kubernetes exec audit evidence: verified
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
| Stage 2 RBAC | 완료 | intended path, shortcut denial, audit evidence 검증됨 |
| Stage 3 Monitoring | 완료 | datasource discovery와 synthetic credential 검증됨 |
| Stage 4 Argo CD | 완료 | 제한된 Git change, reconciliation, shortcut denial 검증됨 |
| Stage 5 Runtime | 완료 | escape worker, CRI proof, shortcut denial, audit 검증됨 |
| Stage 6 CSI/IAM | 미구현 | AWS threat model과 tag policy 필요 |
| Terraform/EKS | 미구현 | Stage 1~5 one-command 배포 기반 구현 필요 |

## 다음 작업: Terraform/EKS Stage 1~5 배포 기반

Stage 1~5 로컬 공격 체인과 shortcut denial은 완료되었다. 다음 작업은 깨끗한 전용
AWS 계정에서 한 번의 명령으로 Stage 1~5 실습 환경을 생성/검증/제거할 수 있도록
Terraform/EKS 기반과 배포 orchestration을 구현하는 것이다. Stage 6 CSI/IAM은 별도
AWS threat model과 tag boundary를 확정한 뒤 추가한다.

### Terraform 시작 전 유지 조건

- Stage 4 repository branch/path, AppProject, admission, RBAC 경계를 넓히지 않는다.
- runtime socket은 `runtime-builder` 이외 Pod와 node에 노출하지 않는다.
- escape node에는 운영 workload, 실제 credential, Final Flag를 배치하지 않는다.
- general/escape node group, namespace, network, AWS tag 경계를 Terraform에도 보존한다.
- Node IAM과 CSI/AWS 권한은 Stage 6 threat model 전에는 추가하지 않는다.

## 아직 결정이 필요한 항목

- Flag 발급/채점 서비스의 최초 도입 시점
- 전체 lab orchestration을 이 저장소에 유지할지 별도 저장소로 분리할 시점
- Stage 1~5 배포 후 자동 acceptance를 단일 스크립트로 묶을 범위
- 로컬에서 mount한 `crictl`을 포함하는 EKS용 runtime-client image의 build/publish 위치

결정 전 기본 방향:

- Stage 2 admission은 외부 dependency 없는 ValidatingAdmissionPolicy로 확정했다.
- 로컬 Stage 2 기준은 kind v0.33.0 / Kubernetes v1.37.0으로 검증했다.
- Stage 2 Job은 digest 고정 공식 `registry.k8s.io/kubectl:v1.37.0`을 사용한다.
- Stage 2 개발 Flag는 placeholder를 사용하고 배포 시 무작위 발급 구조로 교체한다.
- Stage 4는 Argo CD 3.5.3과 Gitea 1.27.3-rootless를 digest로 고정한다.
- Stage 4 read wildcard는 namespaced dynamic cache의 read-only API에만 사용한다.
- Stage 5 로컬 기준은 kind escape worker와 containerd CRI 주입 경로로 확정했다.
- EKS에서는 host binary mount 대신 reviewed `crictl`을 포함한 digest-pinned
  runtime-client image를 사용한다.

## 현재 미완료 사항

- Terraform VPC/EKS, general/escape managed node group, ECR, 배포/삭제 orchestration은
  아직 구현하지 않았다.
- Stage 6 CSI/AWS Storage/IAM pivot과 AWS tag/IAM policy boundary는 아직 설계·구현하지
  않았다.
- Stage 1부터 Stage 5까지를 한 명령으로 배포하고 전체 체인을 연속 실행하는 acceptance
  harness는 없다. 현재 Stage 2~5는 Stage별 kind smoke로 검증한다.
- Stage 3 Kustomization은 Stage 2를 base로 포함하지 않고, Stage 4도 Stage 3을 base로
  포함하지 않는다. Stage 5만 Stage 4 overlay를 직접 포함한다. 따라서 Stage 간 identity와
  credential 전달 계약은 검증됐지만 Stage 2→5 전체 manifest 조합은 아직 배포 단위가 아니다.
- Stage 1 application deployment와 Stage 2~5 overlay를 하나의 clean cluster에서 연결한
  end-to-end smoke는 아직 실행하지 않았다.
- 배포별 무작위 Flag 발급, hash 기반 채점, reset/reissue 서비스는 없다. 현재 proof와
  credential은 local lab용 placeholder/synthetic 값이다.
- EKS용 runtime-client image와 build/publish pipeline은 없다. 로컬 Stage 5는 kind node의
  reviewed `crictl` binary를 read-only mount한다.
- Stage 2~5 체크포인트 브랜치는 아직 GitHub Actions에서 검증하지 않았다. 마지막 검증은
  로컬 test/kind acceptance이며 원격 push와 PR은 아직 수행하지 않았다.

## 알려진 제약과 주의사항

- 현재 로컬 검증에서 해결되지 않은 실패는 없다. Python 50개, Stage 2~5 kind
  acceptance, Compose/Kustomize/compile 검사가 통과했다.
- Stage 5 namespace는 containerd socket hostPath 때문에 Pod Security `privileged` level을
  사용한다. 실제 container는 privileged가 아니지만 runtime socket 자체는 사실상 node
  root에 준하는 권한이므로 공유/운영 cluster에 배포하면 안 된다.
- Stage 5 smoke는 제한된 로컬 메모리에서 proof를 실행하기 전에 일부 Argo/Gitea
  component를 scale-down한다. 이는 AWS 운영 topology가 아니라 acceptance 최적화다.
- Stage 5 smoke의 `crictl`은 명시적 endpoint를 사용하지만 이미지 내부 기본 config가
  없어 경고를 출력한다. 기능 실패는 아니며 EKS runtime-client image에서는 config를
  패키징해야 한다.
- kind v0.33.0/Kubernetes v1.37.0 기준으로 검증했다. Terraform에서는 실제 EKS 지원
  version을 선택하고 ValidatingAdmissionPolicy/CEL 동작을 다시 acceptance해야 한다.
- Stage 3 broker, Git credential, 모든 Flag는 합성 값이다. 실제 AWS credential이나
  production resource로 교체하지 않는다.
- Stage 4 vendor CRD/install manifest가 저장소에 포함되어 변경량이 크다. checkpoint
  검토 시 upstream version과 digest를 별도로 확인한다.
- Stage 2~5는 `codex/stage2-5-checkpoint` 브랜치의 분리된 커밋으로 보존했다. 원격에
  push하기 전에는 이 로컬 브랜치를 삭제하거나 강제로 재설정하지 않는다.

## Stage 2~5 checkpoint 보존 기록

하나의 거대한 snapshot 대신 현재 동작 상태를 아래 순서의 검토 가능한 commit으로
분리해 `codex/stage2-5-checkpoint` 브랜치에 보존했다.

1. `9f1181f feat(lab): add stage 2 RBAC chaining`
   - Stage 2 manifest, attack/shortcut tests, PowerShell/Bash smoke
   - 공통 YAML test helper와 `requirements/dev.txt`의 PyYAML dependency
2. `a396432 feat(lab): add stage 3 monitoring trust chain`
   - Stage 3 manifest, attack/shortcut tests, PowerShell smoke
3. `a604a1a feat(lab): add stage 4 GitOps chain`
   - Stage 4 manifest, scope hook, reviewed Argo CD vendor files, tests/smoke
4. `28bba29 feat(lab): add stage 5 runtime socket chain`
   - Stage 5 manifest, CRI proof path, tests/smoke
5. `docs: checkpoint completed stages 2 through 5`
   - `LAB_PLAN.md`, `STAGE_CONTRACTS.md`, `STATUS.md`

각 Stage commit 전 대상 파일만 stage하고 `git diff --cached --check`, 해당 Stage 정적
테스트와 Kustomize 렌더링을 실행했다. 문서 checkpoint 후 전체 Python/compile/Compose/
Kustomize 검사를 다시 실행한다. 원격 push, PR, tag는 별도 사용자 요청 전에는 수행하지
않는다.

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
