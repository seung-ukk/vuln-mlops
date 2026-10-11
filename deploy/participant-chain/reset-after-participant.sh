#!/usr/bin/env bash
set -euo pipefail

# Run from the operator's WSL after collecting the participant's evidence.
# Gitea uses emptyDir, so restarting it removes the previous exercise's Git
# history. The escape node is replaced only after Argo has restored the base.
REGION=ap-northeast-2
CLUSTER=vuln-mlops-personal-lab
ACCOUNT=707605822656

if [[ $# -ne 3 ]]; then
  echo 'usage: reset-after-participant.sh <attacker EC2 private IPv4> <listener port> <reviewed ModelGate OCI digest>' >&2
  exit 2
fi
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SETUP="${ROOT_DIR}/deploy/participant-chain/setup.sh"

for tool in aws kubectl jq openssl curl mktemp python3; do
  command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }
done
[[ "$3" =~ ^ghcr\.io/seung-ukk/vuln-mlops@sha256:[a-f0-9]{64}$ ]] || {
  echo 'expected a reviewed ModelGate OCI digest' >&2
  exit 2
}
python3 - "$1" "$2" <<'PY'
import ipaddress
import sys

address = ipaddress.IPv4Address(sys.argv[1])
port = int(sys.argv[2])
if not address.is_private or address.is_loopback or address.is_link_local or not 1024 <= port <= 65535:
    raise SystemExit("attacker receiver must be a private IPv4 and a non-privileged port")
PY
[[ "$(kubectl config current-context)" == "arn:aws:eks:${REGION}:${ACCOUNT}:cluster/${CLUSTER}" ]] || {
  echo 'unexpected kubectl context' >&2
  exit 1
}
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$ACCOUNT" ]] || {
  echo 'unexpected AWS account' >&2
  exit 1
}

verify_baseline() {
  kubectl -n runtime-lab get deployment runtime-builder -o json | jq -e '
    .spec.template.spec as $pod |
    $pod.securityContext.runAsUser == 10001 and
    $pod.securityContext.runAsGroup == 10001 and
    ([ $pod.containers[0].volumeMounts[] |
       select(.name == "host-maintenance" or .name == "node-evidence") |
       .readOnly ] == [true, true])
  ' >/dev/null
}

echo '[1/5] End the validator session and restore the Git-controlled baseline.'
kubectl -n modelgate-lab rollout restart deployment/modelgate
kubectl -n modelgate-lab rollout status deployment/modelgate --timeout=10m
bash "$SETUP" "$1" "$2" "$3"
verify_baseline || { echo 'runtime-builder is not at the read-only, non-root baseline' >&2; exit 1; }

echo '[2/5] Recreate the lab-only Gitea repository and rotate its credential.'
# This Gitea Deployment has an emptyDir data volume. Its new Pod starts with
# an empty repository and the second setup creates one fresh baseline commit.
kubectl -n delivery-lab rollout restart deployment/gitea
kubectl -n delivery-lab rollout status deployment/gitea --timeout=10m
umask 077
WORK_DIR="$(mktemp -d)"
trap 'rm -rf -- "$WORK_DIR"' EXIT
openssl rand -hex 24 >"${WORK_DIR}/git-token"
kubectl -n observability-lab create secret generic git-writer-credential \
  --from-file=token="${WORK_DIR}/git-token" --dry-run=client -o yaml | kubectl apply -f -
bash "$SETUP" "$1" "$2" "$3"
verify_baseline || { echo 'runtime-builder baseline check failed after repository recreation' >&2; exit 1; }
BASE_REVISION="$(kubectl -n delivery-lab get application runtime-builder -o jsonpath='{.status.sync.revision}')"
[[ -n "$BASE_REVISION" ]] || { echo 'Argo baseline revision is empty' >&2; exit 1; }
GIT_COMMIT_COUNT="$(kubectl -n delivery-lab exec deployment/gitea -- git \
  --git-dir=/var/lib/gitea/git/repositories/lab-git-writer/vuln-mlops-gitops.git \
  rev-list --count lab-runtime)"
[[ "$GIT_COMMIT_COUNT" == 1 ]] || {
  echo "Gitea lab-runtime is not a fresh single-commit branch: $GIT_COMMIT_COUNT" >&2
  exit 1
}

echo '[3/5] Replace the operations-log Pod that retained the old token.'
kubectl -n observability-lab rollout restart deployment/operations-log
kubectl -n observability-lab rollout status deployment/operations-log --timeout=10m

