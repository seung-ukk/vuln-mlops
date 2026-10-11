# 참가자 회차 종료 후 초기화

운영자 WSL에서 참가자 증거를 수집한 뒤 실행한다. AWS CLI는 실습 계정
`707605822656`을, `kubectl`은 `vuln-mlops-personal-lab`을 가리켜야 한다.
공격자 EC2의 **사설 IP**, 예시 리스너 포트, 현재 검토된 ModelGate 이미지 digest를
인자로 전달한다. 두 번째 인자는 기존 스크립트 호출 형식을 유지하기 위한 값이며,
실제 validator→전용 EC2 정책은 TCP 전체 포트를 허용한다.

```bash
bash deploy/participant-chain/reset-after-participant.sh \
  10.42.143.106 4444 \
  ghcr.io/seung-ukk/vuln-mlops@sha256:e20da314cfcd7bfa8759e919156f544a43eb37b7ce143604ea1663d9d1efded4
```

스크립트는 먼저 ModelGate를 재시작해 기존 validator 셸을 종료하고,
`setup.sh`로 Git 관리 Deployment를 비루트·읽기 전용 기준 상태로
돌리고 Argo 동기화를 기다린다. 이어서 실습 전용 Gitea Pod의
`emptyDir` 저장소를 재생성해 이전 참가자 Git 이력을 제거하고 Git 암호를
새로 발급한다. 두 번째 `setup.sh` 실행은 새 저장소에 기준 commit을 만들고
Argo를 다시 동기화한다. 마지막으로 `operations-log`를 재시작해 이전
credential을 사용하던 Pod를 교체한다.

그 후 전용 escape 노드 하나를 drain하고 Auto Scaling Group에 교체를
요청한다. 이전 EC2의 종료, 이전 Kubernetes 노드의 삭제, 대체 노드와
runtime-builder의 Ready, 새 EC2의 증명 태그 부재, Argo의 기준 revision,
공개 `/readyz`를 확인한 뒤 완료 메시지를 출력한다. 중간에 실패하면
오류 지점에서 멈춘다. 노드 교체 중 실패했다면 EC2와 Kubernetes 노드가
안정된 뒤 상태를 확인하고 다시 실행한다.

이 절차는 실습 리소스를 복원한다. CloudTrail 기록과 이미 외부에 저장한
증적은 삭제하지 않는다. 새 노드의 호스트 task 내용 및 evidence 파일
부재는 이 스크립트에서 직접 조회하지 않는다. 별도로 운영하는 공격자 EC2의
개인 파일, 셸 히스토리, 리스너 프로세스는 이 스크립트의 정리 대상이 아니다.
