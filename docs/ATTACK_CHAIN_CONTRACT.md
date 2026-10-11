# 참가자 침투 체인 계약 초안

2026-10-08 체인 계약. 실제 배포와 검증 상태는 `STATUS.md` 상단을 따른다.

## 학습 목표

참가자는 취약한 모델 검증에서 얻은 validator 실행 권한으로 내부 환경을 조사한다.
운영 모니터링에 남은 제한된 Git 쓰기 권한을 발견하고, Argo CD가 신뢰하는
`runtime-builder` Deployment를 변경한다. 전용 maintenance worker의 고정
hostPath가 쓰기 가능해지고, 그 파일을 host systemd가 root로 실행하는
신뢰 경계를 확인한다. 노드 역할로 전용 EC2 인스턴스에 참가자 증명 태그를
쓰는 AWS API 호출이 최종 영향이다.

`volumeMount.readOnly`, 컨테이너 UID/GID, `readOnlyRootFilesystem`은 서로
다른 설정이다. writable hostPath만으로 임의 호스트 root 실행을 주장하지
않는다. 현재 랩의 host systemd path unit이 변경된 maintenance 파일을
실행한다는 조건을 함께 증명한다.

## 참가자 경로

1. 허용된 IP에서 ModelGate에 접근한다. 모델 검증의 취약한 역직렬화가
   validator 컨테이너에서 코드 실행을 일으킨다. 참가자는 전용 공격자 EC2의
   터미널에서 validator가 시작한 연결을 받는다. EC2 자체에는 AWS 역할,
   operator kubeconfig, Git credential이 없다. Pod 셸은 validator와 같은
   UID 10001, ServiceAccount 및 네트워크 문맥을 사용한다.
2. Pod 셸에서 내부 DNS와 모니터링을 조사한다. Grafana datasource와 운영
   로그를 통해 현재 실습 회차에 유효하고 `runtime-builder/` 한 경로에만
   쓸 수 있는 Git credential을 발견한다. 중간 Flag, Secret reader Job,
   broker exchange, 공개 `next` 응답은 정답 경로에서 사용하지 않는다.
3. 참가자는 내부 Git 저장소의 운영 메모와 Deployment를 검토하고 단일
   Deployment를 변경한다. Git credential은 지정 저장소, branch,
   `runtime-builder/` 경로에만 쓸 수 있다. Argo CD의 revision은 참가자
   commit과 일치해야 한다.
4. 대상 workload는 고정 이미지, ServiceAccount, nodeSelector, hostPath
   경로를 유지한다. 참가자가 조정할 수 있는 보안 필드는 검토된 UID/GID와
   maintenance mount의 `readOnly`다. Git으로 제어하는 Pod 명령은 그
   hostPath의 고정 maintenance 파일만 바꾸고 앱을 계속 실행한다.
5. host systemd가 해당 파일을 root로 실행한다. 호스트 UID, hostname,
   EC2 instance profile의 assumed-role ARN과 그 session의 instance ID를
   확인하고, `ec2:CreateTags`로 그 전용 인스턴스의
   `lab.vuln-mlops/proof`에 참가자가 고른 `lab-` marker를 쓴다. 참가자는
   고정 evidence mount를 읽는 변경된 Pod의 내부 로그에서 결과를 본다.
   운영자는 인스턴스의 실제 태그 값과 CloudTrail `CreateTags` 관리 이벤트,
   별도 Falco 호스트 이벤트를 대조한다. 로그의 ARN 문자열이나 JSON만으로
   AWS API 성공을 인정하지 않는다.

## 이름과 경계

새 활성 리소스의 namespace 및 서비스 이름에는 `stage`를 사용하지 않는다.
제안 이름은 `modelgate-lab`, `observability-lab`, `delivery-lab`,
`runtime-lab`이다. workload는 `modelgate`, `grafana`, `prometheus`,
`operations-log`, `gitea`, `runtime-builder`로 구분한다. 전용 노드는
`lab.vuln-mlops/node-role=escape`로 선택한다. 기존 `stage-*` 리소스는
역사적 프로필로 보존하며, 새 이름의 리소스와 혼용하여 성공을
주장하지 않는다.

공격자 EC2는 EKS와 같은 VPC에서 사설 IP로 validator 연결을 받는다.
팀원은 허용된 공인 IP에서 EC2에 SSH로 접속한다. Pod ingress는 역방향
연결에 필요하지 않다. 참가자에게 EKS operator 접근 권한을 주지 않는다.
팀의 동시 접속은 가능하지만 공유 Git branch와 전용 노드의 공격 실습은
순차 진행한다.

## 수락과 복구

- 공개 ModelGate 업로드부터 실제 validator Pod 셸 연결까지 재현한다.
- 셸에서 내부 모니터링 단서와 제한 Git credential을 발견한다.
- 참가자 commit과 Argo revision, 변경된 Pod 사양을 일치시킨다.
- baseline에서 비루트 UID와 read-only mount의 실패 원인을 확인한다.
- host systemd 실행, 전용 노드의 실제 태그 값 및 CloudTrail `CreateTags`
  관리 이벤트를 대조한다. 이벤트의 대상 인스턴스 ID와 호출자 session ID가
  일치해야 한다.
- Git baseline 복구, 노드 교체, 세션 종료 뒤 다시 시작할 수 있다.

최소 경계 검사는 외부 접속 제한, Git 범위, Pod의 직접 노드 IAM 접근 거부,
hostPath 경로 고정, 증명 키 하나와 escape 인스턴스 태그로 제한된 IAM 범위로
한정한다. 단계별 지름길을
전부 막는 것은 이번 개편의 완료 조건으로 삼지 않는다.

## 개발 순서

1. GitHub `main` 복구 기준과 로컬 미커밋 문서 백업을 확인한다.
2. validator reverse connection을 로컬에서 검증한다. EC2 주소는 구성값이다.
3. 내부 모니터링과 Git credential 단서를 연결하고 고정 broker를 제거한다.
4. 의미 기반 리소스 이름으로 새 활성 경로를 배포한다.
5. 참가자 Git 변경, Argo 동기화, hostPath, 호스트 실행과 EC2 태그를 검증한다.
6. 공격자 EC2와 EKS의 실제 배포는 각 단계의 로컬 검증 뒤 진행한다.
