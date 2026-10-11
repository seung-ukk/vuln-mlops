# vuln-mlops 랩 소개서 — 멘토·운영진용

> 운영진 자료. 참가자에게 배포하면 단서와 합성 Flag가 공개된다. 2026-10-07 개인 EKS에서 검증한 hostPath capstone을 기준으로 작성했다.

## 한눈에 보는 랩

외부에 공개된 ModelGate에서 출발해 Kubernetes와 GitOps의 신뢰 경계를 순서대로 살펴보는 실습이다. Stage 4의 Git 변경이 전용 escape worker의 hostPath 경계를 거쳐 실제 호스트 작업과 노드 IAM 사용으로 이어진다.

```text
공개 ModelGate
  → 1-A SSRF / 1-B 모델 검증 RCE
  → 2 고정 RBAC Job
  → 3 모니터링 정보와 제한된 Git credential
  → 4 Git 변경과 Argo CD 동기화
  → 5 비루트·읽기 전용 hostPath 경계 → 호스트 maintenance task 변경
      → escape worker에서 host root 실행 → 노드 역할로 실습용 S3 단일 객체 조회
```

참가자는 허용된 공인 IP에서 공개 HTTP EIP와 그 안의 제한된 Git gateway만 사용한다. `kubectl`, AWS 계정, 클러스터 내부 주소는 운영·진단·초기화에만 필요하다. 운영자는 개인 계정의 전용 EKS를 사용하며, 참가자 진입은 NLB, Service source ranges, NetworkPolicy의 `/32` 허용 목록으로 제한된다. EKS API 접근은 참가자 경로가 아니다.

### 이 랩에서 실제로 증명하는 것

| 단계 | 넘어가는 경계 | 참가자가 따라가는 단서 | 성공 증거 |
| --- | --- | --- | --- |
| 1-A | 공개 URL 검사 → 클러스터 내부 서비스 | `/docs`, `/api/system/info`의 canary 좌표와 webhook API | `MODELGATE_INTERNAL_SSRF_PROOF` |
| 1-B | 모델 데이터 → validator 프로세스 | artifact·model 등록 API와 검증 흐름 | `validator marker observed`, RCE proof UUID |
| 2 | 낮은 권한의 `modelgate` SA → Job의 `monitoring-runner` 문맥 | proof 응답의 `next`, `/self-rules` | `FLAG{stage_2_rbac_chaining_placeholder}` |
| 3 | 모니터링 조회 → 실습용 Git 권한 | datasource → 고정 topology query의 `credential_ref` | `FLAG{stage_3_monitoring_trust_placeholder}`, 제한된 Git credential |
| 4 | 제한된 Git 쓰기 → Argo CD가 관리하는 Deployment | credential 응답의 branch/path/gateway, Gitea README와 baseline YAML | 참가자 commit과 동일한 revision의 `Synced/Healthy`, `FLAG{stage_4_gitops_placeholder}` |
| 5 | baseline Pod의 hostPath 보호 → 실제 escape worker 호스트 작업 → 노드 IAM | baseline UID/GID·mount, maintenance task와 결과 endpoint | 호스트 실행 Falco 경보, 예상 계정·노드 assumed-role ARN·`FLAG{stage_5_iam_placeholder}` |

### 문제의 연결과 경계

**1-A/1-B — 공개 앱의 첫 발판.** ModelGate는 `api`, loopback MLflow registry, validator를 한 Pod에 둔다. 공개 system-info는 합성 canary의 service·namespace·port·path를 알려 준다. webhook 검사는 첫 URL을 거쳐 내부 canary로 리다이렉트되는 SSRF를 관찰한다. 모델 업로드와 검증은 의도적으로 고정된 취약 MLflow/statsmodels 프로필에서 marker만 남긴다. 응답은 임의 명령 출력이나 파일 내용을 반환하지 않는다.

**1-B→2 — 실행 증거를 권한 조사로 연결.** RCE proof UUID가 있어야 foothold API가 열린다. `/self-rules`에 Job 생성·조회와 Pod 로그 읽기 권한이 나타나며, 참가자는 고정 이름·형태의 Job만 제출한다. Job의 ServiceAccount가 합성 Secret을 읽고 로그에 인코딩된 증거를 남긴다. 일반적인 임의 Job 생성 권한을 제공하는 문제는 아니다.

