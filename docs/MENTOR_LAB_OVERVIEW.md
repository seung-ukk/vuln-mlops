# ModelGate 랩 개요 — 멘토·운영진용

> 참가자에게 배포하지 않는다. 현재 경로는 2026-10-08의 셸 중심 프로필이다.
> 2026-10-07 SSRF·고정 Job·S3 Flag 프로필의 원문은
> [과거 개요](archive/MENTOR_LAB_OVERVIEW_2026-10-07.md)에 보관했다.
> 배포와 초기화 상태는 [STATUS.md](STATUS.md) 상단을 우선한다.

## 학습 목표

```text
공개 ModelGate 모델 검증
  → 취약한 MLflow 역직렬화 → validator Pod의 UID 10001 셸
  → 내부 Grafana/Prometheus와 운영 로그 → 경로 제한 Git credential
  → runtime-builder Deployment 변경 → Argo CD 동기화
  → 고정 hostPath의 maintenance task 변경 → host systemd root 실행
  → 노드 instance profile로 전용 EC2의 proof 태그 쓰기
```

핵심은 Git이 신뢰된 배포 경로를 통해 Pod 사양을 바꾸고, 비루트 UID와 읽기
전용으로 시작한 hostPath가 쓰기 가능해질 때 호스트의 고정 작업에 미치는
영향이다. 이는 범용 컨테이너 탈출이나 대화형 노드 셸 획득을 증명하는
문제가 아니다. 호스트 systemd가 바뀐 파일을 root로 실행하는 구성까지
포함한 실습이다.

## 실제 검증과 한계

- 멘토용 역직렬화 payload는 전용 공격자 EC2의 사설 IP로 셸을 연결했다.
  정상 statsmodels 모델과 payload는 모두 공개 API에서 업로드 201·등록
  201·검증 `succeeded`였다. RCE 증거는 HTTP 상태가 아니라 연결과 UID다.
- validator ServiceAccount로 내부 Application, 관측·runtime Pod 목록과
  로그만 조회한다. Git token은 배포 때 생성하며 운영 로그에만 남는다.
  Gitea 계정은 `lab-runtime`의 `runtime-builder/`에만 쓸 수 있다.
- 참가자 Git commit `ff4d3bf9261fecf6f52f321f7274aea2b5dc0203`와 Argo
  revision이 일치했고 Application은 `Synced/Healthy`였다. 호스트 증거에는
  root/UID 0, 전용 노드 hostname과 node assumed-role ARN이 기록됐다.
- 독립 AWS 확인에서 전용 EC2 `i-02ca356d1262414eb`의
  `lab.vuln-mlops/proof=lab-20261008test01` 및 같은 대상·값을 쓴 노드 역할의
  CloudTrail `CreateTags` 성공 이벤트를 확인했다. 호스트 systemd journal은
  이 회차에서 별도로 조회하지 않았다.
- 최초 payload와 최종 Deployment YAML에는 멘토용 생성기를 사용했다.
  완전한 블라인드 payload 작성·단서 발견성은 아직 검증되지 않았다.

## 운영 경계

- 공격자 EC2는 같은 VPC에서 연결을 받을 뿐 IAM 역할과 운영자 kubeconfig가
  없다. 팀은 공유 Git 브랜치와 전용 노드를 순서대로 사용한다.
- runtime-builder의 이미지, ServiceAccount, nodeSelector, hostPath 원본,
  evidence의 읽기 전용 mount는 고정이다. 참가자 Git 변경은 기존
  Deployment의 제한된 필드에만 적용된다.
- Pod 로그만으로 AWS API 성공을 판정하지 않는다. 운영자가 Git/Argo
  revision, 노드 문맥, 실제 EC2 태그와 CloudTrail 호출자를 대조한다.
- 현재 공격 상태가 남아 있다. 다음 독립 참가자 실습 전에 Git baseline
  복구와 공격 노드 교체가 필요하다. 이전 프로필의
  `orchestrate.sh reset --stage5-iam`은 사용하지 않는다.

현재 참가자에게 줄 문서는 [시작 안내](PARTICIPANT_START_GUIDE.md)이며,
운영 절차와 멘토용 명령은 [현재 PoC](MENTOR_STAGE_POC.md)에 있다.
