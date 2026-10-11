# Project Status

마지막 갱신: 2026-10-11 (Asia/Seoul)

이 문서는 새 Codex 작업과 팀원이 현재 상태를 빠르게 파악하기 위한 인계 문서다.
작업을 시작할 때 `LAB_PLAN.md`, `STAGE_CONTRACTS.md`, 이 문서를 순서대로 읽는다.

## 2026-10-11 참가자·운영자 IP 추가

- 사용자가 개인 Terraform 변수의 운영자·참가자 목록에 `222.235.10.156/32`를 추가했다. 공유한 Terraform 계획은 공격자 EC2의 TCP 22 규칙 1개 생성, EKS 공개 API CIDR 제자리 변경 1개, 삭제 0개였고 적용 결과도 1개 추가·1개 변경·0개 삭제였다.
- 공개 `modelgate-public` Service의 `loadBalancerSourceRanges`와 동명 NetworkPolicy ingress에서 같은 CIDR을 확인했다. NetworkPolicy에 중복된 항목 1개를 제거한 뒤 목록에는 1개만 남았다. 새 IP에서의 실제 HTTP·SSH·EKS 접속 시험 결과는 아직 공유되지 않았다.
- 실제 IP 목록이 있는 `infra/terraform/personal.auto.tfvars`는 Git에서 무시되는 개인 계정 입력 파일이다. 저장소의 Terraform 코드와 문서는 이 입력을 사용하는 구조를 유지한다.

## 2026-10-09 현재 접속 IP `182.220.186.98` 추가

- WSL의 실제 공인 IP가 `182.220.186.98`임을 확인하고 개인 Terraform 변수의 운영자 `public_access_cidrs`와 참가자 `participant_access_cidrs`에 `182.220.186.98/32`를 추가했다. 대상 계획은 전용 공격자 EC2의 TCP 22 인바운드 규칙 1개 생성과 EKS 공개 API CIDR의 제자리 변경 1개뿐이었고 그대로 적용했다. AWS는 EKS 허용 CIDR과 EC2 보안 그룹 규칙 `sgr-0129ad0368ef148c9`를 반환했다.
- `modelgate-lab/modelgate-public` Service의 `loadBalancerSourceRanges`와 같은 이름의 NetworkPolicy ingress에도 새 `/32`를 추가했다. 현재 WSL에서 EKS 조회, 공개 `http://3.35.2.114/readyz`의 `ready`, 전용 EC2 `3.35.13.221`의 SSH hostname 조회를 확인했다. ModelGate Deployment는 1/1 Ready였다.
- 대상 Terraform 적용 후 `modelgate_participant_access_cidrs` 출력이 이전 목록으로 남아 있어, 원격 리소스를 바꾸지 않는 refresh-only 계획·적용으로 출력 상태를 갱신했다. 새 `/32`가 출력에 포함돼 다음 공개 Service 재배포에서도 유지된다. Terraform `validate`, `git diff --check`가 통과했다. 참가자용 새 AWS IAM 신원이나 EKS Access Entry는 추가하지 않았다.

## 2026-10-09 전용 리스너 EC2의 TCP 포트 자유화

- Terraform이 관리하는 공격자 EC2 보안 그룹 `sg-0adf4e68c6f29dd82`의 기존 단일 4444 인바운드 규칙을 TCP 1–65535로 변경했다. 소스는 일반 워커 보안 그룹 `sg-044856f789e3ec830`으로 유지했다. 대상 계획은 0 추가·1 제자리 변경·0 삭제였으며 해당 규칙만 적용했다. AWS `DescribeSecurityGroupRules`에서 실제 포트 범위와 소스 보안 그룹을 확인했다.
- `modelgate-lab/validator-attacker-receiver` NetworkPolicy는 전용 EC2 사설 IP `10.42.143.106/32`에 대한 TCP 모든 포트 송신으로 변경했다. 배포 준비 스크립트도 이 정책을 재적용하도록 수정했고, 기존 리스너 포트 인자는 호출 호환성을 위해 남겼다. Kubernetes API에서 적용된 정책을 확인했다.
- Terraform `fmt -check`·`validate`, setup Bash 구문 검사, NetworkPolicy 서버 측 사전 검증, `git diff --check`가 통과했다. 실제 validator Pod에서 EC2의 TCP 5555 임시 리스너로 접속했고 EC2가 `port-test`를 수신했다. 팀원 SSH 허용 IP, 공개 ModelGate 접근 목록, 다른 Pod/노드의 네트워크 정책은 변경하지 않았다.

## 2026-10-09 현재 접속 IP 추가

- 현재 접속 IP `121.167.58.146/32`를 개인 Terraform 변수의 운영자 `public_access_cidrs`와 참가자 `participant_access_cidrs`에 추가했다. 대상 계획은 EKS 공개 API CIDR 1개 추가와 공격자 EC2 SSH 규칙 1개 추가만 포함했다. EKS 변경은 적용됐고 AWS EKS는 이 CIDR을 반환한다. SSH 규칙은 이미 AWS 보안 그룹 `sg-0adf4e68c6f29dd82`에 수동 생성돼 있어 중복 생성 오류가 났다. 기존 규칙 `sgr-0dd0b5789a156a59c`를 Terraform 상태에 import하고, 설명·태그만 기준값으로 맞췄다.
- `modelgate-lab/modelgate-public` Service의 `loadBalancerSourceRanges`와 동명 NetworkPolicy의 ingress `ipBlock`에도 같은 `/32`를 추가했다. 현재 WSL에서 `kubectl` 조회, 공개 `http://3.35.2.114/readyz`의 `ready` 응답, 기존 PEM으로 실습용 EC2 `3.35.13.221`의 SSH hostname 조회가 모두 성공했다. Terraform `validate`도 통과했다. 전체 Terraform 변경은 적용하지 않았고 이 접속 경로에 필요한 대상만 반영했다.

## 2026-10-08 참가자 경로 실측 (현재 상태 우선)

### 참가자 PoC 후 기준 상태 복원 (2026-10-08)

- EKS 공개 API 접근 CIDR을 `distinct(concat(var.public_access_cidrs, var.participant_access_cidrs))`로 바꿨다. Terraform 전체 계획은 add-on/OIDC 갱신을 포함한 6개 변경이어서 적용하지 않았고, EKS 클러스터만 대상으로 한 계획(0 추가, 1 제자리 변경, 0 삭제)을 적용했다. AWS `DescribeCluster`에서 상태 `ACTIVE`, 허용 `/32` 20개, 요청된 참가자 IP 14개 모두 포함됨을 확인했다. 이 변경은 네트워크 연결만 허용한다. 참가자 IAM 신원과 EKS access entry가 없어 `kubectl`/자율 reset 권한은 아직 없다. 개인 계정은 AWS Organizations 미사용, 서울 리전 IAM Identity Center 인스턴스 없음으로 확인했다. Identity Center access portal 기반 계정 권한을 쓰려면 조직 인스턴스 및 팀원 신원 구성이 선행되어야 한다.
- 실습용 공격자 EC2의 SSH 접근 목록을 재확인했다. 요청한 14개 공인 IP는 모두 `infra/terraform/personal.auto.tfvars`의 `participant_access_cidrs`에 이미 `/32`로 있으며, AWS 보안 그룹 `sg-0adf4e68c6f29dd82`의 TCP 22 인바운드에도 모두 존재한다. 이 그룹은 실행 중인 공격자 EC2 `i-030d4a51c1ac858ad`에 연결돼 있다. 기존 허용 IP까지 SSH 규칙은 총 20개이며, 당시에는 Terraform이나 AWS 규칙을 변경하지 않았다. 이후 EKS 공개 API에는 운영자 CIDR과 이 참가자 CIDR의 합집합을 적용했다.
- 다음 참가자 회차용 운영자 스크립트 `deploy/participant-chain/reset-after-participant.sh`를 저장했다. `setup.sh`로 먼저 안전한 기준 Deployment를 복원한 뒤, `emptyDir` Gitea를 재생성해 이전 Git 이력을 비우고 실습 Git credential을 교체한다. ModelGate·operations-log 재시작과 전용 escape 노드 교체, Argo·Pod·EC2 태그·공개 readiness 검사를 수행하도록 구성했다. **스크립트 전체의 실제 EKS 실행은 아직 하지 않았다.** Git Bash `bash -n`과 파일 공백 검사만 통과했으며 현재 라이브 복원 상태는 아래 실측 기록을 따른다.
- `deploy/participant-chain/setup.sh`를 다시 실행해 Gitea `lab-runtime`의 기준 Deployment를 새 commit `0ee4a1ecbbd9da5f803ba37d8b85434682780457`로 복원했다. live `runtime-lab/runtime-builder`의 Pod UID/GID는 10001이고 `/host-maintenance`, `/node-evidence` mount는 모두 읽기 전용이다. Argo `delivery-lab/runtime-builder`는 같은 revision에서 `Synced/Healthy`다.
- 공격에 사용한 escape 노드 `i-0d0acd7e27a2b2a8c`를 drain하고 Auto Scaling Group에서 종료 요청했다. 대체 노드 `ip-10-42-23-57.ap-northeast-2.compute.internal` (`i-0efa1cb0fb408ecd7`)은 Ready이고 기준 runtime-builder Pod는 그 노드에서 1/1 Running이다. 노드 목록에는 새 escape 노드만 남았으며 새 EC2의 `lab.vuln-mlops/proof` 태그 조회는 빈 목록 `[]`였다. 새 노드의 호스트 기본 task와 evidence 파일 부재는 별도 조회하지 않았다.
- ModelGate Deployment를 재시작해 기존 validator reverse shell 세션을 종료했고 공개 `/readyz`는 `ready`를 반환했다. Git 이력에는 참가자 공격 commit이 남고 기존 배포별 Git credential은 재사용되므로, 이 복원은 완전한 독립 참가자별 자격증명·이력 초기화가 아니다. 다음 참가자에게는 기준 revision과 새 노드를 사용하되 필요하면 credential 교체와 Git 이력 정리를 별도로 수행한다.

### 참가자 셸 재검증 완료 (2026-10-08)

- 공개 ModelGate의 MLflow 모델 업로드·등록에서 직접 구성한 statsmodels 역직렬화 payload로 공격자 EC2(`10.42.143.106:4444`)에 validator UID 10001 reverse shell을 얻었다. 정상 모델 검증과 실패 모델의 `ModuleNotFoundError`도 별도로 관찰했다. statsmodels flavor 선택은 공개 응답에서 유추한 결론이 아니라 참가자에게 제공된 취약점 전제를 바탕으로 한 가설이다. 셸의 운영 메모 → Grafana datasource UID 및 `delivery_sync_info` → `operations-log` Pod 조회·로그 → 배포별 제한 Git token → 내부 Gitea clone을 참가자 신원으로 진행했다. 운영자 조회 결과를 참가자 풀이의 단서로 사용하지 않았다.
- Gitea baseline `a0cb6c8e556c7c6a9da328d12701db9e55f28bc0`에서 참가자가 `runtime-builder/deployment.yaml`의 UID/GID 0, maintenance mount 쓰기 허용, 고정 host task 작성·정상 HTTP 프로세스 시작을 직접 구성했다. 참가자 셸에서 commit `fcc44540580cef326ca25fd9cd199cc29354b4ab`을 `lab-runtime`에 push했고 Argo `delivery-lab/runtime-builder`는 같은 revision에서 `Synced/Healthy`, 새 Pod는 전용 escape 노드 `ip-10-42-30-220.ap-northeast-2.compute.internal`에서 1/1 Running이었다. 참가자 권한의 Pod 로그는 호스트 `root`/UID 0, 해당 노드 hostname, `vuln-mlops-escape-node` assumed-role ARN 및 `tagged i-0d0acd7e27a2b2a8c`를 보였다. 별도 운영자 검증에서 EC2 `lab.vuln-mlops/proof=lab-20261008b`와 동일 노드 역할의 CloudTrail `CreateTags` 이벤트(`2026-10-08T06:50:27Z`, `errorCode=null`)를 확인했다. Pod 로그만으로는 독립 증명이 아니며 EC2 태그·CloudTrail 대조로 최종 AWS 작업을 확인했다.
- 이 참가자 검증 당시에는 공격 후 상태였으나 현재 복원 상태는 바로 위 절을 따른다. 이번 회차에서 reverse shell의 `ncat` 중계는 여러 줄 붙여넣기와 Ctrl+D 처리가 불안정해 한 줄 명령으로 진행했다. 완전한 블라인드 MLflow 취약점 발견성이나 대화형 노드 셸 획득은 검증하지 않았다.

### 참가자 단서 보완 진행 (2026-10-08)

- 폐기된 `stage-04-gitops/runtime-builder` Application은 삭제됐고 `stage-05-runtime/runtime-builder` Deployment는 0 replica로 줄였다. 이전 escape 노드 `i-02ca356d1262414eb`는 사용자 요청으로 이미 종료되어 drain·ASG terminate 재시도 시 대상이 없었다. ASG 활동과 EC2 상태로 종료를 확인했고 새 escape 노드 `ip-10-42-30-220.ap-northeast-2.compute.internal` (`i-0d0acd7e27a2b2a8c`)은 Ready, desired capacity 1의 InService/Healthy다. 새 노드의 proof 태그는 없고, 현재 baseline runtime-builder 및 Falco escape/CloudWatch Pod가 새 노드에서 1/1 Running이다. baseline Pod UID 10001에서 `/host-maintenance/task.sh`와 `/node-evidence` 읽기는 Permission denied였으며, 호스트 파일 내용 자체는 이 회차에서 별도 조회하지 않았다.

- 운영자 수동 sync 재시도 뒤 Gitea baseline `a0cb6c8e556c7c6a9da328d12701db9e55f28bc0`가 현재 `delivery-lab/runtime-builder` Argo Application에서 `Synced/Healthy`가 됐다. live `runtime-lab/runtime-builder`는 UID/GID 10001, `MAINTENANCE_PROFILE=hostpath`, maintenance/evidence mount 모두 readOnly이며 Pod 1/1 Ready다. 아직 같은 escape 노드 `i-02ca356d1262414eb`에서 실행 중이므로 노드 교체는 남았다. 그 노드에는 폐기된 `stage-05-runtime/runtime-builder` Pod와 `stage-04-gitops/runtime-builder` Argo Application도 실행 중임을 확인했다. 다음 참가자 검증 전 옛 프로필을 중지하고 공격 노드를 교체해야 한다.

- 재실행한 준비 스크립트가 Gitea baseline `a0cb6c8e556c7c6a9da328d12701db9e55f28bc0`를 push했으나 Argo는 `OutOfSync/Healthy`와 SyncError를 보였다. 새 admission 정책의 고정 환경변수 규칙이 이전 live Deployment의 `STAGE5_MODE`와 새 `MAINTENANCE_PROFILE` 전환에서 거부했다. 준비 스크립트에 기존 `STAGE5_MODE`가 있을 때만 제거하는 1회성 마이그레이션을 추가했다. 스크립트 문법과 `git diff --check`는 통과했으며, 현재 실행 중인 구버전 스크립트에는 수정이 반영되지 않으므로 운영자 명령으로 live 환경변수를 제거하고 Argo 재동기화를 확인해야 한다.

- 다음 참가자용 `deploy/participant-chain/setup.sh` 재실행에서 Argo가 소유한 `runtime-builder` Deployment의 command, maintenance mount readOnly, UID/GID 필드를 운영자 `kubectl apply --server-side -k`가 다시 소유하려 해 충돌했다. 이 실행은 Gitea baseline commit 이전에 종료됐으므로 현재 공격 revision은 유지된다. 준비 스크립트는 runtime 보조 리소스를 개별 적용하고 Deployment가 없을 때에만 최초 base를 생성하도록 수정했다. `bash -n`과 `git diff --check`는 통과했으며, 수정본의 실제 재실행은 아직 필요하다.

- Terraform 공격자 수신 EC2 보안 그룹은 이전에 `-var='enable_attacker_receiver_security_group=true'`로 적용됐으나 로컬 auto tfvars에 opt-in이 없어 일반 계획에서 23개 삭제가 보였다. `infra/terraform/personal.auto.tfvars`에 이 opt-in을 명시한 뒤 전체 `terraform plan`을 다시 실행하자 **No changes**였다. `terraform validate`도 통과했다. 실제 보안 그룹 `sg-0adf4e68c6f29dd82`는 공격자 EC2 `i-030d4a51c1ac858ad`에 붙어 있고, 현재 운영자 IP `115.91.25.180/32`의 SSH 22와 general-node SG `sg-044856f789e3ec830`에서 listener 4444로의 접근 규칙을 확인했다. 이 계획에는 적용할 변경이 없으므로 `terraform apply`를 실행하지 않았다.

- 작업 장소 변경으로 운영자 WSL 공인 IP가 `115.91.25.180`이 됐다. 이 IP는 참가자 CIDR에는 있었지만 EKS API의 `public_access_cidrs`에는 없어 `kubectl`이 시간 초과됐다. 로컬 `infra/terraform/personal.auto.tfvars`의 운영자 목록에 `115.91.25.180/32`를 추가하고 EKS 클러스터만 대상으로 한 Terraform 계획(0 추가, 1 제자리 변경, 0 삭제)을 적용했다. AWS `DescribeCluster`에서 CIDR 추가를 확인했고, 같은 WSL의 `kubectl`로 `delivery-lab/runtime-builder` Application이 `Synced/Healthy`임을 확인했다. 일반 Terraform 계획에는 이 작업과 무관한 23개 삭제 등이 잡혀 있었으므로 적용하지 않았다.