echo '[4/5] Drain and replace the dedicated escape node.'
mapfile -t ESCAPE_NODES < <(kubectl get nodes -l lab.vuln-mlops/node-role=escape -o json | jq -r '.items[].metadata.name')
[[ ${#ESCAPE_NODES[@]} -eq 1 ]] || { echo 'expected exactly one escape node' >&2; exit 1; }
OLD_NODE="${ESCAPE_NODES[0]}"
OLD_PROVIDER="$(kubectl get node "$OLD_NODE" -o jsonpath='{.spec.providerID}')"
OLD_INSTANCE="${OLD_PROVIDER##*/}"
[[ "$OLD_INSTANCE" =~ ^i-[0-9a-f]+$ ]] || { echo 'invalid escape instance ID' >&2; exit 1; }
OLD_ASG="$(aws autoscaling describe-auto-scaling-instances --region "$REGION" \
  --instance-ids "$OLD_INSTANCE" --query 'AutoScalingInstances[0].AutoScalingGroupName' --output text)"
[[ "$OLD_ASG" == eks-vuln-mlops-personal-lab-escape-* ]] || {
  echo "unexpected escape Auto Scaling Group: $OLD_ASG" >&2
  exit 1
}
kubectl drain "$OLD_NODE" --ignore-daemonsets --delete-emptydir-data --timeout=10m
aws autoscaling terminate-instance-in-auto-scaling-group --region "$REGION" \
  --instance-id "$OLD_INSTANCE" --no-should-decrement-desired-capacity >/dev/null

NEW_NODE=""
for _ in $(seq 1 90); do
  NEW_NODE="$(kubectl get nodes -l lab.vuln-mlops/node-role=escape -o json | jq -r --arg old "$OLD_NODE" '
    .items[] | select(.metadata.name != $old) |
    select(any(.status.conditions[]; .type == "Ready" and .status == "True")) |
    .metadata.name' | head -n 1)"
  [[ -n "$NEW_NODE" ]] && break
  sleep 10
done
[[ -n "$NEW_NODE" ]] || { echo 'replacement escape node did not become Ready' >&2; exit 1; }
kubectl -n runtime-lab rollout status deployment/runtime-builder --timeout=10m
for _ in $(seq 1 60); do
  if kubectl -n runtime-lab get pods -l app=runtime-builder -o json | jq -e --arg node "$NEW_NODE" '
    any(.items[]; .spec.nodeName == $node and
      any(.status.containerStatuses[]?; .name == "runtime-builder" and .ready == true))
  ' >/dev/null; then
    break
  fi
  sleep 5
done
kubectl -n runtime-lab get pods -l app=runtime-builder -o json | jq -e --arg node "$NEW_NODE" '
  any(.items[]; .spec.nodeName == $node and
    any(.status.containerStatuses[]?; .name == "runtime-builder" and .ready == true))
' >/dev/null || { echo 'baseline runtime-builder is not Ready on the replacement node' >&2; exit 1; }
NEW_PROVIDER="$(kubectl get node "$NEW_NODE" -o jsonpath='{.spec.providerID}')"
NEW_INSTANCE="${NEW_PROVIDER##*/}"
[[ "$NEW_INSTANCE" =~ ^i-[0-9a-f]+$ && "$NEW_INSTANCE" != "$OLD_INSTANCE" ]] || {
  echo 'replacement instance ID is invalid' >&2
  exit 1
}
NEW_ASG="$(aws autoscaling describe-auto-scaling-instances --region "$REGION" \
  --instance-ids "$NEW_INSTANCE" --query 'AutoScalingInstances[0].AutoScalingGroupName' --output text)"
[[ "$NEW_ASG" == "$OLD_ASG" ]] || {
  echo "replacement instance is not in the original escape Auto Scaling Group: $NEW_ASG" >&2
  exit 1
}
aws ec2 wait instance-terminated --region "$REGION" --instance-ids "$OLD_INSTANCE"
kubectl wait --for=delete "node/${OLD_NODE}" --timeout=10m
mapfile -t ESCAPE_NODES < <(kubectl get nodes -l lab.vuln-mlops/node-role=escape -o json | jq -r '.items[].metadata.name')
[[ ${#ESCAPE_NODES[@]} -eq 1 && "${ESCAPE_NODES[0]}" == "$NEW_NODE" ]] || {
  echo 'expected only the replacement escape node' >&2
  exit 1
}

echo '[5/5] Check the new node, Argo revision, and public service.'
aws ec2 describe-tags --region "$REGION" \
  --filters "Name=resource-id,Values=${NEW_INSTANCE}" 'Name=key,Values=lab.vuln-mlops/proof' \
  --output json | jq -e '.Tags | length == 0' >/dev/null || {
  echo 'replacement node already has a participant proof tag' >&2
  exit 1
}
verify_baseline
ARGO_STATE="$(kubectl -n delivery-lab get application runtime-builder -o json)"
jq -e --arg revision "$BASE_REVISION" '
  .status.sync.status == "Synced" and .status.health.status == "Healthy" and
  .status.sync.revision == $revision
' >/dev/null <<<"$ARGO_STATE" || { echo 'Argo no longer matches the fresh baseline' >&2; exit 1; }
curl -fsS --max-time 10 http://3.35.2.114/readyz | jq -e '.status == "ready"' >/dev/null

printf 'Reset complete: baseline=%s new_node=%s instance=%s\n' \
  "$BASE_REVISION" "$NEW_NODE" "$NEW_INSTANCE"
