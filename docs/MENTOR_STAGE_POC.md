# ModelGate 현재 경로 PoC — 멘토·운영진용

> 참가자에게 배포하지 않는다. 2026-10-07 Stage 1~5 및 5-A/5-B 원문은
> [과거 답안지](archive/MENTOR_STAGE_POC_2026-10-07.md)에 보관했다.
> 실제 배포·복구 상태는 [STATUS.md](STATUS.md) 상단을 우선한다.

## 1. 공개 모델 검증과 셸

운영자는 EKS context, 허용 공인 IP, 공개 `/readyz` 및 같은 VPC의 전용
공격자 EC2를 확인한다. EC2는 IAM 역할 없이 사설 IP에서 지정 포트를
수신한다. 이 포트와 EC2 SSH 정보는 팀에 별도로 전달한다.

정상 요청 비교에는 [`poc/benign_validation.py`](../poc/benign_validation.py),
역직렬화 기능 확인에는 [`poc/rce_reverse_shell.py`](../poc/rce_reverse_shell.py)를
사용한다. 후자는 멘토 전용이다. 둘 다 ZIP 업로드 201, 모델 등록 201,
검증 Job `succeeded`가 나올 수 있다. exploit의 차이는 validator가 시작한
역방향 연결이다. 셸에서 `id`, `hostname`, `pwd`를 확인하고 UID 10001 및
ModelGate Pod 문맥을 기록한다. 공개 HTTP만으로 RCE를 주장하지 않는다.

## 2. 셸의 내부 단서와 권한

셸 작업 디렉터리 `/opt/modelgate`에서 `VALIDATOR_OPERATIONS.txt`와
`ops/monitoring-history.txt`를 읽는다. 배포 이미지에는 `kubectl`과 토큰
파일을 참조하는 in-cluster kubeconfig가 있으며 운영자 kubeconfig는 없다.
다음 조회로 제한 권한을 확인할 수 있다.

```sh
kubectl auth can-i list pods -n observability-lab
kubectl auth can-i get pods/log -n observability-lab
kubectl -n delivery-lab get application runtime-builder
kubectl -n runtime-lab get pods -l app=runtime-builder
```

Grafana는 내부 `grafana.observability-lab.svc:3000`이다. `/api/datasources`에서
Operations Prometheus UID를 찾고 운영 기록의 `delivery_sync_info`를
UID 프록시로 질의한다. 지표의 `log_namespace`와 `log_selector`가 가리키는
운영 Pod의 로그를 `kubectl logs`로 조회한다. 첫 줄의 `remote`, `branch`,
`path`, `username`, 배포별 `token`을 확인하되 token을 보고서나 터미널
공유 출력에 넣지 않는다.

## 3. Git 변경과 Argo 동기화

Git credential은 내부 Gitea의 `lab-runtime` 브랜치와
`runtime-builder/` 디렉터리에 한정된다. 셸에서 clone해
`runtime-builder/README.md`와 `deployment.yaml`을 읽는다. TTY가 없는
셸에서는 Git 비밀번호 프롬프트가 불편하므로 `GIT_ASKPASS` 또는 일회성
HTTP Basic 헤더를 사용한다. 명령 출력이나 Git URL에 token을 남기지 않는다.

정상 참가자 풀이에서는 YAML을 직접 작성해야 한다. 빠른 기능 확인만
필요할 때는 멘토 전용 [`deploy/participant_hostpath.py`](../deploy/participant_hostpath.py)를
사용할 수 있다. 이 경우 **payload 작성의 블라인드 발견성은 검증되지
않았다**고 기록한다. Git 변경은 기존 Deployment의 UID/GID,
maintenance mount의 `readOnly`, shell `command/args`에 집중하고 이미지,
ServiceAccount, 노드 선택과 evidence mount를 유지한다. 앱을 계속 띄워
readiness가 유지되게 한다.

참가자 셸의 credential로 commit/push한 SHA를 `kubectl -n delivery-lab get
application runtime-builder -o yaml`의 sync revision과 대조한다. 새
runtime-builder Pod가 전용 노드에서 Ready여야 한다. 운영자 `kubectl`의
출력은 참가자의 단서 발견에 사용하지 않는다.

## 4. 호스트와 AWS 증거

참가자 권한으로 `runtime-lab` Pod 로그를 읽으면 별도 읽기 전용
`/node-evidence`에서 전달된 host UID, hostname, node-role ARN 및 marker를
볼 수 있다. 이 로그의 문구만으로 실제 AWS API 성공을 인정하지 않는다.
운영자는 다음 항목을 독립 대조한다.

1. 해당 Git commit과 Argo revision의 완전한 SHA 일치.
2. 호스트 root 문맥과 해당 전용 노드의 instance ID 일치.
3. EC2 실제 태그 `lab.vuln-mlops/proof=lab-<참가자 값>`.
4. CloudTrail `CreateTags` 관리 이벤트의 대상 instance ID, tag key/value,
   node assumed-role 호출자 및 오류 없음. 필요하면 Falco와 host journal도
   확인한다.

2026-10-08 기능 검증에서는 commit `ff4d3bf9261fecf6f52f321f7274aea2b5dc0203`,
노드 `i-02ca356d1262414eb`, marker `lab-20261008test01`이 일치했다.
CloudTrail 오류 코드는 null이었다. systemd journal은 별도 확인하지 않았다.

## 5. 다음 참가자 전 초기화

공유 `lab-runtime` 브랜치의 baseline Deployment를 다시 commit/push하고
Argo `Synced/Healthy`와 정확한 새 revision을 확인한다. 공격이 실행된
escape EC2는 drain·종료해 새 노드로 교체하고 기본 maintenance task와
proof 결과 부재를 확인한다. ModelGate의 이전 셸 세션도 종료한다. 현재
프로필 전용 reset 자동화는 아직 없으므로 이전
`orchestrate.sh reset --stage5-iam`을 실행하지 않는다.
