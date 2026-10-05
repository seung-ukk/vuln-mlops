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

## 제안된 Stage 5 교체 계약: Runtime Builder → IRSA → S3

이 계약은 아직 현재 EKS에 적용되지 않은 전환안이다. 운영 중인 socket Stage 5
계약은 새 이미지와 공개 참가자 경로가 검증될 때까지 아래 기존 항목대로 유지한다.

- Input: Stage 3의 제한된 Git credential과 Stage 4의 Argo `Synced/Healthy` 증거.
- Intended: Git의 `runtime-builder/` 경로에서 기존 앱의 legacy build profile을
  활성화한다. 참가자는 ModelGate의 proof-bound 고정 gateway를 통해 빌드 요청을
  제출하고, 앱의 source reference가 shell command에 조합되는 결함을 이용한다.
- Output: `stage-05-runtime/runtime-builder-iam` ServiceAccount에 연결된 IRSA 역할.
  이 역할은 실습 S3 버킷의 `proof/final-flag.txt` 한 객체에만 `s3:GetObject`를 갖는다.
- Success: 예상 계정, `assumed-role/...runtime-builder/...` ARN, 공개되지 않은 합성
  Flag의 조회. 실제 credential, 임의 파일 또는 shell stdout은 참가자 API로 반환하지 않는다.
- Denial: Stage 4 이전 빌드 경로, 다른 namespace/ServiceAccount의 역할 사용,
  버킷 전체·다른 객체 조회, hostPath/socket/privileged Deployment 변경을 거부한다.
- Interpretation: 이 경로는 Pod 애플리케이션 문맥의 AWS 접근을 증명하며 노드 장악이나
  CSI 공격을 증명하지 않는다.

## Stage 1A: SSRF

### Input identity

- 허용 목록의 팀원 공인 IP에서 ModelGate 전용 endpoint에 접근 가능한 외부 사용자
- 현재 단기 실습 endpoint는 단일 Terraform 관리 EIP의 HTTP NLB이며, synthetic 데이터만
  전송한다. 도메인 확보 후 공개 인증서를 사용하는 HTTPS로 교체한다.
- Kubernetes credential 없음
- AWS credential 없음

### Intended action

1. 공개 UI에서 API 문서를 발견하고 OpenAPI 명세를 조사한다.
2. `GET /api/system/info`의 synthetic probe 좌표로 Kubernetes service FQDN을 조립한다.
3. ModelGate webhook API로 첫 URL을 등록한다.
4. 첫 URL은 공개 주소 검증을 통과하고 내부 synthetic canary로 redirect한다.
5. MLflow webhook test 결과에서 내부 canary 문자열을 확인한다.

### Success evidence

- `MODELGATE_INTERNAL_SSRF_PROOF`
- webhook ID와 test timestamp

### Shortcut denial

- canary는 ALB 또는 host port에 직접 노출하지 않는다.
- public NLB는 `modelgate-public` Service만 게시하고 참가자 `/32` 외 접근을 거부한다.
- Prometheus, Grafana, credential broker, Gitea, Argo CD, MLflow는 NLB로 게시하지 않는다.
- Stage 1 Pod에서 IMDS, Kubernetes API, monitoring, Argo CD로 직접 연결하지 못한다.
- SSRF 응답에 AWS credential, ServiceAccount token 또는 실제 Secret을 포함하지 않는다.
- system-info는 service, namespace, port, path 이외의 완성 URL, ClusterIP, cloud metadata,
  credential을 반환하지 않는다.
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
6. 같은 proof UUID로 bounded foothold API의 다음 경로를 확인한다.

### Output identity

- `uid=10001`의 validator process execution
- `system:serviceaccount:modelgate-lab:modelgate` 권한으로 SelfSubjectRulesReview와 고정
  Stage 2 Job 작업만 중계하는 proof-bound 실행 문맥

### Success evidence

- validation job `succeeded`
- UUID proof에 대한 `validator marker observed`

### Shortcut denial

- proof API는 marker 파일 내용을 반환하지 않는다.
- foothold API는 Kubernetes token, 임의 URL/API path, namespace, manifest, Pod 이름을
  입력받거나 반환하지 않는다.
- payload는 reverse shell, callback, credential 접근, subprocess 실행을 포함하지 않는다.
- Pod는 non-root, restricted Pod Security, capability drop, read-only root filesystem을 유지한다.
- hostPath, runtime socket, privileged mode, AWS identity를 제공하지 않는다.
- MLflow는 외부 Service 또는 Ingress로 노출하지 않는다.

## Stage 2: ServiceAccount -> RBAC Chaining

### Input identity

- `system:serviceaccount:modelgate-lab:modelgate`
- validator의 Kubernetes API 연결

### Intended action

1. Stage 1 proof 응답의 `foothold_session`과 `next`를 확인한다.
2. proof-bound SelfSubjectRulesReview relay로 effective permission을 조사한다.
3. 직접 Secret 접근은 거부되는 것을 확인한다.
4. body가 없는 fixed Job endpoint로 admission policy가 허용하는
   `monitoring-runner` Job을 실행한다.
5. fixed status endpoint를 polling하고 fixed log endpoint에서 synthetic proof를 얻는다.
6. `monitoring-runner`가 이름이 고정된 Stage 2 Secret을 `get`했음을 확인한다.
7. 완료된 고정 Job은 명시적 lab reset까지 유지되어 Stage 3 세션의 선행 증거가 된다.

### Output identity

