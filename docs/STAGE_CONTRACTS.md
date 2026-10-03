# Stage Contracts

이 문서는 각 Stage의 시작 identity, 허용된 공격 경로, 성공 증거 및 반드시 거부해야
하는 지름길을 정의한다. 구현이 문서와 다르면 코드를 확장하기 전에 이 문서를 먼저
검토하고 결정 내용을 기록한다.

## 공통 규칙

- `Input identity`: 참가자가 Stage 시작 시 보유한 유일한 신뢰 identity
- `Intended action`: 랩이 의도적으로 허용하는 공격 행동
- `Output identity`: 다음 Stage에서 사용할 수 있는 새 identity 또는 control plane
- `Success evidence`: Stage 완료를 증명하는 Flag 또는 고정 proof
- `Shortcut denial`: 자동 테스트로 반드시 거부되어야 하는 행동
- Stage가 완료되기 전에는 다음 Stage의 credential, Flag, host mount가 보이면 안 된다.

## 요약

| Stage | Input | Intended boundary crossing | Output | 상태 |
| --- | --- | --- | --- | --- |
| 1A SSRF | 외부 HTTP | Public API -> internal service | 내부 canary 증거 | 구현됨 |
| 1B RCE | 외부 HTTP + model bundle | Model data -> validator process | non-root Pod 실행 | 구현됨 |
| 2 RBAC | `modelgate` SA | Identity -> workload -> higher SA | `monitoring-runner` | 구현됨 |
| 3 Monitoring | monitoring identity | topology/datasource trust | 제한된 Git credential | 구현됨 |
| 4 GitOps | Git credential | Git change -> Argo reconciliation | `runtime-builder` 제어 | 구현됨 |
| 5 Runtime | runtime workload | container -> runtime -> node | escape worker node | 구현됨 |
| 6 CSI/IAM | node/CSI trust | Kubernetes -> AWS storage | Final Flag | 계획 |

## Stage 1A: SSRF

### Input identity

- 팀원 IP에서 ModelGate HTTPS endpoint에 접근 가능한 외부 사용자
- Kubernetes credential 없음
- AWS credential 없음

### Intended action

1. ModelGate webhook API로 첫 URL을 등록한다.
2. 첫 URL은 공개 주소 검증을 통과하고 내부 synthetic canary로 redirect한다.
3. MLflow webhook test 결과에서 내부 canary 문자열을 확인한다.

### Success evidence

- `MODELGATE_INTERNAL_SSRF_PROOF`
- webhook ID와 test timestamp

### Shortcut denial

- canary는 ALB 또는 host port에 직접 노출하지 않는다.
- Stage 1 Pod에서 IMDS, Kubernetes API, monitoring, Argo CD로 직접 연결하지 못한다.
- SSRF 응답에 AWS credential, ServiceAccount token 또는 실제 Secret을 포함하지 않는다.
- 외부 redirector는 팀이 통제하며 open redirect 서비스에 의존하지 않는다.

## Stage 1B: Deserialization RCE

### Input identity

- ModelGate 외부 API 접근 권한
- MLflow UI/API 직접 접근 권한 없음

### Intended action

1. marker-only statsmodels model bundle을 생성한다.
2. `POST /api/artifacts`로 업로드한다.
3. 반환된 `models:/m-...` URI로 model version을 등록한다.
4. validator가 모델을 자동 로드하면서 고정 marker를 생성한다.
5. UUID 기반 proof API로 실행 여부를 확인한다.

### Output identity

- `uid=10001`의 validator process execution
- 다음 Stage에서 `system:serviceaccount:modelgate-lab:modelgate` identity를 사용할 수
  있는 실행 문맥

### Success evidence

- validation job `succeeded`
- UUID proof에 대한 `validator marker observed`

### Shortcut denial

- proof API는 marker 파일 내용을 반환하지 않는다.
- payload는 reverse shell, callback, credential 접근, subprocess 실행을 포함하지 않는다.
- Pod는 non-root, restricted Pod Security, capability drop, read-only root filesystem을 유지한다.
- hostPath, runtime socket, privileged mode, AWS identity를 제공하지 않는다.
- MLflow는 외부 Service 또는 Ingress로 노출하지 않는다.

## Stage 2: ServiceAccount -> RBAC Chaining

### Input identity

- `system:serviceaccount:modelgate-lab:modelgate`
- validator의 Kubernetes API 연결

### Intended action

