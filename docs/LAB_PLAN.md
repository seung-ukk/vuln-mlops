# vuln-mlops 공격 체인 랩 계획

## 1. 목적

이 프로젝트는 외부에 노출된 취약한 MLOps 애플리케이션에서 시작하여
Kubernetes RBAC, 모니터링, GitOps, Container Runtime, AWS Storage/IAM 경계를
차례로 이동하는 격리형 실습 랩을 구축한다.

초기 진입점인 ModelGate는 의도적으로 취약한 MLflow를 사용한다. 이후
Prometheus, Grafana, Argo CD, Kubernetes 및 AWS 구성요소는 검토 시점의 최신
안정 버전을 사용하고, 알려진 오래된 CVE가 아니라 운영상 잘못된 신뢰관계와
권한 조합을 실습 대상으로 삼는다.

현재 개인 EKS에서 검증된 5-B 경로와 새로 구성 중인 5-A 경로는 Stage 4
이후 두 갈래로 나뉜다.

```text
외부 사용자 → ModelGate SSRF/RCE → RBAC Job → monitoring credential
  → 제한된 Git 변경 → Argo reconciliation
      ├─ 5-A: 독립 runtime-maintenance → containerd → 합성 노드 proof (배포 전)
      └─ 5-B: runtime-builder 명령 주입 → Pod IRSA → 합성 S3 Flag (EKS 검증됨)
```

5-A는 기존 socket relay의 고정 CRI 작업을 독립 에이전트로 재사용한다. 아래 원래
계획의 CSI 경로는 별도 확장안이다. 두 문제 모두 노드 장악이나 CSI pivot을
성공 증거로 주장하지 않는다.

```text
외부 사용자
  -> ModelGate SSRF
  -> ModelGate validator 역직렬화 RCE
  -> modelgate ServiceAccount
  -> RBAC identity chaining
  -> Monitoring trust abuse
  -> Argo CD / GitOps 권한상승
  -> Container Runtime socket
  -> 전용 Worker Node
  -> CSI / EBS / IAM
  -> Final Flag
```

## 2. 설계 원칙

1. 각 Stage는 하나의 새로운 보안 경계를 넘어야 한다.
2. 이전 Stage의 identity만 다음 Stage의 시작점으로 사용할 수 있어야 한다.
3. 취약성은 의도적으로 만들되 불필요한 지름길은 허용하지 않는다.
4. Flag는 공격 성공 증거이지 다음 단계를 우회하는 비밀번호가 아니다.
5. 실제 AWS 데이터, 운영 credential, 고객 artifact를 사용하지 않는다.
6. Kubernetes 및 AWS 권한은 실습 전용 namespace, resource name, tag로 제한한다.
7. Terraform state, Git 저장소, Kubernetes ConfigMap에 최종 Flag 평문을 넣지 않는다.
8. 정상 경로 테스트와 shortcut 거부 테스트를 같은 변경에서 작성한다.
9. 한 Stage의 검증이 실패하면 다음 Stage 구현으로 넘어가지 않는다.
10. 생성, 초기화, 증거 수집, 삭제 절차가 모두 자동화되어야 한다.

## 3. 현재 구현된 Stage 1

현재 Kubernetes Deployment는 하나의 Pod에 다음 세 컨테이너를 배치한다.

- `api`: 외부 ModelGate UI/API
- `mlflow-registry`: loopback에서만 동작하는 MLflow Tracking/Registry
- `validator`: 등록된 모델을 `mlflow.pyfunc.load_model()`로 검사

공유 볼륨:

- `/var/lib/modelgate`: job DB와 고정 형식 RCE proof
- `/artifacts`: 업로드 임시 영역과 MLflow artifact

Stage 1에 구현된 경로:

- 공개 UI의 API 문서 링크와 OpenAPI에 노출된 bounded synthetic system-info를 통한
  cluster-local canary 좌표 discovery
- Webhook redirect를 통한 SSRF synthetic canary 확인
- 외부 `POST /api/artifacts`를 통한 MLflow model ZIP 업로드
- 경로 탈출, symbolic link, 중복 경로, 크기 및 파일 수 제한
- 업로드 artifact를 MLflow Logged Model로 변환
- 외부 API만 사용하는 statsmodels 역직렬화 RCE marker PoC
- marker 존재 여부만 반환하고 파일 내용은 반환하지 않는 proof API
- 관측된 marker UUID로만 열리며 SelfSubjectRulesReview, 고정 Stage 2 Job 생성/상태/로그만
  중계하는 participant foothold API
- GHCR 이미지 CI 게시 및 Kubernetes/Compose 설정

Stage 1의 RCE는 non-root `uid=10001`에서 발생한다. privileged mode, hostPath,
runtime socket, host namespace 및 AWS identity는 제공하지 않는다.

## 4. 목표 Stage

### Stage 1A: SSRF

외부 ModelGate API를 통해 MLflow webhook redirect 검증 결함을 사용하고 내부
canary에 접근한다. 결과는 내부 서비스에 도달했다는 합성 증거만 제공한다.