- 정상 statsmodels MLflow 모델을 공개 API로 업로드·등록·자동 검증했다. 업로드와 등록은 각각 HTTP 201, 검증은 `succeeded`였다. 앞서 실행한 역직렬화 payload도 Job 상태가 `succeeded`였다. 두 요청의 HTTP 결과가 다르다는 가정은 성립하지 않으며, RCE는 validator에서 공격자 EC2로 연결된 셸과 UID 10001 실행 문맥으로 판단한다.
- 현재 validator ServiceAccount token을 사용하는 in-cluster kubeconfig와 `kubectl` v1.36.4를 임시로 Pod에 복사해 사전 검사했다. 해당 신원으로 Argo `runtime-builder` Application 상태, `runtime-lab` Pod 목록과 로그 조회가 성공했다. 운영자 kubeconfig는 Pod에 넣지 않았다. 이 `kubectl`과 전용 kubeconfig, 관측 지표 이름·Grafana UID 프록시 경로가 적힌 운영 기록을 포함한 OCI index `ghcr.io/seung-ukk/vuln-mlops@sha256:e20da314cfcd7bfa8759e919156f544a43eb37b7ce143604ea1663d9d1efded4`를 게시하고 ModelGate의 api·mlflow-registry·validator에 적용했다. rollout 후 validator UID 10001에서 `kubectl`로 Argo `Synced/Healthy` revision `ff4d3bf9261fecf6f52f321f7274aea2b5dc0203`와 runtime Pod 목록을 조회하고 운영 기록을 읽었다. 공개 `/readyz`는 Ready다.
- 참가자 안내에는 취약한 MLflow 역직렬화라는 시작 전제와 각 경계의 증거를 명시했다. Git README에는 Deployment에서 바꿀 UID, maintenance mount의 읽기 전용 설정, 고정 작업 실행 방식과 EC2 증명 태그 형식을 적었다. 태그 키는 `lab.vuln-mlops/proof`로 고정이고 값은 `lab-`로 시작하는 참가자 선택 marker다. 멘토 문서는 현재 셸 중심 경로로 다시 쓰고 2026-10-07 프로필은 `docs/archive/`에 보존했다. 공유 Git 브랜치와 공격 노드의 초기화는 각 참가자 종료 후 운영자가 수동으로 한다.
- active 로컬 runtime 매니페스트의 stage 메타데이터와 환경변수를 component/maintenance 명칭으로 정리하고 admission 정책과 코드 호환 분기를 맞췄다. 이 로컬 변경과 새 Git README는 현재 공격 상태의 Gitea 브랜치나 클러스터 runtime-builder에 아직 적용하지 않았다. 관련 로컬 테스트 10개와 렌더링·문법·공백 검사가 통과했다. 현재 공격 commit과 노드 태그는 증거 확보를 위해 유지한다.

- 새 ModelGate OCI index `ghcr.io/seung-ukk/vuln-mlops@sha256:5eb4ae6d2aacc90e9c8dc770aa5a5e759a1022e969e5eea2b700f7aaed9eed48`를 GHCR에 게시하고 EKS에 적용했다. 공개 `/readyz`는 Ready이며 `/api/meta`에서 webhook이 비활성이다. 같은 VPC의 공격자 EC2 `i-030d4a51c1ac858ad` (`10.42.143.106`, 당시 공인 IP `3.35.13.221`)는 `nc`를 갖고 공개 ModelGate에 접근한다. Terraform의 선택적 공격자 보안 그룹과 공개 접근 허용 변경은 적용된 상태다. 아래의 미적용·미설치 문구는 이 날짜 이전의 기록이다.
- 전용 EC2에서 수신하고 공개 모델 업로드·등록 경로에 멘토용 `poc/rce_reverse_shell.py`를 실행했다. validation Job은 `succeeded`였고 validator Pod에서 `uid=10001(modelgate)`의 `/bin/sh` 세션으로 연결됐다. 셸에서 `/opt/modelgate/VALIDATOR_OPERATIONS.txt`를 읽고 제한된 ServiceAccount로 `observability-lab` Pod 목록과 `operations-log` Pod 로그를 조회했다. 로그에는 배포별 Git credential 단서가 있었다. 이 회차의 최초 진입은 멘토 PoC를 사용했으므로 완전한 블라인드 역직렬화 발견성 검증은 아니다.
- 새 `observability-lab`, `delivery-lab`, `runtime-lab` 리소스가 적용됐다. 초기에는 strict VPC CNI 아래 Gitea/Grafana ingress가 시간 초과됐으나 사용자가 제한 NetworkPolicy 네 개를 적용해 복구했다. 이 정책들은 이제 각 kustomization에도 포함된다. Gitea `lab-runtime` baseline `0bb98cddfcf97748c80466b80ee23da4f787a4bb`를 Argo가 `Synced/Healthy`로 반영했다.
- 배포 중 Gitea의 kubelet HTTP readiness가 시간 초과되어 로컬 exec probe로 고쳤다. `operations-log`의 Kubernetes 서비스 환경변수와 포트 변수 충돌도 고쳤고, observability readiness를 localhost exec probe로 조정했다. `operations-log` rollout은 성공했다. 변경 범위의 테스트 7개와 `bash -n` 및 `git diff --check`가 통과했다. 내부 서비스 연결은 계속 확인해야 한다.
- 클러스터의 AWS VPC CNI는 `NETWORK_POLICY_ENFORCING_MODE=strict`다. 정책 적용은 자동 승인 검토에서 두 차례 거부됐고, 이후 사용자가 WSL에서 명시적으로 적용했다. validator에서 Grafana `/api/health`와 UID 기반 Prometheus `delivery_sync_info` 조회가 성공했다. 참가자 reverse shell에서 운영 메모 → Grafana datasource → 지표의 `log_namespace`/`log_selector` → 제한 ServiceAccount의 Pod 로그 → 배포별 credential → Gitea `lab-runtime` clone까지 확인했다.
- 참가자 셸의 제한 Git credential로 `runtime-builder/deployment.yaml` 변경 commit `ff4d3bf9261fecf6f52f321f7274aea2b5dc0203`를 `lab-runtime`에 push했다. Argo는 같은 전체 revision에서 `Synced/Healthy`, 새 runtime-builder Pod는 전용 escape 노드에서 `1/1 Running`이었다. 참가자 ServiceAccount로 읽은 runtime-builder 로그에는 호스트 증거 파일의 `root`/UID 0, 전용 노드 hostname, `vuln-mlops-escape-node` assumed-role ARN, marker `lab-20261008test01`이 있었다. AWS `DescribeTags`는 실제 escape EC2 `i-02ca356d1262414eb`의 `lab.vuln-mlops/proof=lab-20261008test01`을 반환했다. CloudTrail `CreateTags` 관리 이벤트는 같은 인스턴스·키·값, 노드 assumed-role 호출자, `errorCode=null`을 기록했다. 이로써 새 경로의 최종 AWS 변경까지 기능적으로 검증됐다. 호스트 systemd journal 자체는 이 회차에서 독립 조회하지 않았다.
- 최초 셸 획득에는 멘토용 역직렬화 PoC를 사용했다. 최종 Git payload도 WSL 멘토용 `deploy/participant_hostpath.py`로 생성한 뒤 운영자 `kubectl cp`로 참가자 셸의 저장소 작업 디렉터리에 옮겼다. 이후 commit/push는 참가자 셸에서 수행했다. 따라서 **역직렬화·지표 탐색·최종 payload 작성의 완전한 블라인드 발견성은 이 검증으로 주장하지 않는다.** 현재 Gitea 브랜치와 노드 태그는 공격 후 상태 그대로 남아 있어 스크린샷·증거 확보 전 복원하지 않았다.
- 참가자 단서 보완 항목: 운영 메모에는 `delivery_sync_info` 이름과 Grafana UID 프록시 경로를 알아낼 방법이 부족하다. README는 고정 hostPath `task.sh`와 systemd 실행을 설명하지만, 최종 EC2 증명 태그의 키 `lab.vuln-mlops/proof`와 `lab-*` 값 조건은 알려주지 않는다. baseline Deployment에 `lab.vuln-mlops/stage: "05"`와 `STAGE5_MODE`라는 이전 stage 명칭도 남아 있다. 현재 Git 변경은 노드의 대화형 셸을 주는 방식이 아니라, 호스트 systemd가 Git으로 바뀐 task를 root로 실행하는 방식이다. 기능 검증은 완료됐고 이 발견성 간극은 후속 보완이 필요하다.

## 현재 작업: 참가자 셸 중심 경로로 재구성 중

- 사용자가 2026-10-08에 범위를 새로 정했다. 목표는 모델 검증 역직렬화
  RCE → 전용 공격자 EC2의 사설 IP로 validator reverse shell → 내부
  Grafana/Prometheus 단서와 운영 로그의 배포별 제한 Git credential →
  `runtime-builder/deployment.yaml` 변경 → Argo CD 동기화 → 고정 hostPath의
  read-only 및 UID/GID 전환 → 호스트 systemd root 실행 → 노드 역할로 전용
  EC2 인스턴스에 참가자 증명 태그 쓰기다. SSRF, 고정 Job, broker 교환,
  중간 Flag, 공개 `next`
  응답은 새 정답 경로에서 제외한다. 새 계약 초안은
  `docs/ATTACK_CHAIN_CONTRACT.md`에 있다.
- GitHub `origin/main`의 SHA와 로컬 HEAD가 모두
  `eec4976de4c4e29dfa532953f4a5a7c3484ebf26`임을 확인했다. 이 커밋의
  추적 파일은 원격에서 복구 가능하다. 기존 미커밋 문서와 로컬 변수는
  `C:\Users\yoseb\AppData\Local\Temp\vuln-mlops-pre-rework-20261008-020532`
  에 별도 보관했다. 기존 미추적 `checkpoints/`와 `vuln-mlops-gitops/`는
  변경하지 않았다.
- 로컬 코드에서는 mentor용 역직렬화 reverse-shell PoC, validator 운영
  메모, 셸 조사용 도구, 새 `observability-lab`·`delivery-lab`·`runtime-lab`
  매니페스트 및 배포 준비 스크립트를 작성했다. 관측 단서는 Grafana의
  Prometheus 지표에서 `operations-log` Pod를 찾고, validator의 제한된
  ServiceAccount로 그 로그를 읽도록 구성했다. Git 토큰은 저장소에
  고정하지 않고 배포 때 생성하는 Secret에서 운영 로그로 유출된다.
  hostPath, no-IAM ServiceAccount, admission 정책, 전용 노드 선택을 기존
  검증 프로필에서 새 이름으로 옮겼다. 최종 IAM 작업은 전용 노드의
  `lab.vuln-mlops/proof` 키에만 제한된 `ec2:CreateTags`로 바꿨다.
- 로컬 WSL의 실제 MLflow 역직렬화로 같은 프로세스 문맥의 셸 연결과 명령
  실행을 확인했고, 운영 로그의 지표·로그 분리 테스트도 통과했다. 두 새
  kustomization은 로컬 렌더링됐고 셸 문법 및 `git diff --check`가 통과했다.
  새 Docker 이미지는 최종 화면·경로 분리 코드까지 로컬에서 다시 빌드됐다.
  컨테이너 UID/GID 10001, `curl`, `git`, 운영 메모 존재와 mentor PoC 소스
  부재를 확인했다. 새 프로필의 OpenAPI는 모델 업로드·등록·검증 등 9개
  경로를 남기고 기존 SSRF·foothold·webhook 경로를 제외한다.
  Terraform의 선택적 공격자 EC2 보안 그룹은 `validate`를 통과했으나
  적용하지 않았다. 새 hostPath PoC는 호스트 UID·hostname, instance-profile
  ARN과 참가자 marker 기록을 생성하고, 전용 노드의 EC2 증명 태그를 쓴 뒤
  내부 Pod 로그에서 두 증거 파일을 읽도록 구성했다. 이전 S3 기반 PoC의
  테스트 결과는 새 태그 경로의 검증으로 보지 않는다.
  **아직 새 이미지를 게시하거나 EKS에 새 프로필을 적용하지 않았다.**
  따라서 참가자 EC2↔validator 연결, 내부 Git·Argo, hostPath·EC2 태그의 새
  전체 경로는 미검증이다. 공격자 EC2는 사용자가 아직 생성하지 않았다.
  현재 공개 EKS는 아래 2026-10-07 기존 Stage 프로필 상태로 봐야 한다.
- 2026-10-08 최종 AWS 영향을 S3 `GetObject`에서 전용 EC2 노드의
  `lab.vuln-mlops/proof` 태그 쓰기로 변경했다. Terraform은 escape 노드
  launch template에 식별 태그를 명시하고, 선택적 노드 IAM 정책을
  `ec2:CreateTags`의 escape-tagged instance·단일 tag key·`lab-` marker로
  제한한다. 멘토용 manifest 생성기는 호스트 assumed-role의 instance ID를
  추출하여 해당 인스턴스에 태그를 쓴다. 호스트 결과 파일은 내부 Pod 로그에서만
  읽는다. 운영자 수락 시 실제 EC2 태그와 CloudTrail `CreateTags` 관리 이벤트의
  대상 instance ID·호출자 session ID를 대조해야 한다. **실제 AWS 호출과
  이벤트는 아직 검증하지 않았다.** 변경 범위의 로컬 테스트 5개, 생성된 Bash
  문법, Terraform `fmt -check`(변경한 4개 파일)·`validate`, `git diff --check`가
  통과했다. 저장소의 기존 `personal.auto.tfvars`는 전체 `terraform fmt -check`
  대상에서 포맷 차이가 남아 있으나 이번 변경에서 건드리지 않았다.
- 공격자 EC2 `i-030d4a51c1ac858ad`가 같은 VPC의 퍼블릭 서브넷에서
  사설 IP `10.42.143.106`, 현재 공인 IP `3.35.13.221`로 생성됐다.
  인스턴스 프로파일은 없고 전용 보안 그룹 `sg-0adf4e68c6f29dd82`가
  붙었다. SSH는 성공했으나 EC2에서 공개 ModelGate `/readyz`는 응답 없이
  대기했다. 현재 참가자 허용 CIDR에 이 공인 IP가 없으므로 로컬
  `personal.auto.tfvars`에 `3.35.13.221/32`를 추가했다. Terraform과
  ModelGate Service/NetworkPolicy에는 **아직 적용하지 않았다**. EC2에는
  `nc`가 설치돼 있지 않다. 이 공인 IP는 EC2 중지/시작 시 바뀔 수 있다.

## 현재 기준점

- 2026-10-07 재실행에서 공개 Stage 1-A SSRF canary, Stage 1-B marker-only
  RCE, Stage 2 고정 Job과 합성 proof, Stage 3 제한 Git credential 교환을
  순서대로 확인했다. Stage 1-B에는 멘토용 `poc/rce_marker.py`를 사용했으므로
  이 회차를 완전한 블라인드 풀이 검증으로 주장하지 않는다. 공개 `/docs`와
  OpenAPI만으로는 의도한 MLflow flavor와 marker 생성 규칙을 찾기 어려운
  단서 발견성 문제가 남아 있다. 참가자 gateway의 공격 commit
  `45cefa45db719b93420945588226dd123ee57b26`가 Argo에서 같은 revision으로
  `Synced/Healthy`였고, 공개 node-result는 HTTP 200으로 계정
  `707605822656`, 당시 노드 `i-02e6ad123d5453a07`의
  `vuln-mlops-escape-node` assumed-role ARN, 합성
  `FLAG{stage_5_iam_placeholder}`를 반환했다. Falco는 같은 노드에서
  `process=bash uid=0` 호스트 maintenance 경보를 기록했고 같은 이벤트가
  CloudWatch에도 도착했다. 독립 S3 CloudTrail GetObject 데이터 이벤트는
  켜지 않았으므로 확인하지 않았다. 공개 node-result는 결과 JSON의 필드와
  형식을 검사하지만 현재 placeholder Flag의 정확한 값은 검증하지 않는다.
  참가자가 호스트 task를 제어할 수 있는 구조에서 이 응답만으로 실제 S3
  `GetObject`를 독립 증명할 수 없다. 배포별 비공개 합성 Flag의 해시 검증과
  한 객체에 한정된 GetObject 데이터 이벤트는 후속 보완 과제다.
- 재실행 후 참가자 Git baseline을
  `1baa26b92a9bc612fd548092d668e648941240aa`로 복원했다. 이 commit의
  `runtime-builder/deployment.yaml`은 이전 baseline `ff66336`과 동일하며
  Argo는 새 revision에서 `Synced/Healthy`다. 공격 노드
  `i-02e6ad123d5453a07`을 drain·종료하고 새 escape 노드
  `ip-10-42-12-238.ap-northeast-2.compute.internal`
  (`i-02ca356d1262414eb`)로 교체했다. 새 노드는 Ready이고 baseline builder는
  UID/GID 10001로 `1/1 Running`, Falco escape와 CloudWatch 수집기도
  각각 `1/1 Running`이다. 일회성 진단으로 기본 host task, 결과 파일 부재,
  AWS CLI 존재를 확인하고 진단 Pod를 삭제했다. Stage 2 Job 삭제와 ModelGate
  재시작 후 공개 `/readyz`는 HTTP 200, 이전 foothold `/self-rules`는
  HTTP 404였다. 재시작 직후 한 차례 공개 요청 시간 초과가 있었으나
  후속 조회에서 복구됐다.