1. 현재 ServiceAccount와 namespace를 확인한다.
2. SelfSubjectRulesReview 또는 허용된 API discovery로 effective permission을 조사한다.
3. 직접 Secret 접근은 거부되는 것을 확인한다.
4. 지정된 namespace에 Job을 생성할 수 있는 권한 조합을 발견한다.
5. admission policy가 허용하는 `monitoring-runner` ServiceAccount로 Job을 실행한다.
6. `monitoring-runner`가 이름이 고정된 Stage 2 Secret을 `get`한다.

### Output identity

- `system:serviceaccount:stage-02-rbac:monitoring-runner`
- Stage 3 monitoring namespace에 대한 제한된 접근

### Success evidence

- Stage 2 전용 Secret의 Flag
- 생성한 Job 이름, ServiceAccount, Kubernetes audit event

### Required permission shape

- `modelgate` SA:
  - 필요한 discovery 및 제한된 RBAC 조회
  - 지정 namespace의 `jobs` create/get/watch
  - Secret get/list 없음
  - roles/rolebindings create/update/patch 없음
- `monitoring-runner` SA:
  - Stage 2 Flag Secret 한 개에 `resourceNames` 기반 `get`
  - Stage 3 진입에 필요한 최소 네트워크 및 discovery 권한

### Shortcut denial

- `modelgate` SA의 Stage 2 Flag 직접 조회 거부
- 임의 ServiceAccount를 사용하는 Pod/Job 생성 거부
- 임의 image, privileged, hostPath, hostNetwork, hostPID, hostIPC 거부
- Role, RoleBinding, ClusterRole, ClusterRoleBinding 생성/수정 거부
- ServiceAccount token Secret 생성 및 `serviceaccounts/token` 남용 거부
- 다른 namespace의 workload 생성 거부
- node, nodes/proxy, pods/exec, pods/attach 접근 거부
- AWS IMDS 및 Stage 3/4 endpoint 직접 접근 거부

### Acceptance tests

- positive: 지정된 Job과 `monitoring-runner` identity로 Flag 획득
- negative: `modelgate` SA로 Secret get
- negative: 다른 ServiceAccount를 지정한 Job
- negative: privileged/hostPath Job
- negative: RoleBinding 생성
- negative: default, kube-system, argocd namespace 접근

## Stage 3: Monitoring Stack Trust Abuse

### Input identity

- `monitoring-runner` identity
- monitoring namespace 내부 연결

### Intended action

1. 최신 Prometheus/Grafana 구성과 Kubernetes service discovery를 조사한다.
2. target, label, annotation, datasource에서 내부 topology를 확인한다.
3. Argo CD endpoint 및 실습 repository를 식별한다.
4. monitoring component에 과도하게 집중된 제한된 Git credential을 획득한다.

### Output identity

- 실습 repository의 특정 path/branch만 변경 가능한 Git credential
- Argo CD application 이름과 허용된 destination 정보

### Success evidence

- Stage 3 Flag
- 발견한 internal endpoint와 repository path

### Shortcut denial

- monitoring identity에 Secret 전체 list 권한 금지
- cluster-admin, node/proxy, workload create 권한 금지
- AWS IAM, runtime socket, hostPath 금지
- Git credential은 실습 repository 밖에 쓰기 불가
- 외부 사용자가 Prometheus/Grafana에 직접 접근 불가
- metrics/labels에 Final Flag 또는 AWS credential 금지

## Stage 4: Argo CD / GitOps Privilege Escalation

### Input identity

- 제한된 Git write credential
- Argo CD application과 sync 정책에 대한 지식

### Intended action

1. 허용된 repository path의 manifest 또는 values를 변경한다.
2. Argo CD auto-sync가 변경을 reconcile한다.
3. 기존 `runtime-builder` workload의 허용된 실행 필드를 제어한다.

### Output identity

- 기존 `runtime-builder`의 허용된 실행 필드 제어
- Stage 5에서 runtime socket 경계를 추가할 수 있는 workload control plane

### Success evidence

- Stage 4 Flag
- Git commit SHA, Argo sync revision, Kubernetes audit event

### Shortcut denial

- Argo CD를 통한 Namespace, RBAC, Secret, ServiceAccount 생성/수정 거부
- 새 privileged/hostPath workload 생성 거부
- 기존 runtime-builder 이외 workload 변경 거부
- 다른 Argo Project, repository, cluster destination 접근 거부
- Argo CD admin token 및 cluster-admin 사용 금지

### Implemented permission shape

- repository credential은 synthetic이며 `stage4-lab` branch와 `runtime-builder/` path만
  pre-receive hook으로 허용한다.