### Stage 1B: Deserialization RCE

외부에서 model bundle을 업로드하고 validator의 자동 호환성 검사에서 marker-only
payload를 실행한다. 이 단계가 Pod 내부 실행 문맥과 ServiceAccount identity로
이어지는 최초 foothold이다.

### Stage 2: ServiceAccount -> RBAC Chaining

`modelgate` ServiceAccount의 effective permission을 열거한 뒤, 직접 읽을 수 없는
Stage 2 Secret을 지정된 `monitoring-runner` identity를 사용하는 Job을 통해 읽는다.
참가자는 operator kubeconfig나 ServiceAccount token을 받지 않고, Stage 1 proof UUID에
결합된 고정 foothold API로만 이 제한된 권한 조합을 사용한다.
Job 완료 후 같은 proof 세션은 `monitoring-runner` ServiceAccount와 Stage 3 client label을
사용하는 restricted monitoring relay에만 이어진다.
Admission control로 임의 ServiceAccount, 임의 namespace, privileged/hostPath Pod 및
RBAC 객체 생성을 거부한다.

### Stage 3: Monitoring Stack Trust Abuse

최신 Prometheus/Grafana의 Kubernetes discovery 및 datasource 신뢰관계를 이용해
일반 workload에서 볼 수 없는 topology, internal endpoint 및 제한된 Git credential을
찾는다. Monitoring identity 자체에는 Node 또는 AWS 권한을 주지 않는다.
참가자는 operator `kubectl exec` 대신 proof-bound API를 통해 datasource 목록, 고정
`gitops_debug_info` query, 발견한 정확한 credential reference 교환만 수행한다.

### Stage 4: Argo CD / GitOps Privilege Escalation

최신 Argo CD에서 과도한 repository write 범위, AppProject destination/resource 범위,
자동 동기화가 결합된 운영상 오류를 사용한다. 공격자는 새 privileged Pod를 만들지
못하고 기존 `runtime-builder` workload의 허용된 필드만 변경할 수 있어야 한다.
Stage 3에서 발견한 synthetic credential은 ModelGate의 기존 참가자 endpoint 아래 고정
Git smart-HTTP gateway에서만 사용한다. gateway는 단일 repository와 upload/receive-pack
경로만 중계하며 Gitea UI, 관리 API, 임의 repository는 공개하지 않는다. Argo 결과도
proof-bound 고정 status API로 확인하므로 참가자에게 `kubectl` 권한을 요구하지 않는다.

### Stage 5: Container Runtime Socket -> Worker Node

전용 escape node group에 배치된 기존 `runtime-builder` Pod에서 containerd runtime
socket을 발견하고 동일 Node의 runtime resource와 host에 영향을 준다. Runtime socket은
다른 node group과 workload에는 노출하지 않는다.
참가자는 operator `kubectl exec` 대신 Stage 4 proof가 관측된 동일 proof 세션에서 body가
없는 고정 runtime endpoint를 호출한다. ModelGate는 내부 `runtime-relay`의 단일 합성 proof
작업만 호출하며 command, path, image, Pod 또는 CRI config를 입력받지 않는다.

### Stage 6: CSI / AWS Storage / IAM Pivot

Node 또는 CSI operational component의 신뢰관계를 이용해 실습 태그가 지정된
EBS/EFS resource에만 접근하고 Final Flag를 얻는다. 일반 application Pod와 Node IAM은
최종 storage를 직접 읽을 수 없어야 한다.

### 현재 검증된 단순화: Runtime Builder IAM capstone

팀 프로젝트의 범위를 줄이기 위해 현재 개인 EKS에서는 기존 socket 기반
Stage 5와 미구현 Stage 6 대신 `runtime-builder` 앱의 명령 주입과 IRSA 기반
실습 S3 접근을 사용한다. 공개 참가자 경로에서 이 연결을 검증했다. 기존
socket 경로는 저장소에 남은 별도 프로필이다. 현재 경로가 입증하는 것은
Pod 앱 실행 권한에서 AWS IAM 권한으로 이어지는 영향이며, node compromise
또는 CSI pivot을 주장하지 않는다.

Stage 4의 제한된 Git 변경이 Argo를 통해 앱의 legacy build profile을 활성화한다.
참가자는 Git 저장소의 README/Deployment와 공개 ModelGate API에서 빌드 요청 단서를
찾고, 의도된 명령 조합 결함을 통해 앱의 IRSA 역할을 사용한다. 역할은 계정별 실습용
비공개 S3 버킷의 정확한 합성 proof 객체만 읽을 수 있다. Flag는 Terraform state나
Git에 저장하지 않으며 참가자 실습 전 무작위 합성 값으로 교체한다. 공개 응답은
계정, assumed-role ARN, 검증된 합성 Flag만 반환한다.

## 5. 개발 및 배포 환경

### 로컬 개발