- 2026-10-07 참가자 접속 재개를 위해 `116.121.12.50/32`,
  `58.29.191.191/32`, `112.170.44.247/32`, `39.7.28.94/32`를
  운영자 EKS API와 ModelGate 참가자 허용 목록 양쪽에 반영했다. 기존
  허용 CIDR은 유지했다. Terraform의 `enable_hostpath_node_capstone=true`를
  로컬 변수에 명시해 현재 Stage 5 배포를 보존했다. EKS cluster CIDR만
  대상 한정 apply했고, refresh-only로 Terraform 참가자 CIDR 출력을
  동기화했다. ModelGate Service, NetworkPolicy, NLB TCP 80 보안 그룹에
  네 CIDR이 모두 반영됐고, 현재 공인 IP `116.121.12.50`에서 공개
  `/readyz` 응답을 확인했다. 나머지 세 IP에서의 실제 접속은 해당
  네트워크에서 별도 확인이 필요하다. 전체 Terraform plan의 EKS add-on과
  OIDC 갱신은 이번 접근 변경 범위 밖이므로 적용하지 않았다.
- 2026-10-07 hostPath capstone 수락 검증 뒤 Git baseline을
  `ff66336f6c1f633194c31306a98323a5d400a83d`로 복원했고, 공격이 실행된
  escape EC2 인스턴스를 종료해 새 노드
  `ip-10-42-24-178.ap-northeast-2.compute.internal`
  (`i-02e6ad123d5453a07`)로 교체했다. 새 노드는 Ready이며 baseline
  `runtime-builder-7dd95bdf77-t6f6d`는 그 노드에서 `1/1 Running`, 실제
  UID/GID는 10001/10001이다. `falco-escape`와 `falco-cloudwatch`가 새 노드에서
  각각 `1/1 Running`이고 DaemonSet rollout도 완료됐다. 일회성 호스트 진단은
  기본 `task.sh`, `node-evidence/result.json` 부재, `/usr/bin/aws` 존재를
  확인한 뒤 삭제됐다. 공개 `/readyz`는 Ready다. 이후 Stage 2의
  `stage-02-secret-reader` Job을 삭제하고 ModelGate Deployment를 재시작했다.
  공개 `/readyz`는 다시 Ready를 반환했고 이전 foothold의 `/self-rules`는
  HTTP 404로 세션 초기화를 확인했다. Argo Application은 복원 commit에서
  `Synced/Healthy`, 새 노드의 baseline builder Pod는 `1/1 Running`이다.

## 새 경로 검증·전환 이력 (각 항목은 당시 시점의 기록)

- 2026-10-07 새 GitOps baseline을 Gitea `stage4-lab`에 push했다. 새 commit은
  `c6d90974a2d47cf0ff31e2daeba5d5a8daaf1f25`이고 변경 파일은
  `runtime-builder/deployment.yaml`과 참가자용 `runtime-builder/README.md`다.
  Argo `runtime-builder` Application은 자동 동기화를 중지한 상태에서
  새 comparison revision `c6d9097`을 인식했다. 자동 동기화 복구 후
  `Synced/Healthy`와 정확한 전체 revision
  `c6d90974a2d47cf0ff31e2daeba5d5a8daaf1f25`를 확인했다. 사전 검증한 JSON patch로
  라이브 `runtime-builder` Deployment의 새 Pod template과 replicas=1을
  적용했고 rollout은 성공했다. Pod `runtime-builder-7dd95bdf77-f5ncx`는
  새 escape worker `ip-10-42-29-117`에서 `1/1 Running`이다. 전환 작업 디렉터리는
  `/tmp/vuln-hostpath-git-cutover-20261007-151900`이다.
- 사용자가 `stage-04-gitops/stage-04-internal` NetworkPolicy의 egress를
  같은 namespace와 `kube-system` DNS로 좁혔다. 기존 넓은 API CIDR egress는
  제거됐고, 별도 `argocd-controller-api-egress` 정책을 확인한 뒤 적용했다.
  적용 후 Argo Application은 `Synced/Healthy` 및 새 Git revision을 유지했다.
- 사용자가 escape 전용 호스트 maintenance 관측 규칙을 포함한 Falco와
  호스트 경보 필터를 포함한 Fluent Bit CloudWatch 수집기를 업그레이드했다.
  공유된 결과에서 `falco-general` 2/2, `falco-escape` 1/1,
  `falco-cloudwatch` 3/3이 Ready이고 escape 노드에도 두 DaemonSet Pod가
  `1/1 Running`이다. 실제 host maintenance 경보의 CloudWatch 도착은
  아직 공격 task를 실행하지 않아 검증 전이다.
- 사용자가 ModelGate `api`, `mlflow-registry`, `validator`를 새 GHCR digest로
  갱신했다. Deployment는 `1/1`, 새 Pod는 general worker
  `ip-10-42-9-133`에서 `3/3 Running`이며 재시작 0이다. API 컨테이너의
  OpenAPI에 `/api/lab/footholds/{proof_id}/stage-05/node-result` 경로가
  존재함을 확인했다. 공개 EIP의 신규 경로, baseline 쓰기 거부, 실제
  호스트 작업·S3 조회는 아직 검증 전이다.
- 라이브 baseline Deployment 사양은 `runtime-builder-hostpath` ServiceAccount,
  token automount 비활성, escape node selector, UID/GID 10001, maintenance와
  evidence 두 mount의 read-only를 만족했다. Pod 안의 실제 `id`도 10001/10001이고,
  maintenance 디렉터리에 무해한 probe 파일 생성은 errno 13으로 거부됐다.
  Pod의 직접 IMDSv2 token 요청은 `URLError`로 실패했다. 독립적인
  UID와 read-only mount 원인 분리, 공개 참가자 경로, 실제 호스트 실행은
  아직 검증 전이다.
- 운영자 일회성 `hostpath-boundary-probe` Pod를 같은 escape worker에서 실행해
  두 보호 장치를 독립 확인했다. 비루트 UID/GID 10001에 writable maintenance
  mount를 준 경우 호스트 권한이 쓰기를 거부했고, root UID/GID 0에 read-only
  mount를 준 경우 mount가 쓰기를 거부했다. Pod는 Completed 후 삭제됐다.
  `task.sh`와 노드 evidence는 이 진단에서 변경하지 않았다.
- 새 ModelGate 이미지의 공개 EIP에서 `/readyz`가 Ready를 반환했다.
  새 RCE foothold 세션 `fa59825f-73a2-4c0e-b549-e3174c47e0c6`에서
  Stage 2 고정 Job이 성공하고 합성 RBAC proof가 확인됐다. 이어 Stage 3
  exchange가 `stage4-lab`/`runtime-builder/`에 한정된 Git credential과
  participant Git gateway를 반환했다. 사용자의 로컬 검증 디렉터리는
  `/tmp/vuln-hostpath-participant-8jLXZe`이며 token 내용은 공유되지 않았다.
  공개 Stage 4 status는 baseline revision의 `Synced/Healthy`와 hostpath mode를
  반환했다. Git 변경 전 `/stage-05/node-result`는 HTTP 502였다. 비루트
  baseline이 root-only evidence 경로를 읽을 수 없어 발생할 수 있으므로
  이것만으로 evidence 파일 부재를 확정하지 않는다. 실제 노드 파일 부재를
  push 전에 별도 확인한다. 참가자 gateway로 `stage4-lab`을 clone했고
  baseline SHA 일치를 확인했다. 멘토용 생성기로 만든 후보는
  `runtime-builder/deployment.yaml` 한 파일만 변경(121 추가/30 삭제)하며
  고정 이미지·노드·SA·S3 대상과 host 스크립트 문법 검사를 통과했다.
  Argo controller identity로 후보 Pod template의 EKS server dry-run도
  통과했다. 실제 Git commit/push와 노드 실행은 아직 진행 전이다.
- 운영자 일회성 `hostpath-final-preflight` Pod가 escape worker에서 기본
  `task.sh` 내용이 `#!/bin/bash`와 `exit 0`뿐임을 확인했고, 별도
  `node-evidence/result.json`이 없음을 확인했다. 호스트 `/usr/bin/aws`도
  존재했다. 진단 Pod는 Completed 후 삭제됐다. 따라서 push 전 공개
  HTTP 502는 선행 결과 파일 때문이 아니며, 현 baseline 비루트 Pod의
  root-only evidence 경로 접근 실패와 부합한다.
- 참가자 Git gateway로 `runtime-builder/deployment.yaml` 한 파일을
  commit `94a46e04e8ba329ee292d2ead39acdb49b1c1ad4`로 push했다.
  공개 Stage 4 API에서 Argo `Synced/Healthy`, 정확한 commit SHA,
  hostpath mode와 Stage 4 합성 proof가 확인됐다. 새 Pod
  `runtime-builder-698998b447-4zm92`는 escape worker
  `ip-10-42-29-117`에서 `1/1 Running`이다. 공개 `node-result` API는
  HTTP 200으로 계정 `707605822656`, 그 worker instance
  `i-0df552f4de9d7be88`의 `vuln-mlops-escape-node` assumed-role ARN,
  `FLAG{stage_5_iam_placeholder}`를 반환했다. 이는 검토된 host task의
  결과 채널이며 Falco·CloudWatch 호스트 실행 관측 및 Pod 직접 IAM
  shortcut 거부는 이어서 독립 확인한다.
- Falco escape 로그에서 `2026-10-07T06:50:51.897408143Z`의
  `Lab escape host maintenance started` 이벤트가 관측됐다. hostname은
  새 escape worker이고 출력은 `process=bash uid=0`이다. CloudWatch
  `filter-log-events`의 text 형식 `length(events)` 질의가 페이지별로
  `1`과 `0` 두 줄을 반환해 셸 숫자 비교가 실패했다. 따라서 같은 명령
  블록의 CloudWatch 상세 조회와 Pod IMDS/evidence 거부, IAM simulation은
  실행되지 않았다. CloudWatch JSON 응답을 합쳐 다시 확인해야 한다.
- 수정된 CloudWatch JSON 조회에서 host maintenance Falco 이벤트 한 건이
  확인됐다. timestamp는 `2026-10-07T06:50:51.897408143Z`, hostname은
  escape worker, 출력은 `process=bash uid=0`으로 Falco 원본과 일치한다.
  변경된 runtime-builder Pod의 실제 UID/GID는 0/0이며, 별도 evidence
  mount의 probe 파일 쓰기는 `EROFS`, 직접 IMDSv2 token 요청은 `URLError`로
  거부됐다. 다만 `iam simulate-principal-policy`의 표 출력은 요청한 두
  S3 ARN 대신 `arn:aws:s3:::${BucketName}/${KeyName}` 한 줄과
  `implicitDeny`를 보여 줬다. AWS의 현재 응답 구조에서는 상위
  `EvalResourceName`이 ARN 템플릿이므로, 이 표는 정확한 객체별 판단이
  아니다. 개별 ARN 결과는 `ResourceSpecificResults`의
  `EvalResourceDecision`으로 다시 확인해야 한다.
- 실제 노드 역할의 inline policy `read-synthetic-node-proof`가 정확한
  `proof/final-flag.txt` 객체 하나의 `s3:GetObject`만 허용함을 확인했다.
  수정한 IAM 시뮬레이터의 `ResourceSpecificResults`에서 해당 객체는
  `allowed`, 같은 버킷의 `proof/other.txt`는 `implicitDeny`였다.
  공개 참가자 경로, 호스트 Falco·CloudWatch 경보, root Pod의 evidence
  mount·IMDS 거부까지 새 capstone acceptance를 통과했다. 남은 필수
  작업은 Git baseline 복구와 장악된 escape worker 교체·재확인이다.
- 참가자 Git gateway에서 baseline Deployment 파일을 복원해 commit
  `ff66336f6c1f633194c31306a98323a5d400a83d`로 push했다. 공개
  Stage 4 status는 그 revision에서 `Synced/Healthy`, `stage4_proof=null`을
  반환했다. 새 runtime-builder Pod `runtime-builder-7dd95bdf77-c4kc4`는
  아직 이전 escape worker `ip-10-42-29-117`에서 `1/1 Running`이고,
  라이브 사양의 UID/GID 10001, 기본 uvicorn command, maintenance/evidence
  read-only mount가 확인됐다. 호스트 파일과 노드 IAM 문맥은 인스턴스 교체
  전까지 오염된 상태로 취급한다.
- 이전 escape node `ip-10-42-29-117`의 managed node group 및 ASG
  소속, desired size 1을 확인한 뒤 drain해 baseline runtime-builder Pod를
  evict했다. Auto Scaling의 desired size를 줄이지 않고 EC2
  `i-0df552f4de9d7be88`을 종료했으며 `aws ec2 wait instance-terminated`가
  완료됐다. 새 escape worker `ip-10-42-24-178`이 Ready이고 general 노드
  두 대도 Ready다. 새 instance ID, 깨끗한 host 상태, baseline Pod와
  Falco/CloudWatch 재배치는 아직 후속 확인 전이다.
- 2026-10-07 사용자 실환경 사전 점검: AWS 계정 `707605822656`와 EKS context
  `vuln-mlops-personal-lab`이 일치했다. general 노드 2대와 escape 노드 1대가
  Ready이고 Argo runtime-builder는 이전 baseline revision
  `290827d73848a9a6235ca3d537ea4b1fd363cfe0`에서 Synced/Healthy다.
  기존 이미지 digest `sha256:8c97af1b9aae5dd8f182f30c11a1a7b5c2ac9cd5b94a91257fa8f6ed56e5a0a4`
  기반 runtime-builder는 general 노드, runtime-maintenance는 escape 노드에서
  각각 1/1 Ready다. 이전 Pod IRSA와 relay Service/NetworkPolicy가 여전히
  존재하므로 노드 IAM 정책 적용 전에 이 workload들을 중지·제거해야 한다.
  Falco general/escape와 falco-cloudwatch DaemonSet은 각각 2/2, 1/1, 3/3
  Ready다. 새 capstone은 아직 실환경에 적용되지 않았다.
- 사용자가 `/tmp/vuln-hostpath-preflight-20261007-123423`에 현재 Argo와
  Stage 5 리소스를 백업하고 `stage4-lab` Git bundle을 만들었다. bundle은
  baseline revision `290827d73848a9a6235ca3d537ea4b1fd363cfe0`의 전체
  이력을 포함하며 `git bundle verify`가 통과했다. 새 Terraform plan은
  1 add/2 update/1 destroy로, escape node에 정확한 S3 단일 객체 GetObject를
  추가하고 이전 runtime-builder Pod IRSA S3 정책을 제거하며 escape node
  group launch template/user-data만 갱신한다. plan은 아직 적용하지 않았다.
- 사용자가 위 저장 plan을 적용해 `1 added, 2 changed, 1 destroyed`로 완료했다.
  Terraform output은 `hostpath_node_capstone_enabled=true`, escape node role
  `arn:aws:iam::707605822656:role/vuln-mlops-escape-node`다. 이전 escape 노드
  `ip-10-42-5-251`은 새 `ip-10-42-29-117`(Ready)로 교체됐다. general 노드
  두 대는 Ready이며 Falco escape 1/1, falco-cloudwatch 3/3 Ready였다.
  공유된 출력에는 이전 두 Stage 5 Pod의 최종 소멸, 실제 host systemd unit 활성,
  노드 역할의 S3 조회, 새 baseline GitOps 배포는 아직 포함되지 않았다.
- 후속 사용자 출력에서 이전 runtime-maintenance Deployment, runtime-relay
  Service, 두 이전 ServiceAccount, ConfigMap, 관련 개방형 NetworkPolicy가
  제거됐다. `runtime-builder` Deployment만 0/0으로 남고 그 Service와
  `stage-05-default-deny`는 유지됐다. 새 escape worker는
  `ip-10-42-29-117` / EC2 `i-0df552f4de9d7be88`이다. SSM
  `describe-instance-information`은 빈 목록을 반환해 SSM 진단은 사용할 수
  없었다. host bootstrap 파일과 systemd 활성 상태는 아직 별도 확인 필요하다.
- 운영자 일회성 Pod `hostpath-bootstrap-check`가 새 escape 노드에서
  root-owned maintenance/evidence 경로와 `task.sh`의 0600 권한, systemd
  service/path 파일을 확인했다. `vuln-mlops-maintenance.path`는 `enabled` 및
  `active`였다. 진단 Pod는 완료 후 삭제됐다. 실제 공격 task 실행과 노드
  역할 S3 조회는 아직 검증하지 않았다.
- 사용자가 새 `runtime-builder-hostpath` ServiceAccount, Stage 5 전용
  Role/RoleBinding, hostPath ingress/egress 제한 NetworkPolicy, Argo controller의
  API egress 정책과 새 admission 정책·binding을 적용했다. 공유된 마지막 출력에서
  ServiceAccount와 정책이 존재하고, Argo controller ServiceAccount는 기존
  `runtime-builder` Deployment patch가 `yes`, 새 Deployment create는 `no`였다.
  admission 정책·binding 적용의 개별 출력은 공유되지 않았으나 명령 블록의
  최종 조회까지 진행됐다. 허용·거부 Deployment의 실제 server dry-run은 다음 단계다.
- Argo controller ServiceAccount로 기존 Deployment에 새 baseline 전체 Pod
  template을 교체하는 `--dry-run=server`가 통과했다. 이미지 digest를 바꾼
  후보는 `stage-05-runtime-builder-only` admission 정책의 “The reviewed
  image and container are fixed” 메시지로 거부됐다. 실제 Deployment는
  여전히 `replicas=0`, 이전 `runtime-builder-iam` ServiceAccount를 참조한다.
  즉 dry-run은 라이브 workload를 시작하지 않았다.
- 2026-10-07 PR #11을 `main`에 merge commit `eec4976`으로 병합했다.
  main CI의 Python test, 앱 container, runtime-client 3개가 모두 통과했다.
  새 앱 OCI index digest는
  `ghcr.io/seung-ukk/vuln-mlops@sha256:64dcffccfe54b2b8a22006c379f16c6b5eac02f9bd24c70845145e0f4d2738d5`다.
  로컬 `main`도 해당 병합 커밋으로 fast-forward했다. 실제 EKS, GitOps branch,
  Terraform plan, Falco/Fluent Bit release에는 아직 새 capstone을 적용하지 않았다.