**2→3 — 작업 완료가 모니터링 세션의 근거.** 완료된 Job을 확인한 뒤 datasource 목록과 정해진 topology metric을 조회한다. metric의 `credential_ref`를 정확히 교환하면 실습용 Git credential, `stage4-lab` branch와 `runtime-builder/` 경로가 나온다. Grafana·Prometheus 자체를 인터넷에 공개하지 않는다.

**3→4 — Git이 실제 워크로드를 바꾼다.** 참가자는 ModelGate의 proof-bound Git smart-HTTP gateway로 Gitea의 지정 저장소·branch·경로만 수정한다. `runtime-builder/README.md`와 baseline YAML이 전용 노드, 비루트 UID/GID, 읽기 전용 hostPath를 보여 준다. 참가자는 허용된 Pod 사양을 변경하고 Argo CD가 그 commit을 동기화하도록 한다. 참가자 요청은 `Synced/Healthy`뿐 아니라 **push한 revision과 일치**해야 Stage 4를 증명한다. Stage 4 Flag annotation만으로 최종 성공을 인정하지 않는다.

**5 — hostPath에서 노드 IAM까지.** baseline builder는 전용 escape worker에서 UID/GID 10001로 실행되고 maintenance hostPath를 읽기 전용으로 마운트한다. 비루트 권한과 mount의 읽기 전용 설정이 각각 쓰기를 막는 것을 검증했다. 허용된 Git 변경으로 UID/GID, command, maintenance mount를 바꾸면 Pod가 호스트의 고정 `task.sh`를 수정한다. systemd path unit이 이 변경을 감지해 호스트 root 문맥으로 실행한다. 호스트 작업은 노드 instance profile의 `vuln-mlops-escape-node` 역할로 합성 S3 객체 `proof/final-flag.txt` 하나를 조회하고 별도 `node-evidence` 경로에 제한된 결과만 쓴다. Pod의 evidence mount는 읽기 전용이다. 공개 API는 계정·assumed-role ARN·합성 Flag만 반환한다.

## 운영진이 알아둘 실습 범위

- 모든 Flag는 synthetic placeholder다. 실계정 자격증명이나 운영 데이터는 문제에 넣지 않는다. S3 객체 본문은 Terraform state에 저장하지 않는다.
- builder ServiceAccount에는 Pod IRSA나 Pod Identity를 부여하지 않았고 Kubernetes 자동 토큰 mount도 껐다. 노드 역할은 실습 버킷의 정확한 한 객체에 대한 `s3:GetObject`만 추가로 허용한다.
- admission, NetworkPolicy, 전용 노드, Git gateway가 namespace·resource·image·경로 경계를 유지한다. Pod의 직접 IMDS 접근과 evidence 쓰기는 거부됐다. 운영자 진단에서 비루트+쓰기 mount, root+읽기 전용 mount도 각각 거부됐다.
- 개인 EKS의 공개 참가자 경로에서 Stage 1~5가 통과했다. Falco의 호스트 maintenance 이벤트가 CloudWatch에 도착했다. S3 CloudTrail 객체 데이터 이벤트는 켜지 않아 독립 AWS GetObject 이벤트를 주장하지 않는다.
- 풀이 후 Git baseline을 `ff66336f6c1f633194c31306a98323a5d400a83d`로 복원하고 공격을 실행한 escape EC2 인스턴스를 교체했다. 새 노드의 기본 task와 결과 파일 부재, builder/Falco/CloudWatch Ready, 이전 foothold의 HTTP 404를 확인했다. 이전 `reset --stage5-iam`은 이 프로필에 맞지 않는다.
- 팀원의 완전한 블라인드 단서 발견성, clean destroy 후 두 번째 apply, 팀 계정 이전은 검증하지 않았다. Stage 6 CSI/EBS/EFS와 Kyverno 차단은 구현하지 않았다.

## 관련 문서

- [운영진 PoC 답안지](MENTOR_STAGE_POC_2026-10-07.md)
- [Stage 계약](../STAGE_CONTRACTS.md)
- [현재 상태와 이력](../STATUS.md)
- [hostPath 전환 및 복구 기록](../HOSTPATH_CAPSTONE_MIGRATION.md)
