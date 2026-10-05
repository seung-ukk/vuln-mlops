# vuln-mlops 진행 보고서

작성일: 2026-10-05 
범위: 개인 AWS 계정의 격리된 EKS 실습 환경, Stage 1~5

## 요약

공개 ModelGate 진입점에서 시작해 SSRF, marker-only RCE, 제한된 Kubernetes RBAC,
모니터링 정보, GitOps 변경, containerd runtime socket의 합성 노드 proof까지 이어지는
Stage 1~5 경로를 구현했다. 
개인 EKS의 공개 EIP에서 자동 수락 검증이 전체 통과했고,
사용자가 운영자 `kubectl` 없이 공개 API와 제한된 Git gateway로 직접 실행한 PoC도
Stage 5 합성 proof까지 통과했다.

이는 **현재 구현된 참가자 경로가 동작한다**는 증거다. 임의 노드 명령권 획득,
AWS IAM identity 접근, CSI/EBS Final Flag 획득을 검증했다는 뜻은 아니다.
원래 계획의 Stage 6은 아직 구현되지 않았다.

## 구현 및 검증 상태

| 단계 | 구현된 경계 이동 | 개인 EKS 증거 |
| --- | --- | --- |
| Stage 1A | 공개 webhook redirect → 내부 synthetic canary | 수동 PoC의 `MODELGATE_INTERNAL_SSRF_PROOF` |
| Stage 1B | model bundle → validator 역직렬화 marker | 수동 PoC의 validation `succeeded`, proof UUID 발급 |
| Stage 2 | proof-bound ModelGate relay → 고정 `monitoring-runner` Job | 수동 PoC의 Job `succeeded=1`, 합성 Flag |
| Stage 3 | monitoring relay → Grafana datasource·고정 metric·credential reference | 수동 PoC의 reference 교환과 합성 Git credential |
| Stage 4 | 제한된 Git push → Argo CD reconciliation | 수동 commit `d94c32c167f3a2fd5b10759cb25a198ba3af98f7`, `Synced/Healthy` |
| Stage 5 | proof-bound runtime relay → containerd CRI 작업 → 노드 전용 합성 proof | 수동 응답 `success=true`, `FLAG{stage_5_node_placeholder}` |
| Stage 6 | CSI/AWS Storage/IAM → Final Flag | 미설계·미구현 |

자동 수락 검증은 공개 EIP를 통해 Stage 1~5 intended path와 대표 shortcut denial을
완료했고, 종료 후 Git baseline을 복원해 Argo CD `Synced/Healthy`를 확인했다.
자동 스크립트의 운영자 `kubectl`은 준비·우회 검사·복원에 사용했다. 공격 경로의
HTTP/Git 요청은 공개 ModelGate endpoint를 사용했다.

수동 참가자 PoC에서는 `/api/system/info`의 canary 좌표, RCE proof의 `next`,
Stage 2 log의 `next`, Stage 3의 `credential_ref`와 `git_gateway`, Stage 4 상태의
`runtime_relay`를 차례로 사용했다. Git push 직후 Argo 상태 API가 잠시 이전
revision을 반환했으나, 재조회에서 새 revision과 Stage 5 경로가 확인됐다.
수동 Stage 5 proof 응답은 첨부된 터미널 기록으로 확인했다. 이후 운영자 `reset`으로
Git baseline `7f8fcbff78d6d99d5c3283b6b4df2fd2ffff57df`가 Argo
`Synced/Healthy`로 복원되고 Stage 2 Job 삭제 및 ModelGate/runtime-builder 재시작이
완료된 것도 확인했다.


## 남은 부분과 주장 범위

- Stage 5는 고정된 CRI 동작으로 노드 전용 합성 파일을 읽는다. Runtime socket의
  잠재 권한은 높지만, 참가자에게 임의 노드 명령권을 제공하거나 노드 IAM 역할을
  실제 호출한 결과는 없다. 따라서 현재 결과를 “완전한 노드 장악·AWS IAM 탈취”로
  표현하지 않는다.