- `system:serviceaccount:stage-02-rbac:monitoring-runner`
- Stage 3 monitoring namespace의 Grafana와 credential broker에만 연결되는
  `monitoring-session` relay

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
2. proof-bound datasource endpoint에서 Grafana datasource UID를 확인한다.
3. 고정 query endpoint를 통해 `gitops_debug_info` topology metric을 확인한다.
4. metric에서 Argo CD application, 실습 repository와 opaque credential reference를 식별한다.
5. 발견한 정확한 reference만 broker에 교환해 제한된 Git credential을 획득한다.
6. credential 응답의 proof-bound `git_gateway`와 `application_status` 경로를 다음 단계
   진입점으로 사용한다.

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
- Gitea UI, 관리 API와 임의 repository를 외부에 직접 공개하지 않음
- ModelGate Pod가 Grafana, Prometheus, broker에 직접 연결하지 못하고
  `monitoring-session` TCP 8080만 연결 가능
- monitoring relay는 datasource 목록, 고정 query, 고정 exchange 이외 경로를 404 처리
- Stage 2 Job이 완료되지 않은 proof 세션의 Stage 3 relay 사용 거부
- metrics/labels에 Final Flag 또는 AWS credential 금지

## Stage 4: Argo CD / GitOps Privilege Escalation

### Input identity

- 제한된 Git write credential
- Argo CD application과 sync 정책에 대한 지식
- 완료된 Stage 2 Job에 결합된 proof 세션과 ModelGate 참가자 endpoint

### Intended action

1. proof-bound ModelGate Git gateway에서 고정 repository를 clone한다.
2. 허용된 repository path의 manifest 또는 values를 변경해 같은 gateway로 push한다.
3. Argo CD auto-sync가 변경을 reconcile한다.
4. proof-bound application status API에서 revision, sync/health와 synthetic proof를 확인한다.
5. 기존 `runtime-builder` workload의 허용된 실행 필드를 제어한다.

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
- 임의 upstream URL/path, 다른 Git repository와 Gitea UI/API proxy 금지
- Stage 2가 완료되지 않은 proof 세션, Git Basic 인증 누락, 허용되지 않은 Git service 거부
- Git request body는 8 MiB로 제한하고 upstream cookie/redirect header를 외부로 전달하지 않음

### Implemented permission shape

- repository credential은 synthetic이며 `stage4-lab` branch와 `runtime-builder/` path만
  pre-receive hook으로 허용한다.
- ModelGate gateway는 `vuln-mlops-gitops.git`의 `info/refs`, `git-upload-pack`,
  `git-receive-pack`만 내부 Gitea로 중계하고 Stage 3 Basic credential을 그대로 검증한다.
- ModelGate의 Kubernetes status 권한은 `runtime-builder` Application/Deployment 한 개에
  대한 `get`으로 제한되며 list/watch/mutation 권한은 없다.
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
- `Synced/Healthy` Stage 4 revision과 synthetic proof가 결합된 proof-bound 참가자 세션

### Intended action

1. Stage 4 application status 응답에서 고정 `runtime_relay` 경로를 발견한다.
2. body 없는 proof 요청으로 내부 relay의 단일 CRI 작업을 실행한다.
3. relay가 현재 Pod sandbox에 digest 고정 proof container를 만들고 고정 node proof만
   현재 Pod의 `tmp` emptyDir로 복사한다.
4. 임시 CRI container와 proof 파일이 제거된 뒤 Node 전용 Stage 5 Flag를 응답으로 확인한다.

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
- 참가자의 임의 command, path, image, Pod, sandbox 또는 CRI config 입력 거부
- Stage 4 proof/sync/health/mode가 준비되지 않은 세션의 runtime relay 사용 거부
- ModelGate 이외 Pod의 relay 연결과 relay Service의 외부 노출 거부
- baseline의 relay 직접 호출은 HTTP 409이며 reviewed Stage 4 desired state가 proof annotation과
  mode를 함께 reconcile한 뒤에만 `RELAY_ENABLED=true` 허용

### Implemented permission shape

- `runtime-builder`는 `lab.vuln-mlops/node-role=escape` label과 전용 taint를 가진
  worker에만 배치하며, containerd socket은 이 Pod의 고정 `runtime-relay` container에만
  mount한다.
- Stage 5 namespace는 hostPath 때문에 privileged Pod Security level을 사용하지만,
  ValidatingAdmissionPolicy가 Deployment 이름, image digest, node selector, toleration,
  socket/client path, volume/container shape와 non-privileged security context를 고정한다.
- Argo CD controller는 기존 `runtime-builder`의 `update/patch`만 수행할 수 있고
  workload create/delete, 다른 resourceName 변경, Secret/RBAC 변경은 할 수 없다.
- digest 고정 runtime-client init container가 packaged `crictl`을 `emptyDir` 도구 볼륨으로
  복사하고, ConfigMap의 고정 relay 코드만 이를 실행한다. host binary는 mount하지 않는다.
  runtime socket을 통해 기존 Pod sandbox에 다음 container attempt를 주입하고 node의
  synthetic proof만 해당 Pod의 기존 `tmp` emptyDir로 복사한다.
- proof는 escape kind worker에만 존재하며 manifest, Kubernetes Secret, control-plane,
  AWS identity에는 저장하지 않는다. 참가자에게는 고정 형식 proof 응답만 반환하며 임시
  CRI container와 Pod 내부 proof 파일은 요청 종료 전에 제거한다.
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