- 2026-10-07 이미지 발행 사전 검증: 전체 Python 테스트 224개가 통과했다.
  신규 공개 `/node-result` 경로를 기존 API 허용 목록 테스트에 반영하고
  요청 본문이 없음을 확인했다. `.dockerignore`를 Dockerfile이 실제 복사하는
  소스와 기본 requirements만 허용하도록 좁혀 로컬 Terraform 변수와 다른
  작업물을 빌드 컨텍스트에서 제외했다. 새 이미지를 로컬 Docker에서 빌드하고
  컨테이너 안에서 ModelGate, runtime-builder, PoC 모듈을 import했다.
  새 Falco 호스트 경보가 기존 Fluent Bit 필터에서 누락되는 점을 찾아,
  컨테이너 경보와 호스트 maintenance 경보 두 종류만 전송하도록 필터를 수정했다.
  전체 테스트 224개와 Fluent Bit chart 0.58.2 Helm 렌더링이 통과했다.
  이 수집기 변경도 아직 라이브 release에 적용하지 않았다.
  전환 안내서에 기존 `falco-cloudwatch` Helm release 갱신·rollout 확인을
  별도 단계로 명시했다.
  Draft PR #11의 첫 CI에서 runtime-client 이미지 빌드가 실패해,
  `.dockerignore` 허용 목록에 해당 이미지의 Dockerfile과 `crictl.yaml`을
  추가했다. 수정 후 runtime-client 이미지는 로컬 Docker에서 빌드됐다.
  수정 커밋 `5381e1e`의 PR CI는 Python test, 앱 container 빌드,
  runtime-client 빌드 3개가 모두 통과했다. PR은 draft이며 아직 main 병합,
  GHCR 새 digest 발행, EKS/GitOps 전환은 하지 않았다.
  이 이미지는 로컬 태그 `vuln-mlops:hostpath-preflight`일 뿐 GHCR에 게시되지
  않았고 EKS에 적용되지 않았다.
- 2026-10-07 새 hostPath capstone은 **로컬 구현·오프라인 검증 단계**다.
  `stage-05-hostpath` baseline/overlay와 admission 정책, escape worker의
  systemd path/service bootstrap, node IAM 단일 객체 opt-in, 이전 Pod IRSA
  S3 정책의 opt-in 시 제거, 제한된 결과 API, 멘토용 PoC 생성기와 경계 테스트를
  추가했다. Terraform opt-in 기본값은 `false`이며 실제 EKS와 GitOps 저장소에는
  아직 적용하지 않았다. 변경된 앱 이미지를 새 OCI digest로 발행해야 한다.
  `docs/HOSTPATH_CAPSTONE_MIGRATION.md`에 전환·검증·노드 교체 순서를 기록했다.
  Terraform `fmt -check`/`validate`, Kustomize 렌더링, 관련 Python 테스트
  84개가 통과했다. 사용자의 WSL 가상환경에서 새 경로 테스트 17개도
  통과했고, 생성한 host task는 WSL `bash -n`을 통과했다. 대상 EKS endpoint
  일치를 확인한 뒤 새 admission 정책·바인딩의 `--dry-run=server`가 통과했다.
  이 드라이런은 실제 Deployment 변경의 허용 여부까지 검증하지 않는다.
  사용자가 생성한 Terraform plan은 1 add/2 update/1 destroy이며,
  escape node에 정확한 S3 객체의 `s3:GetObject`를 추가하고 이전 Pod IRSA
  객체 정책을 제거한다. escape node group은 같은 launch template의 버전만
  갱신하고 새 user-data에는 host maintenance unit이 포함된다. plan은
  **적용하지 않았다**. 실제 systemd·node IAM/S3 검증은 아직 수행하지 않았다.
  기존 Falco 공통 규칙은 호스트 프로세스를 제외하므로 escape release에만
  추가할 관측 전용 host maintenance 규칙을 별도 values 파일로 만들었다.
  pinned chart 9.2.0의 Helm 렌더링과 경계 테스트가 통과했지만 라이브 Falco
  업그레이드와 실제 event 수집은 아직 하지 않았다.
  추가 검토에서 writable maintenance hostPath에 결과 JSON을 두면 호스트 실행
  없이 위조할 수 있음을 확인해, 노드가 별도 `node-evidence` 디렉터리에 쓰고
  Pod는 그 디렉터리를 고정 read-only hostPath로만 읽도록 수정했다. 이에 따른
  로컬 테스트·Terraform 검증·Kustomize 렌더링은 통과했다. 사용자가 만든
  `/tmp/vuln-hostpath-node-review.tfplan`은 이 수정 이전 계획이므로 **폐기**했다.
  새 `/tmp/vuln-hostpath-node-review-v2.tfplan`은 사용자가 생성했고 1 add/2
  update/1 destroy만 포함한다. 저장된 계획을 읽어 새 user-data에
  `maintenance/task.sh`와 별도 `node-evidence` 디렉터리가 모두 있으며 이전
  합성 node Flag는 없음을 확인했다. IAM은 escape node의 정확한 S3 객체
  `s3:GetObject`만 추가하고 Pod IRSA 정책을 제거한다. **아직 적용하지 않았다.**
  수정된 admission 정책·바인딩도 대상 EKS의 `--dry-run=server`를 통과했다.
  기존 정책의 `last-applied-configuration` 경고만 있었고 실제 저장은 하지 않았다.
  이는 정책 표현식의 서버 검증이며 공격/거부 Deployment의 라이브 허용 여부는
  아직 검증하지 않았다.
- 2026-10-07 새 목표: Stage 1~3을 유지하고 Stage 4 GitOps가 전용 escape
  worker의 hostPath 기반 노드 장악으로 이어지며, 최종 S3 객체는 Pod IRSA가
  아닌 노드 IAM 역할로 읽는 단일 경로를 설계 중이다. 기존 5-A/5-B는
  이전 프로필이며 현재 EKS 배포는 아직 새 목표로 전환되지 않았다. 목표
  계약은 `STAGE_CONTRACTS.md` 상단에 추가했다.
- 새 목표의 실습 환경은 사용자가 현재 개인 EKS로 지정했다. 해당 EKS의
  escape worker에는 기존 maintenance agent와 Falco·Fluent Bit 등이 있어
  전환 시 이전 agent 제거, 관측 신뢰 범위, 노드 교체 reset이 필요하다.
- 2026-10-07 공개 EIP의 `/docs`·`/readyz`는 집 IP에서 HTTP 200, Stage 1
  SSRF canary와 marker-only RCE는 재검증 성공했다. 이 회차의 Stage 2~5와
  새 참가자 IP `112.170.44.247`의 직접 접속은 확인하지 않았다.