- Docker Compose: Stage 1 기능 및 PoC
- kind: Stage 2~5의 Kubernetes, RBAC, NetworkPolicy, Admission, GitOps/runtime 검증
- 로컬에서는 AWS IAM/CSI 동작을 모의하되 실제 권한 성공으로 간주하지 않는다.

### AWS 통합 환경

- 전용 AWS 계정 또는 완전히 격리된 lab account
- 2개 이상의 AZ에 걸친 전용 VPC와 private worker subnet
- 일반 workload와 Stage 5용 escape EKS managed node group 분리
- escape node group의 고정 label/taint와 1-node 상한
- 현재 팀 내부 단기 실습 진입점은 단일 public subnet과 Terraform 관리 EIP를 사용하는
  ModelGate 전용 HTTP NLB이며 팀원 공인 IP `/32`만 허용
- 도메인 확보 후 장기 운영 진입점은 HTTPS ALB/NLB로 교체하고 현재 HTTP 예외를 제거
- EKS API endpoint는 private 또는 제한된 public CIDR 사용
- EKS Access Entry API와 별도 operator role 사용
- VPC CNI NetworkPolicy strict mode와 CNI용 Pod Identity 사용
- EKS Pod Identity 또는 검토된 IRSA 사용
- 태그 기반 IAM resource restriction
- CloudTrail, EKS audit log 및 exercise log 보존

Terraform은 Stage 1~5의 로컬 공격 체인이 안정화된 뒤 작성한다. Kubernetes manifest,
Helm values, Stage contract 테스트를 Terraform 내부 문자열로 만들지 않는다.

## 6. 계획된 저장소 구조

```text
vuln-mlops/
  modelgate/                 # Stage 1 애플리케이션
  poc/                       # 안전한 SSRF/RCE 검증
  deploy/base/               # ModelGate 안전 기준 배포
  deploy/eks-lab/            # EKS용 명시적 overlay
  lab/
    base/                    # 전체 랩 공통 정책
    stages/
      stage-02-rbac/
      stage-03-monitoring/
      stage-04-gitops/
      stage-05-runtime/
      stage-06-storage/
  infra/terraform/           # 공격 체인 확정 후 추가
  tests/
    attack-path/             # 의도된 성공 경로
    shortcuts/               # 우회 경로 거부
    reset/                   # 반복 실행 및 초기화
  docs/
    LAB_PLAN.md
    STAGE_CONTRACTS.md
    STATUS.md
```

필요하면 장기적으로 application과 lab orchestration 저장소를 분리할 수 있다. 분리
전까지는 디렉터리 경계를 유지하고 Terraform, application, Stage manifest를 섞지 않는다.

## 7. Flag 및 채점 원칙

- 개발 중에는 `FLAG{stage_name_placeholder}` 형식을 사용할 수 있다.
- 팀 실습에서는 배포 시 무작위 Flag를 생성한다.
- 채점 서비스에는 원문이 아니라 hash를 저장한다.
- Terraform state와 Git에는 Flag 원문을 저장하지 않는다.
- Kubernetes Secret을 사용하는 Stage는 해당 Stage identity만 특정 resource name으로
  `get`할 수 있게 하고 `list` 권한은 주지 않는다.
- 최종 Flag는 Kubernetes Secret이 아닌 태그가 지정된 lab storage에 둔다.
- reset 시 Flag와 proof를 재발급하고 이전 값은 무효화한다.

## 8. 검증 전략

모든 Stage는 다음 세 종류의 검증을 갖는다.

1. 기능 테스트: 정상 서비스와 배포가 동작하는가.
2. Attack-path 테스트: 의도된 identity 전환으로 Flag를 획득할 수 있는가.
3. Shortcut 테스트: 이전 identity가 후속 Flag, host, runtime, AWS resource에 직접
   접근하지 못하는가.

필수 공통 검사:

- Kubernetes `auth can-i` positive/negative matrix
- Pod Security 또는 admission policy 결과
- NetworkPolicy 허용/거부 matrix
- image tag가 아닌 검토된 digest 사용 여부
- AWS IAM policy simulation 및 CloudTrail evidence
- clean deploy -> attack -> reset -> second attack 반복 가능 여부

## 9. 완료 기준

전체 랩은 다음 조건을 모두 만족해야 완료된 것으로 본다.

- 외부 참가자는 허용된 ModelGate 진입점 외에는 접근할 수 없다. 현재 단기 실습은
  `/32` 제한 HTTP NLB이고, 도메인 확보 후 HTTPS로 전환한다.
- Stage 1부터 Final Flag까지 문서화된 순서로 완료할 수 있다.
- 각 Stage를 건너뛰는 주요 shortcut 테스트가 모두 실패한다.
- 일반 workload compromise가 즉시 cluster-admin 또는 AWS admin으로 이어지지 않는다.
- 최신 운영 구성요소의 버전과 image digest가 기록된다.
- Terraform으로 생성 및 삭제가 반복 가능하다.
- 실습 계정 밖의 AWS resource에 대한 접근이 IAM으로 거부된다.
- 팀원이 operator 도움 없이 실행 가능한 runbook과 증거 수집 절차가 있다.
