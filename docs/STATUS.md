# Project Status

마지막 갱신: 2026-10-06 (Asia/Seoul)

이 문서는 새 Codex 작업과 팀원이 현재 상태를 빠르게 파악하기 위한 인계 문서다.
작업을 시작할 때 `LAB_PLAN.md`, `STAGE_CONTRACTS.md`, 이 문서를 순서대로 읽는다.

## 현재 기준점

- Branch: local `main` at `fd29a46` (PR #8); migration repair is uncommitted
- Latest merged commit: `fd29a46` (PR #8)
- Repository: `https://github.com/seung-ukk/vuln-mlops`
- Container: `ghcr.io/seung-ukk/vuln-mlops`
- 현재 작업 트리: PR #8의 IAM runtime-builder 전환 코드가 main에 병합되었고,
  개인 EKS의 기존 Stage 5 Deployment를 새 앱으로 전환했다. 공개 참가자 경로의
  명령 주입→IRSA→S3 proof 검증은 아직 하지 않았다. 아래 초기 준비 기록의
  "미적용" 문장은 당시 시점의 기록이며 현재 상태는 다음 항목이 우선한다.

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
  clean redeploy 검증은 남아 있다.
- 이번 수동 복구를 `orchestrate.sh`의 IAM migration 단계에 반영했다. 검토된 base
  Deployment에서 Pod template JSON patch를 생성하고 서버 dry-run 결과에서
  old socket/escape 필드가 제거됐는지 검사한 다음 실제 patch한다. 관련 로컬 테스트
  34개가 통과했다. 이 재현성 수정은 아직 commit/PR/실제 재실행 전이다.
- 현재 마무리 순서는 IAM 프로필 `reset --stage5-iam`으로 참가자 Git 변경과
  transient proof/Job을 복원하고, 이번 migration 복구와 참가자 PoC 문서/테스트를
  PR/CI로 보존한 뒤 reset 및 이후 재배포 재현성을 필요한 범위에서 확인하는 것이다.
  기존 socket 전용 `accept`는 IAM 프로필에 사용하지 않는다. 팀원 블라인드 단서
  발견성과 clean destroy→second apply는 이번 공개 참가자 PoC로 검증되지 않았다.
- 공개 참가자 검증 후 운영자가 `reset --stage5-iam`을 실행했다. Gitea의 실습
  commit `9945783`은 baseline commit `59c0be6a5b8645ef189a7f6588a6dbd19c66dcf3`으로
  복원됐고 Argo는 해당 revision에서 `Synced/Healthy`였다. Stage 2 Job이 삭제되고
  ModelGate와 runtime-builder Pod가 재시작/rollout되어 임시 세션과 `/tmp` proof가
  초기화됐다. 이 reset은 실제 EKS에서 통과했지만 수정된 IAM deploy migration
  경로의 두 번째 실행은 아직 검증하지 않았다.

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