- Stage 4의 proof annotation 값과 변경 필드는 수동 검증 가이드에서 힌트로 제공했다.
  모든 단서를 처음 보는 팀원이 스스로 찾아내는 블라인드 실습은 아직 검증하지 않았다.
- Stage 6의 CSI/EBS/EFS resource, Final Flag, 태그 기반 IAM 경계는 없다.
- 개인 계정 EKS의 기존 cluster 재배포는 검증했지만 destroy 후 clean second apply와
  팀 계정 이전은 검증하지 않았다.
- Falco와 Kyverno는 설치하지 않았다. 현재 관측 자료는 EKS audit, CloudTrail,
  애플리케이션/수락 검증 결과에 한정된다.
- Flag와 Git credential은 synthetic placeholder다. 배포별 무작위 Flag, hash 채점,
  참가자 전용 PoC runner, 도메인/TLS는 아직 없다.
- 현재 참가자 진입점은 허용 공인 IP `/32`만 접근 가능한 HTTP NLB다. 실습 종료 시
  공개 접근·클러스터 비용 관리와 자원 철거가 필요하다.

##  결정할 범위

**선택 A — 현재 Stage 1~5를 프로젝트 결과로 마무리:** 실제 EKS와 참가자 PoC의
연결 증거를 제시한다. 문서에서 Stage 5의 결과를 “runtime socket을 통한 노드 전용
합성 proof”로 정확히 표현하고, Stage 6은 후속 연구로 둔다. 가장 적은 추가 작업이다.

**선택 B — 작은 Stage 5 최종 확장:** 고정 CRI 작업의 실습 전용 노드 marker 쓰기와,
노드 문맥에서 `sts:GetCallerIdentity`를 호출해 계정·역할 ARN만 반환하는 방법을
짧게 검증한다. 실제 자격 증명 값은 반환하지 않는다. 현재 IMDSv2 hop limit 1과
Pod Identity 경계를 유지하면서 단순하게 구현될 때만 진행한다. 성공해도 증명하는
범위는 “노드 IAM identity 도달”이며 CSI/Final Flag 획득이 아니다.

**선택 C — 원래 Stage 6까지 구현:** CSI 권한, 태그가 지정된 EBS/EFS, Final Flag
초기화, AWS IAM 허용·거부, 반복 배포/삭제를 새로 설계·검증해야 한다. 현재 완료한
Stage 1~5와 별도의 작업량이다.

현재 프로젝트 목표가 팀 시연과 공격 흐름 이해라면 **선택 A를 기준으로 보고하고,
시간이 남을 때만 선택 B의 가능성을 조사**하는 것이 적절하다. 선택 B를 시도하더라도
일반 Pod의 직접 접근 거부와 relay의 고정 입력 경계는 최소한으로 확인해야 한다.

## 요약

> 개인 EKS의 공개 ModelGate에서 시작한 Stage 1~5 공격 체인을 자동 수락 검증과
> 참가자 수동 PoC로 재현했으며, 마지막 단계는 containerd runtime socket으로
> 노드 전용 합성 proof에 도달하는 범위까지 검증했습니다. 실제 노드 IAM·CSI·AWS
> 저장소 접근과 블루팀 정책 적용은 아직 수행하지 않았습니다.

## 관련 자료

- [랩 계획](LAB_PLAN.md), [Stage 계약](STAGE_CONTRACTS.md), [상세 상태](STATUS.md)
- [수동 참가자 PoC](PARTICIPANT_POC.md)
- [PR #7: ModelGate image digest 갱신](https://github.com/seung-ukk/vuln-mlops/pull/7)
- [AWS EKS 노드 IAM 역할](https://docs.aws.amazon.com/eks/latest/userguide/create-node-role.html)
- [AWS IMDS 컨테이너 hop limit 설명](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html)