- AppProject는 단일 repository, 단일 namespace, `apps/Deployment`만 허용한다.
- Argo CD controller의 mutation은 이름이 `runtime-builder`인 Deployment의
  `update/patch`로 제한한다.
- controller의 namespaced dynamic cache에는 API discovery와 desired/live diff를 위해
  resource wildcard `get/list/watch`가 필요하다. destination cluster Secret은
  `stage-04-gitops` namespace만 허용하며 wildcard rule에는 mutation verb가 없다.
- Stage 4에는 runtime socket, hostPath, privileged workload를 추가하지 않는다.

## Stage 5: Runtime Socket -> Worker Node

### Input identity

- 전용 escape node의 `runtime-builder` container
- 해당 Pod에만 mount된 containerd socket

### Intended action

1. runtime socket과 runtime namespace를 발견한다.
2. 동일 Node의 runtime resource를 조사한다.
3. runtime control을 통해 host에 제한된 영향을 준다.
4. Node 전용 Stage 5 Flag를 확인한다.

### Output identity

- 전용 escape worker node의 host-level control
- Stage 6 CSI 경로를 조사할 수 있는 위치

### Success evidence

- Node filesystem에 배치된 Stage 5 Flag
- 해당 Node와 runtime operation의 audit evidence

### Shortcut denial

- runtime socket은 다른 Pod와 node group에 존재하지 않음
- escape node에는 운영 workload와 실제 credential이 없음
- Node IAM으로 Final Flag storage 직접 접근 거부
- control-plane node 접근 불가
- 다른 worker node로 lateral movement 거부

### Implemented permission shape

- `runtime-builder`는 `lab.vuln-mlops/node-role=escape` label과 전용 taint를 가진
  worker에만 배치하며, containerd socket은 이 Pod 하나에만 mount한다.
- Stage 5 namespace는 hostPath 때문에 privileged Pod Security level을 사용하지만,
  ValidatingAdmissionPolicy가 Deployment 이름, image digest, node selector, toleration,
  socket/client path, volume/container shape와 non-privileged security context를 고정한다.
- Argo CD controller는 기존 `runtime-builder`의 `update/patch`만 수행할 수 있고
  workload create/delete, 다른 resourceName 변경, Secret/RBAC 변경은 할 수 없다.
- 로컬 acceptance에서는 node의 reviewed `crictl` binary를 read-only로 mount한다.
  runtime socket을 통해 기존 Pod sandbox에 다음 container attempt를 주입하고,
  node의 synthetic proof만 해당 Pod의 기존 `tmp` emptyDir로 복사한다.
- proof는 escape kind worker에만 존재하며 manifest, Kubernetes Secret, control-plane,
  AWS identity에는 저장하지 않는다. 성공 증거는 containerd CRI operation log와
  namespace-scoped Kubernetes exec audit event로 확인한다.
- Node IAM, CSI, AWS resource와 Final Flag는 Stage 5에 포함하지 않는다.

## Stage 6: CSI / AWS Storage / IAM Pivot

### Input identity

- escape worker node control 또는 CSI component trust relationship
- Stage 6용 Kubernetes resource 정보

### Intended action

1. CSI component의 Kubernetes 권한과 AWS identity 연결을 조사한다.
2. 실습 태그가 지정된 EBS/EFS resource만 식별한다.
3. 허용된 attach/mount/read 동작으로 Final Flag를 확인한다.

### Output identity

- 별도의 후속 identity 없음. 공격 체인의 최종 단계이다.

### Success evidence

- 태그가 지정된 lab storage의 Final Flag
- CloudTrail event와 Kubernetes/CSI log correlation

### Shortcut denial

- 일반 Pod, `modelgate` SA, monitoring SA, Argo CD SA의 AWS API 접근 거부
- Node instance profile의 Final Flag volume attach/read 거부
- CSI identity가 태그 없는 EBS/EFS, snapshot, KMS key에 접근하지 못함
- 다른 region/account의 resource 접근 거부
- IAM role 생성, PassRole, policy 수정 권한 금지
- Final Flag를 Kubernetes Secret, SSM Parameter 또는 Terraform output으로 복제하지 않음

## Contract 변경 절차

1. 변경 이유와 위협 모델 영향을 PR 또는 `STATUS.md`에 기록한다.
2. intended path와 shortcut test를 함께 수정한다.
3. 더 높은 권한을 추가할 때 해당 권한이 필요한 정확한 API call을 기록한다.
4. `*` resource 또는 verb를 사용하면 더 좁힐 수 없는 이유를 문서화한다.
5. Contract 검증 후 다음 Stage 상태를 갱신한다.