- Base: `main` at `74ac10a` (PR #10); capstone 작업 브랜치는
  `codex/hostpath-node-capstone` (draft PR #11). 기존 미추적 `checkpoints/`는
  이 작업에서 변경하지 않음
- Latest merged commit: `74ac10a` (PR #10)
- Repository: `https://github.com/seung-ukk/vuln-mlops`
- Container: `ghcr.io/seung-ukk/vuln-mlops`
- 현재 상태: PR #10까지 main에 병합됐고 개인 EKS 공개 EIP에서 Stage 1~4와
  독립 Stage 5-A runtime/합성 노드 proof, 5-B 명령 주입/IRSA/S3 proof가 모두 통과했다.
  아래 과거 "미적용" 문장은 당시 시점의 기록이며 이 기준점이 우선한다.

### 2026-10-06 Falco 관측 계층 준비 및 general 설치

- 블루팀 Falco만 별도 `falco-observe` namespace에 두고 general/escape worker를
  서로 다른 Helm release로 관측하는 설정을 `deploy/falco/`에 추가했다. 참가자
  경로, Argo, Stage 5 workload, IAM과 node group은 변경하지 않았다.
- 공식 Falco chart 9.2.0/Falco 0.45.0, modern eBPF, least-privileged capability
  mode와 container metadata plugin 0.7.4를 선택했다. rule 자동 추적, Falco
  Talon/response action, 외부 HTTP 출력은 껐다. 기본 upstream rule 대신 lab
  namespace의 process-start 규칙만 로드하고 JSON stdout에 namespace/Pod/container/
  executable name만 기록한다. 명령 인자, 파일 경로, Flag 본문은 출력하지 않는다.
- 현재 escape `t3.medium`의 allocatable은 1930m CPU/약 3.2Gi 메모리이고,
  설치 전 Pod 요청 합계는 160m/32Mi였다. Falco 요청은 노드당 100m/512Mi,
  상한은 500m/1Gi다. Metrics API가 없어 실제 사용량은 아직 측정하지 못했다.
- general/escape 차트를 각각 Helm 9.2.0으로 로컬 렌더링했다. escape는 정확한
  node selector와 taint toleration을 사용하고 CRI metadata socket은
  `/run/containerd/containerd.sock` 하나만 설정한다. 블루팀 namespace는 ingress를
  거부하며 DNS와 plugin 초기 다운로드용 HTTPS만 허용한다. 경계 테스트 3개 통과.
- 사용자가 개인 EKS에서 `falco-observe` namespace와 NetworkPolicy를 적용하고
  `falco-general` release를 설치했다. general worker 두 대에 Falco Pod가 각각
  `1/1 Running`, 재시작 0이었고 modern BPF syscall source가 열렸다. 시작 직후
  snapshot에는 두 Pod의 event drop 0, Falco RSS 약 89Mi가 보였으며 공개 EIP
  `/readyz`는 ready였다. snapshot의 약 50% Falco CPU는 시작 후 2초 측정값이라
  지속 사용량의 증거로 해석하지 않는다. AppArmor annotation deprecation 경고와
  root PID namespace가 없어 BPF iterator를 비활성화했다는 로그가 있었지만
  DaemonSet rollout과 source 시작은 성공했다.
- 사용자가 `falco-escape` release도 개인 EKS에 설치했다. escape worker
  `ip-10-42-5-251`의 Falco는 `1/1 Running`, 재시작 0이고 container plugin 0.7.4가
  CRI socket 하나를 사용하며 modern BPF syscall source가 열렸다. 같은 시점에
  general 두 Pod와 `runtime-maintenance`도 Ready, 공개 EIP `/readyz`도 ready였다.
  시작 후 2초 snapshot의 escape RSS는 약 89Mi이고 event drop은 0이었다.
- Falco 0.45는 사용자 규칙의 `evt.dir=<`가 항상 참이라며 deprecated 경고를 냈다.
  조건을 제거하고 경계 테스트 3개와 general/escape Helm render를 다시 통과했다.
  사용자가 수정된 값으로 두 release를 revision 2까지 upgrade했다. 공유된 Pod
  목록은 rollout 중간 시점이라 모든 Falco Pod의 최종 Ready 상태까지는 확인하지
  못했다. `runtime-maintenance` Deployment는 여전히 `1/1`이었다.
- 운영자 전용 `python -c pass` 센서 검증에서 general Falco는
  `runtime-builder`의 `process=python`을, escape Falco는
  `runtime-maintenance`의 `process=python`을 각각 `Lab container process started`
  JSON 경보로 기록했다. 경보에는 namespace/Pod/container/executable만 있고
  명령 인자나 proof 내용은 없었다. 이는 센서 동작 증거이며 참가자 Stage 5
  풀이 경보 검증은 아니다. Helm chart의 AppArmor annotation deprecation 경고는
  남아 있으나 두 release upgrade는 성공했다.
- 안정 상태의 자원·event drop 확인, 실제 5-A/5-B 공격 이벤트 관측은 남아 있다.
  `kubectl logs`는 임시 확인 채널이며 장기 보존용 수집기는 미구현이다. 설치
  순서와 rollback은 `deploy/falco/README.md`에 있다.
- 후속 사용자 출력에서 revision 2의 `falco-general`과 `falco-escape` DaemonSet
  rollout이 모두 성공했고 general 2개/escape 1개 Pod는 전부 `1/1 Running`, 재시작
  0이었다. 현재 운영자는 `kubectl logs`로 Falco 경보를 조회할 수 있으나 Pod 교체,
  노드 교체, kubelet 로그 회전 때문에 3일 조회 가능성은 보장되지 않는다.
- CloudWatch 7일 보존용 수동 배포 설정을 `deploy/falco/cloudwatch-values.yaml`,
  IAM 문서 생성기, NetworkPolicy, `CLOUDWATCH.md`에 준비했다. 공식 Fluent Bit
  chart 0.58.2/앱 5.1.2의 DaemonSet이 Falco 컨테이너의 process-start 경보만
  읽어 단일 log group으로 전송하도록 제한했다. 별도 Pod Identity role은 정확한
  cluster/namespace/ServiceAccount만 신뢰하고 해당 log stream의 생성·쓰기만 허용한다.
  Terraform은 수정하지 않았고 AWS log group/role/association 및 collector는 아직
  EKS에 적용하지 않았다. Fluent Bit Helm 로컬 render와 Falco/CloudWatch 경계
  테스트 6개가 통과했다. 기존 Pod Identity Agent의 세 노드 배치 확인이 선행돼야 한다.
- 사용자 사전 점검에서 AWS 계정 `707605822656`, EKS cluster ARN/kube context가
  `vuln-mlops-personal-lab`으로 일치했고 general 2대/escape 1대가 Ready였다.
  `eks-pod-identity-agent` add-on은 Terraform 관리 태그를 가진 `ACTIVE`
  `v1.4.0-eksbuild.3`였다. 공유된 출력에는 Agent Pod의 노드별 목록이 없어 escape
  worker에 Agent가 실제 실행 중인지는 아직 확인하지 못했다. 수동 배포 안내서에서
  add-on 생성·삭제 절차를 제거하고 `Environment=personal-lab` 태그로 정정했다.
- 추가 출력에서 Pod Identity Agent DaemonSet은 `DESIRED/CURRENT/READY = 3/3/3`,
  재시작 0이었고 general 2대와 escape 1대에 각각 `1/1 Running` Pod가 있었다.
  따라서 CloudWatch 수집기 배포 전 Agent 노드 배치 조건은 충족됐다. 아직 log group,
  IAM role, Pod Identity association, Fluent Bit는 생성·설치되지 않았다.
- 이어서 사용자가 CloudWatch log group `/vuln-mlops/vuln-mlops-personal-lab/falco`를
  7일 보존으로 생성하고 전용 IAM role/policy, Pod Identity association
  `a-g1mtdbki4ngobpmvi`, collector NetworkPolicy와 `falco-cloudwatch` Helm revision 1을
  수동 적용했다. 수집기 DaemonSet은 3/3 Ready, general 2대와 escape 1대에서 각각
  `1/1 Running`, 재시작 0이었다. 새 log group 조회에 과거 Falco 로그를 읽어 전송한
  runtime-builder·runtime-maintenance 및 Gitea process-start JSON 경보가 나타났다.
  이는 CloudWatch 전송이 general/escape 양쪽에서 동작함을 확인하지만, 출력의
  Stage 5 경보는 설치 전 05:10 UTC에 생성된 것이므로 설치 직후 probe 경보의 신규
  수신 여부는 아직 분리 확인하지 못했다. 수집기 오류 로그와 두 Stage 5 Deployment의
  최종 Ready 출력도 아직 공유되지 않았다.
- 사용자는 후속 신규 probe/조회가 정상 동작한다고 확인했다. 공유된 Fluent Bit
  출력에는 general 노드 수집기의 Falco log stream 생성 성공과 오류 없는 기동이
  보였고, `runtime-builder`와 `runtime-maintenance` Deployment는 각각 `1/1 Ready`였다.
  신규 CloudWatch 조회 이벤트 본문은 공유되지 않았으므로 그 개별 시각/내용은
  독립 증거로 기록하지 않는다. 현재 관측 계층은 운영 중이며 차단 기능은 없다.
- 참가자 EIP 허용 IP를 추가하려고 사용자가 `participant_access_cidrs`에
  `134.231.169.94/32`를 더했다. Terraform plan은 `modelgate_participant_access_cidrs`
  output만 변경했고 apply는 `0 added, 0 changed, 0 destroyed`로 성공했다.
  이어 실행한 `manage.sh deploy`와 `status`는 모두 EKS Kubernetes API의
  `13.125.112.89:443` 접속 타임아웃으로 실패했다. 따라서 새 IP의 Service
  `loadBalancerSourceRanges`/NetworkPolicy 적용 및 EIP 실제 접속은 미확인이다.
  운영자 현재 공인 IP와 EKS `publicAccessCidrs`를 대조한 뒤 재시도해야 한다.
- 카페에서 확인한 운영자 공인 IP는 `116.121.12.50`, 실제 EKS API 허용 CIDR은
  집 IP `1.236.20.205/32`뿐이었다. 두 번째 Terraform plan/apply는 카페 IP를
  `participant_access_cidrs`에 잘못 추가해 output만 다시 변경했고 AWS 리소스 변경은
  0건이었다. 로컬 무시 파일 `infra/terraform/personal.auto.tfvars`에서 카페 IP를
  `participant_access_cidrs`에서 제거하고 `public_access_cidrs`에 집 IP와 함께
  추가했다. 이 수정은 아직 Terraform plan/apply 또는 EKS API에 반영되지 않았다.
- 사용자는 `134.231.169.94/32`가 멘토 IP로 운영자 EKS API 접근과 참가자 EIP
  접근이 모두 필요하다고 정정했다. 로컬 tfvars에서 이 IP를 두 CIDR 목록에 모두
  포함시켰다. 카페 IP `116.121.12.50/32`는 배포용 임시 EKS API CIDR에만 두고
  참가자 목록에서는 제외했다. 대상 지정 Terraform plan/apply로 EKS cluster의
  `publicAccessCidrs`에 집·카페·멘토 IP가 모두 반영됐고 AWS 조회에서 cluster
  `ACTIVE`를 확인했다. 이 plan은 EKS cluster 1건만 변경하여 전체 plan에 나타난
  애드온/OIDC 변경을 적용하지 않았다. 참가자 CIDR output에는 이전 apply의 카페 IP가
  남아 있었으나 `refresh-only` plan/apply로 그 IP만 output에서 제거했다. 실제 AWS
  리소스 변경은 0건이었다. 이어 `manage.sh deploy`와 `status`가 성공했고 ModelGate
  NLB의 고정 EIP는 `3.35.2.114`, target health는 healthy, Load Balancer Controller는
  `1/1 Ready`였다. 실제 Kubernetes Service `loadBalancerSourceRanges`와 ModelGate
  NetworkPolicy 양쪽에 멘토 `134.231.169.94/32`가 포함되고 카페
  `116.121.12.50/32`는 제외된 것을 조회했다. 멘토 현장 네트워크에서의 HTTP 접속은
  아직 직접 확인하지 않았다.

### 2026-10-06 병행 Stage 5 실제 검증과 운영진 문서

- PR #10의 PR check 3개와 병합 후 main CI check 3개가 성공했다. 현재 게시 이미지의
  OCI index digest는 `sha256:8c97af1b9aae5dd8f182f30c11a1a7b5c2ac9cd5b94a91257fa8f6ed56e5a0a4`다.
- 사용자가 이 digest로 개인 EKS의 IAM 병행 프로필을 배포했다. Argo baseline은
  `80889134f3eb15529629062941f26df86a9968db`에서 `Synced/Healthy`였고,
  general worker의 runtime-builder와 escape worker의 runtime-maintenance가 Ready였다.
  builder→agent `/healthz`는 HTTP 200, 공개 EIP `/readyz`는 ready였다.
- 새 공개 foothold에서 Stage 2 Job과 Stage 3 credential 교환이 성공했다.
  Stage 4 Git commit `533820aeef879422ba8735f7724a22b78fedbe1c`가 Argo
  `Synced/Healthy`로 반영됐고 status에 Stage 4 proof, `runtime_relay`,
  `builder_endpoint`가 함께 표시됐다.
- 5-A의 body 없는 공개 POST는 고정 CRI 작업과 `FLAG{stage_5_node_placeholder}`를
  반환했다. `{"command":"id"}` body를 보낸 요청은 HTTP 400으로 거부됐다.
  5-B는 proof 전 404, build 명령 주입 후 `completed`, 예상 계정과
  `assumed-role/...runtime-builder/...` ARN 및 `FLAG{stage_5_iam_placeholder}`를
  반환했다. 이 결과는 임의 노드 장악이나 CSI 경로를 뜻하지 않는다.
- 이 수동 풀이 이후 사용자가 `reset --stage5-iam`을 실행했다. 공유된 출력에서
  Argo runtime-builder는 baseline revision `290827d73848a9a6235ca3d537ea4b1fd363cfe0`의
  `Synced/Healthy`, runtime-builder와 runtime-maintenance는 각각 `1/1` Ready였다.
  공유된 출력에는 개별 Job·proof 삭제 내역이 없어 그 부분은 독립 확인으로 기록하지 않는다.
- 멘토·운영진용 현재 구성 소개서 `MENTOR_LAB_OVERVIEW.md`와 단계별 PoC 답안지
  `MENTOR_STAGE_POC.md`를 추가했다. 팀원의 블라인드 단서 발견성, clean destroy 후
  두 번째 apply, 팀 계정 이전, Stage 6은 여전히 미검증/미구현이다.
- 팀원에게 별도로 전달할 시작 문서 `PARTICIPANT_START_GUIDE.md`를 추가했다.
  EIP, 접속 확인, 첫 조사 지점과 기록 방법만 담고 정답·Flag 값은 제외했다.
- 운영진 PoC의 Stage 1-A/1-B 설명을 실제 `poc/ssrf_canary.py`와
  `poc/rce_marker.py`의 요청 순서, 출력값, 자동화 범위에 맞춰 정리했다.

### 이전 작업 기록: 독립 Stage 5-A / 5-B 병행 구성

- 사용자가 두 최종 문제를 같은 EKS에서 독립적으로 제공하도록 범위를 확장했다.
  현재 배포된 5-B는 general worker의 `runtime-builder` 명령 주입→IRSA→합성
  S3 proof이며 유지한다. 새 5-A는 전용 escape worker의 독립
  `runtime-maintenance` agent가 고정 containerd CRI proof 작업을 수행한다.
  참가자에게 임의 CRI config/command/path나 노드 장악 권한을 제공하지 않는다.
- 기존 runtime relay ConfigMap/Service/NetworkPolicy를 공용 Kustomize 구성으로
  이동해 두 프로필이 같은 고정 코드를 사용한다. IAM overlay에서는 Service와
  NetworkPolicy를 독립 agent만 선택하도록 patch하고, 별도 ServiceAccount는
  IRSA annotation과 자동 토큰 mount가 없다. IAM builder는 general worker에서
  socket 없이 남는다. 새 agent의 image/node/socket/container shape를 고정하는
  admission policy를 추가했다.
- Stage 4 상태 응답이 `iam-build`에서 runtime relay와 builder 경로를 모두
  반환하도록 하고, runtime proof endpoint는 Stage 4 proof와 Argo
  `Synced/Healthy`를 검사한다. 내부 agent는 ModelGate에서 직접 접근할 수 없고
  Git으로 활성화된 builder만 고정 maintenance 요청을 전달한다. 이전 socket
  프로필의 남은 ModelGate→relay NetworkPolicy도 IAM deploy에서 삭제한다.
  Gitea README와 참가자 PoC에 두 경로를 설명했다.
- 전체 로컬 Python 테스트 199개, Python compile, Bash 문법, `git diff --check`,
  기존 socket 프로필과 새 IAM migration overlay의 Kustomize 렌더가 통과했다.
  IAM 렌더는 ModelGate→agent 직접 NetworkPolicy가 없고 builder→agent만
  선택되는 것을 확인했다.
- 사용자가 현재 개인 EKS API에서 새 `stage-05-runtime-maintenance-fixed`
  ValidatingAdmissionPolicy/Binding을 기존 검증 이미지 digest로 server-side dry-run했고
  두 리소스 모두 통과했다. IAM migration overlay 전체도 같은 이미지로 EKS
  server-side dry-run에 통과했다(`dryrun_exit=0`). 실제 정책 적용과 agent 배포는
  아직 하지 않았다. 새 이미지 게시, 실제 EKS 배포, 공개 EIP 5-A/5-B 병행
  참가자 검증, reset 재확인은 하지 않았다. 현재 EKS는 5-B만 실행 중이다.

### Runtime-builder IAM/S3 실제 EKS 전환

- PR #8의 세 check와 병합 후 main CI가 성공했다. 게시된 GHCR OCI index digest는
  `sha256:b7ae9077d1e3c94d7a26a274a8de65dfc56830f5febec390c1ba67e5a79bed9d`
  이며 `linux/amd64` manifest를 포함한다.
- 새 admission policy와 IAM migration overlay의 EKS server-side dry-run이 통과했다.
  `deploy --skip-foundation --stage5-iam`은 ModelGate 새 image rollout과 Gitea IAM
  baseline push `1f9888d9c1bb0b79da42d7797a9beb24d4cafca8`까지 진행했다.
- Argo는 기존 Deployment의 escape node selector/toleration 등이 SSA merge에서
  남아 새 admission policy의 general-worker 조건에 거부되어 `OutOfSync`였다.
  운영자 SSA `--force-conflicts` dry-run도 runtime-relay, init container, socket
  volume을 남겨 실제 적용하지 않았다. 검토된 IAM base의 Pod template만 교체하는
  JSON patch를 server-side dry-run한 뒤 적용했다. 새 Deployment가 rollout했고
  IRSA ServiceAccount와 위 새 digest를 사용한다. Argo는 revision `1f9888d`에서
  `Synced/Healthy`로 복구됐다.
- ModelGate 세 컨테이너가 새 digest를 사용하고 ModelGate→builder `/healthz`는 HTTP
  200, 공개 EIP `/readyz`는 ready다. 공개 EIP 참가자 경로에서 Stage 1 SSRF/RCE,
  Stage 2 Job, Stage 3 credential 교환, Stage 4 Git push `99457834bbd874b22c1e2bcfabbc75b6a8fcaa96`
  및 Argo `Synced/Healthy`, Stage 5 명령 주입과 IRSA/S3 합성 proof를 확인했다.
  `main; true; #`는 completed, `main; false; #`는 failed였다. build subprocess가
  `/tmp`에서 실행되므로 `python -m runtime_builder.aws_proof`만 실행하면 모듈을
  찾지 못해 failed/404가 된다. `main; cd /opt/modelgate && python -m
  runtime_builder.aws_proof; #`로 재시험하여 completed와 예상 계정,
  `assumed-role/...runtime-builder/...` ARN, 합성 Flag를 확인했다. 운영자 진단이
  만든 proof 파일을 제거해 404를 확인한 뒤 공개 참가자 경로로 재실행했다.
  S3 객체는 여전히 알려진 합성 placeholder이며 전체 shortcut denial과
  destroy 후 clean second apply 검증은 남아 있다.
- 이번 수동 복구를 `orchestrate.sh`의 IAM migration 단계에 반영했다. 검토된 base
  Deployment에서 Pod template JSON patch를 생성하고 서버 dry-run 결과에서
  old socket/escape 필드가 제거됐는지 검사한 다음 실제 patch한다. 관련 로컬 테스트
  34개가 통과했다. 이 재현성 수정은 PR #9로 병합됐고 실제 IAM deploy 재실행에
  사용됐다.
- 현재 마무리 순서는 IAM 프로필 `reset --stage5-iam`으로 참가자 Git 변경과
  transient proof/Job을 복원하고, 이번 migration 복구와 참가자 PoC 문서/테스트를
  PR/CI로 보존한 뒤 reset 및 이후 재배포 재현성을 필요한 범위에서 확인하는 것이었다.
  기존 socket 전용 `accept`는 IAM 프로필에 사용하지 않는다. 팀원 블라인드 단서
  발견성과 clean destroy→second apply는 이번 공개 참가자 PoC로 검증되지 않았다.
- 공개 참가자 검증 후 운영자가 `reset --stage5-iam`을 실행했다. Gitea의 실습
  commit `9945783`은 baseline commit `59c0be6a5b8645ef189a7f6588a6dbd19c66dcf3`으로
  복원됐고 Argo는 해당 revision에서 `Synced/Healthy`였다. Stage 2 Job이 삭제되고
  ModelGate와 runtime-builder Pod가 재시작/rollout되어 임시 세션과 `/tmp` proof가
  초기화됐다. 이 reset은 실제 EKS에서 통과했다.
- PR #9 첫 CI는 188개 테스트가 통과하고 shortcut 테스트 한 개에서
  `UnicodeDecodeError`가 발생했다. 새 `iam_template.py` import로 생성된
  `deploy/eks-lab/__pycache__/*.pyc`를 기존 테스트가 모든 파일을 UTF-8로 읽으며
  포함한 것이 원인이다. shortcut 검사는 배포 텍스트 파일 확장자만 읽도록 수정했다.
- PR #9 수정 후 로컬 전체 Python 테스트 189개가 통과했다. PR check와 병합 후
  main CI run `37361085911`이 성공했다. 사용자가 병합 커밋 `9cd7f48`을 main으로
  동기화한 뒤 같은 검증된 OCI digest로
  `deploy --skip-foundation --stage5-iam`을 다시 실행했다. 수정된 JSON template
  patch 경로가 완료됐고 runtime-builder rollout, 전체 표시 Deployment Ready,
  Argo baseline revision `59c0be6a5b8645ef189a7f6588a6dbd19c66dcf3`의
  `Synced/Healthy`를 확인했다. 전체 참가자 PoC를 반복 실행하지는 않았다.

### Runtime-builder IRSA/S3 초기 준비 기록

- Terraform의 EKS IRSA OIDC provider를 활성화하고, 실습 전용 private S3 버킷 하나,
  `stage-05-runtime/runtime-builder-iam` ServiceAccount만 신뢰하는 IAM role, 정확히
  `proof/final-flag.txt` 한 객체의 `s3:GetObject`만 추가했다. Flag 본문은 Terraform
  state에 저장하지 않는다.
- 기존 socket 기반 runtime-builder Pod에 역할을 곧바로 붙이지 않았다. 먼저 별도의
  일회성 진단 Job으로 동일 ServiceAccount의 STS identity, 합성 객체 읽기, 버킷 전체
  접근 거부를 확인하도록 manifest와 운영자 절차를 작성했다. 현재 Stage 1~5 클러스터
  배포는 이 변경으로 수정되지 않았다.
- IRSA/S3 대상 및 기존 Terraform 경계 테스트 33개, `terraform fmt -check`,
  `terraform validate`, `git diff --check`가 통과했다. 사용자 Terraform plan은
  `6 add, 1 change, 0 destroy`였고, 유일한 제자리 변경은 CoreDNS
  `v1.14.6-eksbuild.4` → `v1.14.7-eksbuild.10`이었다. 저장된 계획을 실제 적용해
  OIDC provider, 전용 IAM role/policy, 비공개 S3 bucket과 암호화/공개 차단을 생성했다.
  사용자가 `proof/final-flag.txt`에 합성 placeholder를 업로드했고 `head-object`에서
  30바이트/AES256을 확인했다. 첫 IRSA 진단 Job은 AWS 호출 전에 `exec format error`로
  실패했다. 원인은 공식 AWS CLI 이미지의 `linux/arm64` manifest digest를 x86_64
  general worker에 고정한 것이며, `linux/amd64` digest와 node architecture selector로
  수정했다. 사용자가 Job을 재실행해 `arn:aws:sts::707605822656:assumed-role/
  vuln-mlops-personal-lab-runtime-builder/...`, `FLAG{stage_5_iam_placeholder}`,
  `bucket-wide access denied`를 확인했다. 이 결과는 IRSA→고정 S3 객체 경계의 실제
  AWS 성공 증거다. 다음은 참가자 경로의 runtime-builder 앱·명령 주입 구현이다.
- 작은 FastAPI `runtime_builder` 앱의 첫 코드와 대상 테스트를 추가했다. baseline은
  build 요청을 거부하고 legacy profile은 의도적으로 shell에 source reference를
  삽입한다. 응답은 명령 출력 없이 상태만 반환한다. 별도 maintenance module은 STS
  account/assumed-role ARN과 정확한 합성 S3 객체만 읽어 형식을 검증한다. 앱 코드
  5개 대상 테스트와 compile이 통과했다. Docker 이미지에 boto3와 앱 코드를 포함할
  준비를 했지만 새 OCI digest 게시·manifest pin·Argo/ModelGate 참가자 경로 연결은
  아직 하지 않았으며 현재 EKS 워크로드는 기존 socket 경로로 작동한다.
- ModelGate에 proof-bound `stage-05/build/info`, `stage-05/build`, `stage-05/aws-proof`
  참가자 gateway를 추가했다. Stage 2 완료, Argo `Synced/Healthy`, Stage 4 proof,
  `iam-build` mode가 모두 확인되어야 내부 앱에 중계하며, 응답은 정해진 상태/계정/역할/
  합성 Flag 형태만 허용한다. 기존 socket relay 경로는 현재 클러스터용으로 유지했다.
  신규 앱/gateway와 기존 Git/runtime API 대상 테스트 24개가 통과했다. 새 앱 이미지
  게시 및 Stage 5 Deployment 전환 전에는 이 신규 경로가 공개 EIP에서 열리지 않는다.
- `lab/stages/stage-05-iam-app/`에 현재 overlay에 포함되지 않는 전환용 Deployment,
  Service, NetworkPolicy, admission policy 초안을 추가했다. `__RUNTIME_BUILDER_IMAGE__`
  placeholder는 새 OCI index digest가 게시되기 전에는 적용할 수 없다. 이 초안은
  general worker의 단일 앱 컨테이너와 IRSA ServiceAccount를 사용하고 socket/hostPath를
  제거한다. 변경된 앱/gateway 및 기존 API 계약 대상 테스트 27개가 통과했다.
- 전환안 작성 후 전체 Python 테스트 178개, Python compile,
  `terraform fmt -check`/`validate`, `git diff --check`가 통과했다. 새 앱은 아직
  이미지 digest 게시·실제 EKS rollout·공개 EIP 참가자 검증 전이다.
  참가자 단서로 전환용 Gitea `runtime-builder/README.md`를 작성하고, Stage 4
  증거가 있을 때만 열리는 build info 응답에 `source_ref`와 legacy shell resolver
  힌트를 추가했다. 현재 socket orchestrator는 README를 Gitea에 seed하지 않으므로
  이 단서는 IAM 앱 전환 시 함께 게시해야 하며 현재 EKS 참가자에게는 보이지 않는다.
  관련 앱/gateway 테스트 10개가 통과했다. Stage 4 전 build info 접근은 HTTP 409로
  거부되며 README에는 Flag 원문이 없다.
- 기존 socket 배포를 건드리지 않는 별도 IAM Kustomize overlay와 전환용 overlay를
  추가했다. 전환용 overlay는 운영자 SSA가 기존 `runtime-builder` Deployment를
  직접 덮어쓰지 않도록 제외하고, 새 Gitea baseline push 후 Argo가 기존 Deployment를
  reconcile하게 한다. `orchestrate.sh deploy --skip-foundation --stage5-iam`은 새 OCI
  digest 입력을 검사하고 Terraform role ARN·bucket·region을 manifest에 치환한다.
  ModelGate도 같은 새 digest로 갱신하며 Gitea baseline에 참가자 README를 포함한다.
  이후 `reset --stage5-iam`을 사용하고 socket 프로필 명령의 IAM Deployment 변경은
  거부한다. 현재 이미지는 아직 CI에 게시되지 않았으므로 실제 EKS 전환은 미실행이다.
  로컬 IAM overlay와 전환 overlay Kustomize 렌더, placeholder 치환/파싱,
  배포·앱·gateway 대상 테스트 39개 및 Bash 문법 검사가 통과했다.
- PR #8의 첫 CI에서 `ci/container`와 `ci/runtime-client`는 통과했으나 `ci/test`는
  실패했다. CI 실패 로그의 직접 조회는 네트워크 timeout으로 완료하지 못했지만,
  로컬 전체 테스트에서 IAM 역할 ARN의 계정 중립적 형식 검사 문자열까지 금지하던
  기존 shortcut 테스트 실패를 재현했다. 실제 12자리 계정이 들어간
  하드코딩 ARN만 금지하도록 검사를 좁혔고, 수정 후 전체 Python 테스트가 통과했다.
  이 수정은 PR #8에 포함되어 세 PR check와 병합 후 main CI가 통과했다.
- 이 진단 Job은 운영자 검증이며 참가자 경로 성공 증거가 아니다. 최종 목표는
  Pod 명령 실행→IRSA→합성 S3 proof이고, 이 자체를 노드 장악으로 부르지 않는다.

### 현재 ModelGate 이미지 갱신

- 병합 커밋 `cde5312`의 GHCR `:main`과 `:sha-cde5312`는 같은 OCI index
  `sha256:8f0a902437e5f276e4c316fdb7d77b0f955337c075199b8c221a9193b2158da9`를
  가리킨다. index에 `linux/amd64` manifest가 포함되어 있다.
- EKS Stage 1~3 overlay, Stage 5 runtime relay의 base/desired Deployment,
  ValidatingAdmissionPolicy를 이 digest로 동기화했다. runtime-client pin은 유지했다.
- 관련 Stage 1/EKS·Stage 5 intended/shortcut 계약 테스트 26개, 전체 EKS Kustomize
  render, `git diff --check`가 통과했다.
- 이미지 pin 변경은 PR #7/CI로 보존되었고 현재 개인 EKS에 적용되었다.
- PR #7 병합과 세 CI check 성공 후 개인 EKS `deploy --skip-foundation`을 실행했다.
  기존 클러스터의 Stage 5 admission policy가 이전 relay image digest를 고정해 둔 상태에서
  orchestration이 새 Git baseline을 먼저 push하여 Argo가 새 Deployment를 거부했다.
  Application revision `ff2c3dcb81084cbea1f190ba4ce93a26b4fc3177`은 `OutOfSync/Healthy`이고,
  policy의 "runtime-builder image and container shape" 거부가 원인임을 확인했다.
- 사용자가 같은 `vuln-mlops-stage4` field manager로 새 Stage 5 admission policy를 먼저
  server-side apply했다. Stage 5 overlay server dry-run/실제 apply와 runtime-builder rollout이
  성공했고, Argo 자동 동기화는 실패한 같은 revision을 재시도하지 않아 제한된 수동 sync로
  `ff2c3dc`를 `Synced/Healthy`로 복구했다.
- Stage 1~3 overlay apply 뒤 ModelGate와 canary rollout이 성공했다. ModelGate 세 컨테이너
  모두 새 digest를 사용하고 공개 EIP `/readyz`는 `{"status":"ready"}`를 반환했다.
- 재발 방지를 위해 deploy가 Git baseline 복원 전에 Stage 5 policy를 먼저 적용하도록
  순서를 수정했다. 공개 EIP를 지정한 `accept`가 participant API와 Git gateway를
  해당 주소로 호출하고 readiness를 기다리도록 확장했다. 관련 orchestration/shortcut
  테스트와 Bash 문법 검사를 통과했으며 공개 EIP Stage 1~5 `accept` 실행은 대기 중이다.
- 공개 EIP `accept`에서 Stage 1 SSRF/RCE, Stage 2 Job, Stage 3 datasource와 arbitrary
  reference denial은 통과했다. Stage 4 Git clone은 ModelGate→Gitea TCP 3000 timeout으로
  HTTP 502가 났다. Gitea Service/Endpoint는 정상이고 두 Pod는 같은 general node였다.
- Stage 4 Kustomize의 최상위 `namespace: stage-04-gitops`가 ModelGate Git egress 정책을
  잘못된 namespace로 옮긴 것이 원인이다. namespace transformer를 vendored Argo 리소스에만
  적용해 ModelGate 정책은 `modelgate-lab`, Git client 정책은 `stage-02-rbac`에 남도록
  수정했다. 사용자 EKS에서 올바른 ModelGate egress 정책 생성 후 내부 Gitea HTTP 200 확인.
- Stage 5 overlay 재적용은 Argo가 소유한 relay downward-API `fieldRef` 두 필드에서만
  SSA 충돌이 났다. Kubernetes 기본 `apiVersion: v1`을 base/desired manifest에 명시해
  해당 Deployment의 server-side dry-run이 통과했다. `--force-conflicts`는 사용하지 않았다.
- 관련 Stage 4/5와 orchestration intended/shortcut 테스트 50개, Stage 4/5 EKS
  Kustomize render, Bash 문법 및 `git diff --check` 통과.
- 수정된 `deploy --skip-foundation` 재실행이 성공했다. admission policy를 Git baseline
  변경 전에 적용했고 Argo는 새 baseline `7042b46ebbc27dea925102ea123da1f4a9cbac91`에서
  `Synced/Healthy`였다. Stage 1~5 workload rollout도 모두 통과했다.
- 공개 EIP `accept` 재실행에서 Stage 1~3, Stage 4의 제한된 Git push 및 Argo reconciliation
  `bc1b9c5`가 통과했다. Stage 5 proof 호출은 HTTP 502였고, 실패 후 Git baseline이
  복원되었다. ModelGate에서 Stage 5 runtime relay `/healthz`도 ConnectTimeout이었다.
- `modelgate-runtime-relay-egress` NetworkPolicy는 올바른 namespace에 있고 relay Pod는
  escape 노드에서 `2/2 Running`이다. Terraform의 escape 노드 보안 그룹은 general
  노드로부터 TCP 8080 ingress를 허용하지 않아 cross-node relay 연결이 차단된다.
  general SG → escape SG TCP 8080 단일 규칙과 intended/shortcut 테스트를 추가했다.
  관련 Terraform 테스트 28개, `terraform fmt -check`, `terraform validate`,
  `git diff --check` 통과. 개인 EKS에서 Terraform plan `1 add, 0 change, 0 destroy`를
  검토·적용했고 ModelGate → runtime relay `/healthz` HTTP 200을 확인했다.
- 공개 EIP `accept` 재실행에서 Stage 1~5 intended path와 대표 shortcut denial이 모두
  통과했다. Stage 4 제한 Git push `3241f056251d31fe9aa8a0e996ec50e452edfdd6`는
  Argo `Synced/Healthy`로 이어졌고 Stage 5 synthetic node proof를 얻었다. Cleanup 후
  baseline `eb62d47d397c715bca0144d94481dc0bd8c9db89`가 `Synced/Healthy`다.
  이 acceptance는 공개 참가자 API/Git gateway 경로를 실행하면서도 운영자 `kubectl`로
  초기화·우회 거부·복원을 수행하는 자동 검증이다. 독립 참가자의 단서 발견성은 별도
  사용자 실습으로 확인해야 한다.
- 사용자가 운영자 `kubectl` 없이 공개 EIP와 제한된 Git gateway로 Stage 1~5를 직접
  실행했다. Stage 4 commit `d94c32c167f3a2fd5b10759cb25a198ba3af98f7`의
  Argo `Synced/Healthy`와 Stage 5 `FLAG{stage_5_node_placeholder}` 응답을 확인했다.
  이후 운영자 `reset`으로 Git baseline `7f8fcbff78d6d99d5c3283b6b4df2fd2ffff57df`를
  복원했고 Argo `Synced/Healthy`, Stage 2 Job 삭제, ModelGate/runtime-builder 재시작과
  전체 workload Ready를 확인했다. 멘토 보고용
  `docs/MENTOR_PROGRESS_REPORT.md`와 힌트 포함 참가자 절차
  `docs/PARTICIPANT_POC.md`를 작성했다. Stage 5는 임의 노드 명령 또는 AWS IAM
  접근을 검증한 것이 아니며 Stage 6은 미구현이다.
- Stage 5의 노드 marker 쓰기·노드 IAM identity 확인 확장을 검토하기 전에 현재
  Stage 1~5 동작 기준을 `checkpoints/stage1-5-stable-2026-10-05/`에 로컬 source patch와
  미추적 파일 사본, 복구 절차로 보존한다. 이 checkpoint는 Terraform state나 EKS
  snapshot이 아니다. 실제 클러스터는 위 `reset` 이후 baseline 상태다.

## 완료된 작업

### Application

- FastAPI 기반 ModelGate UI/API
- Pod-local MLflow Tracking/Registry
- 비동기 validation worker
- SQLite job queue
- health/readiness endpoint
- non-root container image와 restricted security context

### Stage 1 SSRF

- 공개 UI에서 `/docs`를 안내하고 OpenAPI의 `GET /api/system/info`가 service, namespace,
  port, path로 분리된 bounded synthetic canary 좌표만 제공하는 discovery 경로
- MLflow webhook redirect SSRF 경로
- Docker-internal synthetic canary
- EKS `stage-01-canary` restricted namespace와 ClusterIP-only synthetic canary
- ModelGate Pod에서 정확한 namespace/Pod label/TCP 9000으로만 허용한 양방향
  NetworkPolicy 계약
- `compose` 또는 `eks` 고정 이름만 받으며 임의 내부 URL을 받지 않는 PoC target 선택
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
- 관측된 proof UUID로만 접근 가능한 participant foothold relay
- relay가 SelfSubjectRulesReview와 고정 Stage 2 Job 생성·상태·로그만 제공하며 Kubernetes
  token, 임의 API path/URL, namespace, manifest, Pod 이름은 외부 입력으로 받지 않음

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
- 외부 ModelGate API의 proof-bound relay를 통한 Stage 1 RCE → Stage 2 RBAC 연결
- relay가 만드는 Job과 reviewed `attack-job.yaml`의 완전 일치 계약 테스트
- 완료된 고정 Job은 TTL 자동 삭제 대신 orchestration reset에서 명시적으로 삭제되어
  참가자가 Stage 2 이후 중단해도 Stage 3 세션 선행 증거가 유지됨

### Stage 3 Monitoring Stack Trust Abuse

- Prometheus 3.14.0과 Grafana 13.2.2 digest 고정 배포
- namespace 한정 Kubernetes service discovery RBAC
- Grafana anonymous Viewer datasource proxy를 통한 Prometheus 조회
- metric에는 topology와 opaque credential reference만 노출
- broker에서 repository/branch/path 제한 synthetic Git credential과 Flag 교환
- default-deny 및 `monitoring-runner` client 전용 NetworkPolicy
- `monitoring-runner` ServiceAccount와 Stage 3 client network identity를 사용하는
  restricted `monitoring-session` relay; Kubernetes token은 mount하지 않음
- 완료된 Stage 2 Job이 있는 proof 세션에만 datasource discovery, 고정 topology query,
  정확한 credential reference exchange를 제공하는 participant API
- credential 응답에 같은 proof 세션의 고정 Stage 4 Git gateway와 application status 경로 제공
- ModelGate는 Stage 3 service에 직접 연결하지 못하며 `monitoring-session:8080`만 연결
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
- ModelGate EIP/내부 Service를 그대로 사용하는 proof-bound Git smart-HTTP gateway 구현:
  단일 repository의 `info/refs`, upload-pack, receive-pack만 허용하고 Gitea UI/API는 비공개
- Stage 3 Basic credential을 내부 Gitea에서 실제 검증하며 request body 8 MiB 제한,
  arbitrary service/repository/upstream과 cookie/redirect response header 중계 거부
- 참가자는 operator `kubectl` 없이 고정 application status API에서 Argo revision,
  `Synced/Healthy`, Stage 4 proof와 Stage 5 mode를 확인
- ModelGate status RBAC은 Stage 4 Application 및 Stage 4/5 `runtime-builder` Deployment의
  `resourceNames` 기반 `get`만 허용하고 list/watch/mutation은 금지

### Stage 5 Runtime Socket -> Escape Worker

- `stage-05-runtime` namespace와 전용 escape worker label/taint 경계
- `runtime-builder` 하나에만 containerd socket과 reviewed `crictl` client 노출
- digest 고정 Debian workload, non-privileged security context, no SA token, default-deny network
- digest 고정 runtime-client init container가 packaged `crictl`을 도구 `emptyDir`로 복사하고,
  ConfigMap 기반 고정 runtime relay만 socket을 mount하도록 분리
- ModelGate→runtime relay TCP 8080만 허용하는 양방향 NetworkPolicy와 ClusterIP Service
- Stage 4 `Synced/Healthy`, proof annotation, runtime mode를 모두 검증한 뒤 body 없는 고정
  Stage 5 endpoint만 relay하고 command/path/image/Pod/CRI config 입력을 받지 않음
- baseline relay는 비활성화하고 ValidatingAdmissionPolicy가 reviewed Stage 4 proof/mode와
  결합된 `RELAY_ENABLED=true` 전환만 허용하여 Stage 1 Pod의 조기 직접 호출을 차단
- 임시 CRI container와 proof 파일을 요청 종료 전에 제거하고 고정 synthetic 응답만 반환
- Argo CD mutation을 기존 `runtime-builder`의 update/patch로 제한
- ValidatingAdmissionPolicy로 node, image, socket/client path, volume/container shape 고정
- 기존 CRI sandbox에 다음 `runtime-builder` attempt를 주입하는 intended path
- node에만 존재하는 synthetic proof를 기존 Pod `tmp` emptyDir로 제한 복사
- containerd CRI operation ID와 namespace-scoped Kubernetes exec audit evidence 검증
- 다른 workload/hostPath/node/privileged 변경과 create/delete shortcut 거부

### Terraform/EKS foundation

- Terraform 1.16.x와 AWS provider 6.62.0 고정
- VPC module 6.7.3, EKS module 21.26.0, EKS Pod Identity module 2.9.0 고정
- 서울 리전 기본값과 2개 AZ public/private subnet 구성
- private worker와 비용을 제한한 단일 NAT gateway 구성
- EKS 1.36 기본값, 1.37 opt-in 및 API-only Access Entry 구성
- public EKS endpoint를 명시적 operator IPv4 `/32`로 제한
- root/creator 대신 별도 cluster operator role에 Kubernetes admin Access Entry 부여
- EKS control-plane 다섯 로그 유형과 CloudWatch 보존 설정
- CoreDNS, kube-proxy, VPC CNI, Pod Identity Agent 관리형 add-on 구성
- VPC CNI NetworkPolicy strict mode와 CNI 권한의 Pod Identity 분리
- strict mode에서 CoreDNS가 먼저 격리되지 않도록 foundation → CoreDNS 전용 정책 →
  CoreDNS add-on을 순서대로 적용하는 `bootstrap.sh` 구성
- 부트스트랩의 명시적 non-root profile, saved plan, 중단 후 재실행, 최종 no-drift
  안전장치 구성
- general/escape managed node group, label/taint, escape 1-node 상한 구성
- EKS 모듈의 공용 node security group을 비활성화하고 general/escape 전용 security
  group과 최소 control-plane/DNS/HTTPS 규칙으로 Stage 5 노드 lateral 경계 구성
- 고정된 짧은 node IAM role 이름과 불필요한 IRSA/OIDC provider 비활성화
- IMDSv2 강제, hop limit 1, instance metadata tag 비활성화
- Node IAM에 Stage 6 storage/CSI 권한을 추가하지 않는 shortcut 테스트
- 기존 EKS overlay의 IMDS 및 private-network wildcard 허용 제거

### EKS Stage 5 runtime-client image

- EKS 1.36과 맞춘 공식 `crictl` v1.36.0 archive와 공식 SHA-256 고정
- digest 고정 Debian 최종 이미지와 BuildKit checksum 검증 구성
- `/run/stage5/containerd.sock`만 기본 runtime/image endpoint로 지정
- GHCR `vuln-mlops-runtime-client` 전용 amd64 build/publish job 구성
- pull request에서는 build-only, main/tag push에서만 package publish
- 로컬 이미지에서 `crictl version v1.36.0`, 설정 파일, curl/wget 부재 검증
- main CI에서 GHCR 게시 완료, OCI index digest
  `sha256:556d3f1837edfcd0da44627a39dbe890822217c66b1beec2d31f5ff6c48a930b` 고정
- Stage 5 초기/desired Deployment가 같은 digest를 사용하며 host `crictl` mount 제거

### EKS Stage 1 deployment

- ModelGate `main` OCI index digest
  `sha256:9953d23e8102114873c3a52eaecd0a2e80d260cb0b7ee09ae348c0af3d66a244` 확인
- EKS overlay에서 api, mlflow-registry, validator 세 컨테이너를 동일 digest로 치환
- base 개발 tag는 유지하되 AWS 배포에서는 mutable tag 사용 금지
- EKS 1.36 `ACTIVE`, general node 2대와 escape node 1대 `Ready` 확인
- escape node만 `lab.vuln-mlops/escape=true:NoSchedule` taint 보유 확인
- Stage 1 전체 manifest client dry-run 통과
- EKS overlay에는 개인 계정 ID, cluster/operator ARN, subnet/security-group ID 및
  credential을 넣지 않는 account-portability negative test 추가
- 팀 계정 전환 시 별도 Terraform state/tfvars와 임시 deployment role, 승인된 operator
  `/32`만 교체하고 Kubernetes manifest와 public GHCR digest는 재사용
- 개인 계정 EKS에서 namespace, ServiceAccount, ClusterIP Service, Deployment,
  NetworkPolicy 실제 apply 완료
- ModelGate Pod `3/3 Running`, restart 0, general node 배치 및 escape taint 회피 확인
- Deployment와 실행 container 세 개 모두 고정 OCI index digest 사용 확인
- `kubectl port-forward`를 통한 `/healthz`와 `/readyz` 응답 확인
- 운영자 격리 CPython 3.11.17 환경에서 MLflow 3.13.0, statsmodels 0.14.5로
  외부 API-only marker RCE smoke 실행
- artifact upload → model registration → validator load → UUID proof 흐름 성공,
  `validator marker observed` 확인 후에도 Pod `3/3 Running`, restart 0 유지
- EKS synthetic canary는 ServiceAccount token, egress, Ingress/LoadBalancer/NodePort,
  host namespace/hostPath/runtime socket 없이 구성
- Kustomize render에서 ModelGate→canary TCP 9000 egress 패치와 canary→ModelGate-only
  ingress가 정확히 합성되고 canary image도 같은 OCI index digest로 치환됨을 확인
- 개인 계정 EKS에서 public HTTPS first hop → 고정 cluster-local canary redirect SSRF가
  `MODELGATE_INTERNAL_SSRF_PROOF`를 반환하는 intended path 확인
- canary access log의 `/canary` 요청 출발지 `10.42.30.104`가 ModelGate Pod IP와 일치하고,
  canary Pod는 general node에서 `1/1 Running`, restart 0임을 확인
- 비인가 Pod의 FQDN direct-canary 시도는 VPC CNI strict-mode DNS 단계에서 timeout으로
  거부됨을 확인
- 테스트 Pod의 egress를 canary namespace/Pod/TCP 9000으로 명시 허용하고 DNS를 우회한
  ClusterIP 직접 접근도 connection timeout으로 거부되어 canary ingress selector 경계 확인
- shortcut smoke용 임시 Pod와 NetworkPolicy 삭제 완료

### EKS Stage 2 composition

- 기존 kind Stage 2 base와 attack Job 제외 계약을 그대로 재사용
- 통합 EKS overlay가 Stage 1과 Stage 2 control resources를 함께 렌더링
- Terraform Kubernetes Service CIDR을 `172.20.0.0/16`으로 명시하고 API Service IP를
  `172.20.0.1`로 계산하는 output 추가
- EKS overlay에서 kind 전용 `10.96.0.1/32`, `172.16.0.0/12:6443`을 제거하고
  ModelGate와 Stage 2 Job에 `172.20.0.1/32:443`만 허용
- 현재/개인 계정 control-plane ENI, public endpoint IP, account ID는 manifest에 넣지 않음
- EKS 1.36 ValidatingAdmissionPolicy server dry-run: passed
- 운영자 kubectl을 1.36.4로 맞춰 EKS 1.36.4와 client/server minor 일치 확인
- Terraform plan/apply는 실제 resource 변경 없이 `kubernetes_service_ip=172.20.0.1`
  output만 state에 추가
- 실제 EKS에 Stage 2 namespace, SA, RBAC, synthetic Secret, admission, NetworkPolicy apply 완료
- ModelGate identity의 self-review와 Stage 2 Job create는 허용되고, Secret 직접 get,
  RoleBinding create, SA token mint, Pod exec, Node read는 거부됨을 확인
- EKS admission이 잘못된 Job name/SA/image, privileged, hostPath/Secret volume, env override
  7개 shortcut을 모두 거부하고 Job/Pod가 생성되지 않음을 확인
- ModelGate identity가 fixed `stage-02-secret-reader` Job을 생성하고 EKS API Service
  `/32:443` 경계를 통해 `monitoring-runner`로 실행해 8초 만에 exit 0 완료
- 실행 Pod는 pinned kubectl digest, projected short-lived SA token, no env/no host mount를 유지
- Job Pod가 general node에 배치되고 restart 0으로 완료됨을 확인
- ModelGate identity가 Pod log에서 base64 synthetic proof를 읽고
  `FLAG{stage_2_rbac_chaining_placeholder}`로 디코딩하는 intended path 확인
- CloudWatch EKS audit에서 operator role의 impersonated effective identity가 ModelGate SA인
  Job create `201`과 invalid Job create `422`를 확인
- CloudWatch EKS audit에서 `monitoring-runner`의 `stage-02-flag` Secret get `200` 확인
- Stage 2 EKS intended path, shortcut denial, NetworkPolicy, node placement, audit evidence 완료

### EKS Stage 3 composition

- 통합 EKS overlay가 Stage 1~3 control resources를 함께 렌더링하며 임시
  `attack-client.yaml`은 intended boundary-crossing acceptance 시에만 별도 생성
- kind 전용 `10.96.0.1/32`, `172.16.0.0/12:6443` API 목적지를 Stage 3 공통
  NetworkPolicy에서 제거
- Prometheus Pod만 `172.20.0.1/32:443`에 접근하는 별도 EKS NetworkPolicy 추가
- Grafana와 credential broker는 ServiceAccount token을 mount하지 않고 Kubernetes API
  egress도 받지 않으며, 모든 Stage 3 Service는 cluster-internal 유지
- Prometheus, Grafana, credential broker에 readiness/liveness probe와 requests/limits 추가
- Prometheus 3.14.0, Grafana 13.2.2, nginx-unprivileged 1.29.1 pinned OCI index가 모두
  `linux/amd64` manifest를 제공함을 registry에서 확인
- 실제 EKS apply와 세 Deployment rollout 성공, 모두 general node에서 `1/1 Running`,
  restart 0 및 ClusterIP-only Service 유지 확인
- Prometheus에만 projected ServiceAccount token이 주입되고 Grafana와 credential broker에는
  token volume이 없음을 실제 Pod에서 확인
- `monitoring-runner` client가 Grafana datasource proxy를 통해 topology와 opaque credential
  reference만 발견하고 broker에서 범위 제한 synthetic Git credential과 Stage 3 Flag 교환
- 임의 credential reference는 `404`, Prometheus TCP 9090 직접 접근은 NetworkPolicy timeout,
  Secret/workload/RBAC/exec/node 권한은 모두 거부
- CloudWatch EKS audit에서 Prometheus SA의 namespace 한정 services/endpoints/pods watch
  `200`만 확인했으며 acceptance client는 검증 후 삭제
- 현재 client는 운영자가 생성하고 `exec`하는 acceptance harness다. 팀 실습 전에는
  operator `exec` 없이 Stage 2 output identity에서 이어지는 참가자용 handoff가 필요

### EKS Stage 4 composition

- Argo CD CRD만 server-side apply하고 기존 Stage 1~3 field ownership은 건드리지 않도록
  `deploy/eks-lab/stage-04` 하위 overlay를 별도 적용 단위로 구성
- 상위 EKS overlay는 Stage 1~4 전체 구성을 계속 렌더링
- Stage 4 공통 NetworkPolicy에서 kind 전용 API CIDR을 제거하고 Argo CD application
  controller만 `172.20.0.1/32:443`에 접근하는 별도 policy 추가
- Redis 8.2.3-alpine OCI index를
  `sha256:08ad0b1d280850169a790dba1393ff7a90aef951fc19632cf4d3ce4f78e679ba`로 고정
- Argo CD 3.5.3, Gitea 1.27.3-rootless, Redis 8.2.3-alpine, nginx-unprivileged 1.29.1
  pinned image가 모두 `linux/amd64` manifest를 제공함을 registry에서 확인
- 사용하지 않는 Argo CD server/Dex/ApplicationSet/notification entrypoint는 replica 0
- Redis는 synthetic password Secret을 사전 생성해 upstream API-dependent initializer를
  제거하고 ServiceAccount token automount와 Kubernetes API egress를 비활성화
- Gitea와 baseline/desired runtime-builder에 probes와 requests/limits 추가
- Stage 4 EKS 전용/전체 통합 Kustomize render와 관련 attack/shortcut 테스트 35개 통과
- 첫 실제 apply에서 upstream Redis `secret-init`이 token 비활성화 때문에 실패하고
  controller/repo-server가 Redis Secret을 기다리는 현상을 확인
- Redis 인증을 synthetic Secret으로 사전 생성하고 API-dependent init container를 제거해
  token/API egress 없이 복구; 핵심 Pod 5개 `1/1 Running`, restart 0 확인
- Gitea synthetic 사용자/repository와 pre-receive hook을 bootstrap하고 baseline branch를
  Argo에서 `Synced/Healthy`로 확인
- `main` branch와 repository root의 `forbidden.txt` push는 hook이 거부
- 허용된 `stage4-lab:runtime-builder/` 변경 commit
  `e6755e2f2fb4bc26d49150f36efa359f3439c640`을 Argo CD가 reconcile
- Application `Synced/Healthy`, live Deployment `mode=git-controlled`, pinned image와
  `FLAG{stage_4_gitops_placeholder}` proof 확인
- Argo controller는 기존 `runtime-builder` patch/update만 허용되고 workload create/delete,
  다른 Deployment patch, Secret/ServiceAccount/RBAC create는 거부
- privileged와 hostPath dry-run은 Kubernetes validation/Pod Security/Stage 4 admission에서 거부
- live runtime-builder에 ServiceAccount token, hostPath, privileged, Stage 5 nodeSelector 없음 확인
- CloudWatch EKS audit에서 Argo application controller SA의 `runtime-builder` Deployment
  patch `ResponseComplete 200` 확인
- Gitea는 `emptyDir` 기반이므로 Pod 재생성 뒤 사용자/repository/hook bootstrap을 다시
  실행해야 하며 팀 실습용 자동 bootstrap/reset은 아직 필요

### EKS Stage 5 composition

- 상위 EKS overlay가 Stage 1~5를 렌더링하도록 `deploy/eks-lab/stage-05` 조합 추가
- Stage 5 base에 Stage 4 EKS 전용 controller API egress와 내부 통신 제한을 동일하게 적용하고
  두 overlay 간 파일 일치를 테스트로 고정
- escape 관리형 노드만 cloud-init으로 고정 synthetic node proof를 생성하며 general node,
  Kubernetes manifest, IAM 자격 증명에는 proof를 추가하지 않음
- 기존 escape node에는 새 launch-template version을 적용해 롤링 교체했으며 general node와
  control plane은 변경하지 않음 (`0 added, 2 changed, 0 destroyed`)
- Stage 5/EKS 관련 계약 테스트 37개, 통합 Kustomize render, Terraform fmt/validate 통과
- 새 escape node 한 대가 `Ready`, taint/label 유지, containerd 2.2.7과 exact socket 확인
- containerd socket은 `stage-05-runtime/runtime-builder` Pod 하나에만 노출되고 token,
  privileged, host namespace는 비활성화
- synthetic Git baseline `fc15e866d1e182d652a6333ea3023a40ed892730`과 desired revision
  `49346f7c3e25642937e0abfd38dc47af07620a89`을 Argo가 `Synced/Healthy`로 reconcile
- digest-pinned Debian proof image를 escape node containerd가 pull하고 CRI create/start를 통해
  `FLAG{stage_5_node_placeholder}` 획득; 단기 container는 runtime에서 정리되고 Pod proof도 reset
- 다른 workload create/delete/update, general node 이동, 다른 socket, privileged, SA token,
  hostNetwork shortcuts는 RBAC/admission에서 거부
- CloudWatch audit에서 Argo controller patch `ResponseComplete 200`과 Stage 5 Pod exec 14개
  audit ID의 `ResponseStarted`/`ResponseComplete` 및 streaming status `101` 확인
- acceptance 후 Terraform plan `No changes`

### Stage 1~5 deployment orchestration

- `deploy/eks-lab/orchestrate.sh`에 `deploy`, `reset`, `status` 실행 모드 추가
- 기존 `infra/terraform/bootstrap.sh`를 재사용해 strict NetworkPolicy/CoreDNS 순서를 보존
- Terraform output의 cluster name, region, operator role로 임시 kubeconfig를 생성해 개인/팀
  계정별 ARN이나 account ID가 Kubernetes manifest에 들어가지 않도록 유지
- Stage 1~3는 기존 client-side ownership으로 적용하고 Argo CD CRD와 Stage 4~5는 기존
  `vuln-mlops-stage4` server-side manager로 적용해 재실행 시 field conflict를 피하도록 분리
- 기존 GitOps deployment에서는 Git baseline을 apply 전에 복원해 Argo-owned runtime 필드가
  reviewed manifest와 일치한 상태에서 Stage 4~5를 재적용
- Stage 1, canary, Stage 3, Argo CD/Gitea, Stage 5 workload rollout을 고정 목록으로 대기
- Gitea의 고정 synthetic 사용자/repository를 idempotent하게 생성하고 pre-receive scope hook과
  `stage4-lab:runtime-builder/` Stage 5 baseline을 재구성
- 원격 baseline이 이미 같으면 Git commit/push를 생략하고, 내용이 다를 때만 scope hook을
  통과하는 normal forward commit을 생성하며 force-push는 사용하지 않음
- reset은 고정 Stage 2 Job, Stage 3 client, ModelGate/runtime-builder의 ephemeral proof state만
  초기화하며 namespace, Terraform resource, Secret/RBAC 전체 삭제는 수행하지 않음
- orchestration intended/shortcut 정적 계약 테스트와 WSL `bash -n` 통과
- 첫 live 재실행은 전체 overlay를 새 field manager 하나로 적용해 기존 manager와 충돌했고
  안전하게 중단됨; `--force-conflicts` 없이 위의 ownership 분리 방식으로 수정
- 수정 후 실제 EKS 재실행에서 기존 Gitea repository 감지, baseline 복원, 전체 workload
  Ready와 Argo `Synced/Healthy` revision `d9d50273b7e74f580ae2f13b23e69c5277652891` 확인
- 동일 deploy 재실행에서 Gitea commit/push 없이 같은 revision을 유지하고 전체 workload
  Ready와 Argo `Synced/Healthy`를 재확인해 idempotent resume을 검증함
- reset 실행 후 ModelGate와 Stage 5 runtime-builder Pod가 새 UID로 교체되었고,
  Stage 5 proof 파일과 고정 Stage 2 Job, Stage 3 client가 모두 제거된 것을 확인함
- `accept` 모드는 reset 이후 Stage 1 SSRF/RCE, Stage 2 RBAC, Stage 3 monitoring,
  Stage 4 GitOps, Stage 5 CRI proof와 대표 shortcut denial을 순서대로 실행하고 reviewed
  Git baseline과 임시 리소스를 정리하도록 구현함
- 첫 실제 `accept` 실행은 Stage 1~4를 통과했지만 Stage 5 rollout 직후 종료 중인 이전
  Pod를 선택했고, 실패 cleanup이 새 Gitea 포트포워드에 Git remote를 갱신하지 않아 중단됨
- Ready/non-terminating Pod 중 최신 Pod를 선택하고 baseline cleanup마다 현재 동적
  포트포워드로 Git remote를 갱신하도록 수정함
- 수정 후 실제 `accept` 재실행에서 Stage 1 SSRF/RCE, Stage 2 RBAC, Stage 3 monitoring,
  Stage 4 GitOps, Stage 5 CRI proof와 대표 shortcut denial이 모두 통과함
- cleanup이 reviewed baseline revision `8819a05e455e6edb8d6ceda5aa698f91156e3dc2`를
  정상 push했고 최종 Argo `Synced/Healthy`와 전체 workload Ready를 확인함
- destroy 후 clean second apply는 아직 필요

### Delivery

- GitHub Actions Python test
- GitHub Actions container build와 GHCR publish
- `main`, `latest`, `sha-*`, `v*` tag policy
- Compose와 Kubernetes deployment 환경변수 반영
- GHCR anonymous pull 검증
- `docs/STAGE1_5_WRITEUP.md`에 Stage별 핵심 원리, 실제 요청/응답, synthetic proof,
  shortcut denial과 자동 acceptance 절차를 정리한 멘토용 답안 추가

## 최근 검증 결과

- Python tests: `122 passed`
- Python compileall: passed
- Docker Compose config validation: passed
- Terraform format: passed
- Terraform init with pinned provider/modules: passed
- Terraform validate: passed
- Terraform AWS plan: security group 분리 후 `73 to add, 0 to change, 0 to destroy`
  계획 생성 및 경계 검토 완료
- Terraform plan에서 공용 module node security group과 `ingress_nodes_ephemeral` 부재,
  general/escape/control-plane 전용 security group 및 제한 규칙 확인
- Terraform AWS apply: VPC, EKS control plane, node group 2개, 관리형 add-on 생성 완료;
  최초 CoreDNS readiness timeout은 strict mode bootstrap policy 누락으로 발생
- CoreDNS 전용 bootstrap NetworkPolicy 적용 후 Pod 2개 `1/1 Running`, add-on `ACTIVE`
- 최초 timeout으로 남은 CoreDNS state taint 해제 완료
- KMS key administrator를 계정 principal로 고정해 Terraform 실행자 변경 drift 제거
- 복구 후 Terraform plan: `No changes`
- 기존 AWS cluster에서 `bootstrap.sh --auto-approve` 재실행 검증: foundation phase를
  안전하게 건너뛰고 node 3대 Ready, CoreDNS 정책 재적용, rollout, add-on `ACTIVE`,
  최종 Terraform `No changes` 확인
- 실제 EKS node 3대 `Ready`: general 2대, escape 1대와 escape `NoSchedule` taint 확인
- 실제 EC2 ENI: general node는 general SG만, escape node는 escape SG만 연결됨을 확인
- EKS Stage 1 overlay Kustomize render: passed
- EKS Stage 1 SSRF intended/shortcut 정적 계약 테스트 9개: passed
- EKS Stage 1 canary Kustomize patch/render 및 digest 치환: passed
- EKS Stage 2 composition/RBAC/API egress 계약 테스트 31개: passed
- Stage 1+2 통합 EKS Kustomize render: passed
- Stage 1~3 통합 EKS Kustomize render: passed
- EKS Stage 3 composition/Prometheus-only API egress 계약 테스트: passed
- Stage 3 pinned image `linux/amd64` availability: verified
- 실제 EKS Stage 3 rollout: passed (세 Pod `1/1 Running`, general node, restart 0)
- 실제 EKS Grafana datasource discovery → broker credential exchange: passed
- 실제 EKS Stage 3 arbitrary reference/direct Prometheus/RBAC/external exposure shortcuts: denied
- 실제 EKS Stage 3 CloudWatch audit namespace-scoped discovery watch `200`: verified
- Stage 1~4 통합 EKS Kustomize render: passed
- Stage 4 분리 server-side EKS overlay render: passed
- EKS Stage 4 controller-only API egress와 Redis digest 계약 포함 대상 테스트 35개: passed
- Stage 4 pinned image `linux/amd64` availability와 EKS 1.36 CRD/admission dry-run: verified
- 실제 EKS Stage 4 핵심 Pod rollout: passed (5개 `1/1 Running`, general node, restart 0)
- 실제 EKS Stage 4 baseline 및 Git-controlled revision: `Synced/Healthy`
- 실제 EKS Stage 4 wrong branch/path push: denied
- 실제 EKS Stage 4 Git commit → Argo reconciliation → synthetic proof: passed
- 실제 EKS Stage 4 controller RBAC 및 privileged/hostPath shortcuts: denied
- 실제 EKS Stage 4 CloudWatch audit controller patch `200`: verified
- Stage 1~5 통합 EKS Kustomize render와 Stage 5 관련 계약 테스트 37개: passed
- 실제 Terraform Stage 5 escape launch-template/node-group update: `0 add, 2 change, 0 destroy`
- 실제 EKS Stage 5 escape node 한 대 `Ready`, label/taint와 containerd 2.2.7: verified
- 실제 EKS Stage 5 Git baseline/desired → Argo reconciliation: `Synced/Healthy`
- 실제 EKS Stage 5 runtime socket 단일 Pod 노출 및 CRI synthetic node proof: passed
- 실제 EKS Stage 5 RBAC/admission shortcut matrix: denied
- 실제 EKS Stage 5 CloudWatch audit Argo patch `200`, Pod exec streaming `101`: verified
- 실제 EKS Stage 5 acceptance 후 Terraform plan: `No changes`
- Stage 1~5 orchestration 신규 계약 테스트: `11 passed`
- orchestration acceptance와 기존 EKS foundation/Stage 1 관련 회귀 테스트: `55 passed`
- Stage 1~5 orchestration WSL Bash syntax: passed
- 실제 Stage 1~5 orchestration 중단 후 재실행: passed
- 실제 동일 deploy 재실행 및 Git revision 불변 idempotency: passed
- 실제 reset과 ephemeral proof/resource 정리: passed
- 실제 reset 후 Stage 1~5 자동 intended path와 대표 shortcut denial: passed
- 자동 acceptance cleanup 후 Git baseline 및 Argo `Synced/Healthy`: passed
- ModelGate 단일-EIP NLB intended/shortcut 계약 테스트 10개와 기존 Terraform 경계
  회귀 테스트를 합친 37개: passed
- ModelGate public access 변경 후 Terraform format/validate와 WSL Bash syntax: passed
- 실제 EIP/NLB plan/apply: `7 add, 0 change, 0 destroy`; EKS/node group 교체 없음
- 실제 AWS Load Balancer Controller Pod Identity rollout과 단일-AZ NLB target health: passed
- 고정 EIP `3.35.2.114`에서 ModelGate `/healthz`와 `/readyz`: passed
- 허용 `/32`에서 공개 endpoint Stage 1 redirect SSRF와 marker-only RCE: passed
- 비허용 공인 IP의 ModelGate NLB 접근: connection timeout으로 denied
- 최초 reset에서 ModelGate가 NLB에 활성화되지 않은 다른 AZ로 재배치되어 target이
  `Target.NotInUse`가 되는 단일-subnet 제약을 확인함
- access manager가 public subnet AZ를 조회해 ModelGate를 같은 zone에 고정하고 NLB target
  `healthy`까지 대기하도록 보완함
- AZ 고정 후 기본 surge rollout이 동일 노드에 ModelGate Pod 두 개를 요구해
  `Insufficient memory`로 중단되는 것을 확인함. 단일 replica access 모드에
  `maxSurge: 0`, `maxUnavailable: 1`을 적용함
- 해당 보완 후 실제 orchestration `reset` 재검증: passed. ModelGate는 public subnet과
  같은 `ap-northeast-2a`의 general node에서 `3/3 Running`, Deployment는
  `NewReplicaSetAvailable`, NLB target은 `healthy`, 고정 EIP `/healthz`는 HTTP 200으로
  복구됨. 단일 replica의 `maxSurge: 0` 구성상 rollout 중 짧은 서비스 중단은 허용됨
- 실제 EKS Stage 2 RBAC positive/negative matrix: passed
- 실제 EKS Stage 2 admission shortcut 7개: denied
- 실제 EKS Stage 2 Job → monitoring-runner → synthetic Flag: passed
- 실제 EKS Stage 2 CloudWatch audit create `201`/denied `422`/Secret get `200`: verified
- 실제 EKS Stage 1 사전 점검: cluster/add-on/node/taint 정상, client dry-run passed
- ModelGate GHCR OCI index anonymous inspect와 digest 확인: passed
- Stage 1 EKS digest/account-portability attack/shortcut 계약 테스트 18개: passed
- Stage 1 OpenAPI discovery intended/shortcut와 실제 system-info API 대상 테스트 16개:
  passed
- system-info discovery 변경 후 WSL Python 3.11 전체 테스트 125개: passed
- proof-bound Stage 1→2 relay API, fixed Job parity, unknown-proof/임의 body shortcut
  대상 테스트 17개: passed
- Stage 1→2 relay 변경 후 WSL Python 3.11 전체 테스트 130개와 acceptance Bash 문법 검사:
  passed
- Stage 2→3 participant relay API, Kustomize render, 네트워크/임의 reference shortcut 및
  orchestration 대상 테스트 49개: passed
- Stage 2→3 relay 변경 후 Stage 3/통합 EKS Kustomize render, WSL Python 3.11 전체 테스트
  137개, compile 및 acceptance/orchestration Bash 문법 검사: passed
- Stage 3→4 ModelGate Git gateway와 participant Argo status 변경 대상 API/manifest/
  orchestration 테스트 50개: passed
- Stage 3→4 변경 후 Windows Python 전체 테스트 145개와 compile: passed
- Stage 4, Stage 5, 통합 EKS Kustomize render 및 acceptance/orchestration WSL Bash 문법:
  passed
- Stage 4→5 proof-bound runtime relay API/manifest/orchestration 대상 테스트 48개: passed
- runtime relay 변경 후 Windows Python 전체 테스트 155개와 relay ConfigMap script compile:
  passed
- Stage 5/통합 EKS Kustomize render, acceptance/orchestration WSL Bash 문법 및 현재 EKS
  API의 Stage 5 overlay server-side dry-run: passed
- 실제 EKS Stage 1 rollout: passed (`3/3 Running`, general node, restart 0)
- 실제 EKS Stage 1 `/healthz`: `{"status":"ok","version":"0.1.0"}`
- 실제 EKS Stage 1 `/readyz`: `{"status":"ready"}`
- 실제 EKS Stage 1 marker-only RCE: validation `succeeded`, fixed proof evidence verified
- RCE 이후 validator 로그: start/success metadata만 기록, credential 또는 proof 내용 없음
- 실제 EKS Stage 1 redirect SSRF: fixed cluster-local target에서 synthetic canary proof 확인
- canary access log: ModelGate Pod IP에서 발생한 `GET /canary` 200 확인
- 비인가 Pod의 canary FQDN 직접 접근: DNS resolution timeout으로 denied
- 비인가 Pod의 canary ClusterIP 직접 접근: explicit egress 허용 후에도 ingress에서 denied
- Stage 5 EKS runtime-client local image build and runtime checks: passed
- GHCR runtime-client anonymous digest pull, `crictl version v1.36.0`, 기본 socket 설정: passed
- digest-pinned Stage 5 Kustomize render와 attack/shortcut 계약 테스트 15개: passed
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
- PR #2 checks: test/container/runtime-client succeeded
- main merge commit `a2de860` GitHub Actions run #10: succeeded

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
| Terraform/EKS | 구현 중 | Stage 1~5 AWS acceptance 완료, clean 재배포·자동화 필요 |

## 다음 작업: Stage 1~5 clean 재배포와 orchestration

Terraform foundation의 첫 AWS apply, node/ENI 경계, strict NetworkPolicy와 CoreDNS 복구,
최종 no-drift까지 확인했다. `bootstrap.sh`는 clean deployment에서 CoreDNS add-on보다
bootstrap NetworkPolicy를 먼저 적용하도록 두 단계로 구성했고, 현재 cluster에서 중단 후
재실행 경로를 검증했다. Stage 1~5 AWS acceptance와 최종 Terraform no-drift를 완료했다.
CRD server-side apply, Stage overlay 적용, synthetic Gitea baseline, 제한된 reset을 계정
중립적인 orchestration으로 묶고 현재 개인 계정 EKS에서 deploy 재실행, idempotency와
reset을 검증했다. reset 이후 Stage 1~5 전체 attack path를 실행하는 `accept` 모드와 실제
EKS 재실행까지 검증했다. 다음 작업은 개인 계정의 destroy 후 clean second apply와 이후
팀 계정 배포를 검증하는 것이다. Stage 6 CSI/IAM은 별도 AWS threat model과 tag boundary를
확정한 뒤 추가한다.

도메인 없는 팀 내부 초기 진입점은 별도 `deploy/eks-access` 계층으로 설계했다. 이 계층은
첫 public subnet 하나, Terraform 관리 EIP 하나, ModelGate 전용 internet-facing NLB만
사용한다. AWS Load Balancer Controller는 EKS Pod Identity를 사용하며 참가자 공인 IP
`/32`와 NLB health-check subnet 이외의 ModelGate ingress를 허용하지 않는다. HTTP는
synthetic lab 데이터만 전달하는 단기 실습 예외이며, 도메인 확보 후 HTTPS로 교체한다.

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

결정 전 기본 방향:

- Stage 2 admission은 외부 dependency 없는 ValidatingAdmissionPolicy로 확정했다.
- 로컬 Stage 2 기준은 kind v0.33.0 / Kubernetes v1.37.0으로 검증했다.
- Stage 2 Job은 digest 고정 공식 `registry.k8s.io/kubectl:v1.37.0`을 사용한다.
- Stage 2 개발 Flag는 placeholder를 사용하고 배포 시 무작위 발급 구조로 교체한다.
- Stage 4는 Argo CD 3.5.3과 Gitea 1.27.3-rootless를 digest로 고정한다.
- Stage 4 read wildcard는 namespaced dynamic cache의 read-only API에만 사용한다.
- Stage 5 로컬 기준은 kind escape worker와 containerd CRI 주입 경로로 확정했다.
- kind와 EKS는 `images/runtime-client`가 만드는 reviewed `crictl` 이미지를 동일한
  게시 OCI digest로 사용하며 host binary mount는 사용하지 않는다.

## 현재 미완료 사항

- Terraform VPC/EKS와 general/escape managed node group의 첫 AWS apply는 완료했지만,
  destroy 후 clean second apply 반복 검증은 아직 수행하지 않았다.
- 원격 state/bootstrap, ECR, DNS/TLS는 아직 구현하지 않았다. 도메인 없는 ModelGate
  단일-EIP HTTP NLB의 Terraform/Kubernetes 구성, 실제 AWS 배포, 허용·비허용 공인 IP
  검증은 완료했다. 선-NLB 삭제와 Terraform EIP 반환 절차는 전체 실습 철거 때 실제로
  검증한다. 첫 개인 계정 검증은 계정별 local state를 사용한다.
- Stage 6 CSI/AWS Storage/IAM pivot과 AWS tag/IAM policy boundary는 아직 설계·구현하지
  않았다.
- Stage 1부터 Stage 5까지를 한 명령으로 배포하고 전체 체인을 연속 실행하는 acceptance
  harness의 배포/reset/status와 전체 intended path `accept` 모드를 구현했고 실제 AWS
  검증을 완료했다. 현재 Stage 2~5는 Stage별 kind smoke도 유지한다.
- Stage별 base Kustomization은 서로 독립적이며 통합 EKS overlay는 현재 Stage 1~5를
  조합한다. Stage 4/5는 vendored CRD 때문에 CRD server-side apply와 나머지 overlay apply를
  분리해야 한다.
- Stage 1 application deployment와 Stage 2~5 overlay의 기존 cluster 연결 검증은 완료했지만,
  destroy 후 새 cluster에서 수행하는 clean end-to-end smoke는 아직 실행하지 않았다.
- 배포별 무작위 Flag 발급, hash 기반 채점, reset/reissue 서비스는 없다. 현재 proof와
  credential은 local lab용 placeholder/synthetic 값이다.
- 현재 `poc/rce_marker.py`의 AWS smoke는 운영자 로컬 Python 3.11 격리 환경에서 실행한다.
  팀 계정 참가자 배포 전에는 digest-pinned PoC runner 이미지 또는 사전 생성된 안전한
  payload/curl 흐름을 제공해 참가자 로컬 Python 의존성과 `kubectl exec` 우회를 제거한다.
- Stage 3→4는 ModelGate의 기존 EIP/Service에서 고정 Git smart-HTTP gateway와 read-only
  Argo status API로 이어지며, Stage 4→5도 operator `kubectl exec` 없이 proof-bound runtime
  relay의 단일 합성 CRI 작업으로 연결했다. 다음 AWS 검증은 변경 이미지를 게시한 뒤 현재
  EKS에 overlay를 적용해 공개 EIP에서 Stage 1→5 participant flow를 다시 실행하는 것이다.
- Stage 2~5 checkpoint는 PR #1, Terraform foundation과 runtime-client image는 PR #2,
  Stage 5 runtime-client digest pin은 PR #3, Stage 1~5 EKS composition은 PR #4로
  `main`에 병합되었고 CI가 통과했다. 현재 branch는 clean 재배포 orchestration 작업만
  포함한다.

## 알려진 제약과 주의사항

- 현재 로컬 검증에서 해결되지 않은 실패는 없다. Python 87개, Stage 2~5 kind
  acceptance, Compose/Kustomize/compile 검사가 통과했다.
- Stage 5 namespace는 containerd socket hostPath 때문에 Pod Security `privileged` level을
  사용한다. 실제 container는 privileged가 아니지만 runtime socket 자체는 사실상 node
  root에 준하는 권한이므로 공유/운영 cluster에 배포하면 안 된다.
- Stage 5 smoke는 제한된 로컬 메모리에서 proof를 실행하기 전에 일부 Argo/Gitea
  component를 scale-down한다. 이는 AWS 운영 topology가 아니라 acceptance 최적화다.
- Stage 5 runtime-client에는 `/run/stage5/containerd.sock` 기본 config가 패키징되어
  있다. 실제 EKS에서 공개 GHCR pull과 CRI 경로는 Stage 1~5 배포 조합 때 다시 검증한다.
- kind v0.33.0/Kubernetes v1.37.0 기준으로 검증했다. Terraform에서는 실제 EKS 지원
  version을 선택하고 ValidatingAdmissionPolicy/CEL 동작을 다시 acceptance해야 한다.
- Stage 3 broker, Git credential, 모든 Flag는 합성 값이다. 실제 AWS credential이나
  production resource로 교체하지 않는다.
- Stage 4 vendor CRD/install manifest가 저장소에 포함되어 변경량이 크다. checkpoint
  검토 시 upstream version과 digest를 별도로 확인한다.
- 현재 AWS CLI는 개인 계정의 임시 bootstrap IAM 사용자 profile을 사용하고, Kubernetes
  접근은 별도 operator role과 Access Entry를 사용한다. bootstrap 사용자의
  AdministratorAccess는 개인 계정 검증 후 축소/제거하며 팀 계정에서는 IAM Identity
  Center 또는 임시 Terraform deployment role을 사용한다.
- Terraform plan에는 EKS control plane, EC2 worker 3대, NAT gateway, public IPv4,
  CloudWatch 로그처럼 비용이 발생하는 리소스가 포함될 예정이므로 apply 전 검토한다.
- 최초 생성한 `personal.tfplan`은 공용 node security group 규칙을 포함하므로 절대 apply하지
  않는다. 코드 변경 후 같은 파일명으로 새 plan을 생성하기 전까지 폐기된 계획으로 본다.
- 첫 `personal-isolated.tfplan` 재계획은 `Invalid count argument`로 실패했으므로 출력 파일이
  존재하더라도 유효한 승인 대상이 아니다. EKS module-level `depends_on` 제거 후 새 이름으로
  plan을 다시 생성한다.
- VPC CNI strict mode의 clean apply는 `infra/terraform/bootstrap.sh`로 실행해야 한다.
  Terraform 단독 one-shot apply는 CoreDNS 정책보다 add-on을 먼저 만들 수 있어 사용하지
  않는다. 기존 cluster에서 resume 경로는 검증했지만 destroy 후 완전한 clean bootstrap과
  second apply 반복 검증은 아직 수행하지 않았다.

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
