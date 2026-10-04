#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COREDNS_POLICY="${SCRIPT_DIR}/../../deploy/eks-lab/coredns-network-policy.yaml"
COREDNS_ADDRESS='module.eks.aws_eks_addon.this["coredns"]'
AUTO_APPROVE=false

usage() {
  printf 'Usage: AWS_PROFILE=<non-root-profile> %s [--auto-approve]\n' "$0"
}

case "${1:-}" in
  "") ;;
  --auto-approve) AUTO_APPROVE=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

for command_name in terraform aws kubectl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'ERROR: required command is missing: %s\n' "$command_name" >&2
    exit 1
  fi
done

if [[ -z "${AWS_PROFILE:-}" ]]; then
  printf 'ERROR: set AWS_PROFILE to an explicit non-root bootstrap profile.\n' >&2
  exit 1
fi

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$CALLER_ARN" == *':root' ]]; then
  printf 'ERROR: root credentials are not accepted for lab bootstrap.\n' >&2
  exit 1
fi
printf 'AWS caller: %s\n' "$CALLER_ARN"

if [[ ! -f "$COREDNS_POLICY" ]]; then
  printf 'ERROR: CoreDNS policy was not found: %s\n' "$COREDNS_POLICY" >&2
  exit 1
fi

PHASE1_PLAN="$(mktemp)"
PHASE2_PLAN="$(mktemp)"
KUBECONFIG_FILE="$(mktemp)"
cleanup() {
  rm -f -- "$PHASE1_PLAN" "$PHASE2_PLAN" "$KUBECONFIG_FILE"
}
trap cleanup EXIT

tf() {
  terraform -chdir="$SCRIPT_DIR" "$@"
}

confirm_apply() {
  local phase="$1"
  if [[ "$AUTO_APPROVE" == true ]]; then
    return
  fi
  local answer
  read -r -p "Apply the reviewed ${phase} plan? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    printf 'Stopped before apply.\n'
    exit 0
  fi
}

tf init -input=false

# On a clean or partially completed deployment, create the cluster and workers
# without CoreDNS. Strict VPC CNI policy would otherwise isolate CoreDNS before
# its namespace policy can be installed.
if ! tf state list 2>/dev/null | grep -Fqx "$COREDNS_ADDRESS"; then
  tf plan -input=false -var=enable_coredns_addon=false -out="$PHASE1_PLAN"
  confirm_apply "foundation"
  tf apply -input=false "$PHASE1_PLAN"
else
  printf 'CoreDNS is already in Terraform state; skipping the foundation phase.\n'
fi

CLUSTER_NAME="$(tf output -raw cluster_name)"
AWS_REGION="$(tf output -raw region)"
OPERATOR_ROLE_ARN="$(tf output -raw cluster_operator_role_arn)"

aws eks update-kubeconfig \
  --name "$CLUSTER_NAME" \
  --region "$AWS_REGION" \
  --role-arn "$OPERATOR_ROLE_ARN" \
  --kubeconfig "$KUBECONFIG_FILE" >/dev/null
export KUBECONFIG="$KUBECONFIG_FILE"

if [[ "$(kubectl get nodes --no-headers 2>/dev/null | wc -l)" -eq 0 ]]; then
  printf 'ERROR: the cluster has no worker nodes.\n' >&2
  exit 1
fi
kubectl wait --for=condition=Ready nodes --all --timeout=15m

# Apply only the reviewed CoreDNS bootstrap boundary before enabling the add-on.
kubectl apply -f "$COREDNS_POLICY"

# Recover safely when rerunning after an interrupted or previously failed add-on.
if kubectl -n kube-system get deployment coredns >/dev/null 2>&1; then
  kubectl -n kube-system rollout restart deployment/coredns
  kubectl -n kube-system rollout status deployment/coredns --timeout=10m
  if [[ "$(aws eks describe-addon --cluster-name "$CLUSTER_NAME" --addon-name coredns --region "$AWS_REGION" --query 'addon.status' --output text 2>/dev/null || true)" == "ACTIVE" ]]; then
    tf untaint "$COREDNS_ADDRESS" >/dev/null 2>&1 || true
  fi
fi

set +e
tf plan -input=false -detailed-exitcode -var=enable_coredns_addon=true -out="$PHASE2_PLAN"
PHASE2_EXIT=$?
set -e
case "$PHASE2_EXIT" in
  0) printf 'CoreDNS is already converged in Terraform.\n' ;;
  2)
    confirm_apply "CoreDNS"
    tf apply -input=false "$PHASE2_PLAN"
    ;;
  *) printf 'ERROR: CoreDNS phase planning failed.\n' >&2; exit "$PHASE2_EXIT" ;;
esac

aws eks wait addon-active \
  --cluster-name "$CLUSTER_NAME" \
  --addon-name coredns \
  --region "$AWS_REGION"
kubectl -n kube-system rollout status deployment/coredns --timeout=10m

set +e
tf plan -input=false -detailed-exitcode -var=enable_coredns_addon=true >/dev/null
FINAL_EXIT=$?
set -e
if [[ "$FINAL_EXIT" -ne 0 ]]; then
  printf 'ERROR: final Terraform plan is not clean (exit %s).\n' "$FINAL_EXIT" >&2
  exit 1
fi

printf 'Bootstrap complete: workers are Ready, CoreDNS is ACTIVE, and Terraform has no drift.\n'
