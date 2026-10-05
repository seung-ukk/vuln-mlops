#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${ROOT_DIR}/infra/terraform"
LBC_CHART_VERSION="1.14.0"
LBC_RELEASE="aws-load-balancer-controller"
COMMAND="${1:-}"

usage() {
  cat <<'EOF'
Usage:
  AWS_PROFILE=<profile> ./deploy/eks-access/manage.sh deploy
  AWS_PROFILE=<profile> ./deploy/eks-access/manage.sh status
  AWS_PROFILE=<profile> ./deploy/eks-access/manage.sh teardown

Run Terraform first with enable_modelgate_public_access=true. teardown removes the
Kubernetes Service/NLB before the controller, but intentionally leaves the
Terraform-managed EIP and IAM resources for the subsequent terraform destroy.
EOF
}

case "$COMMAND" in
  deploy|status|teardown) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

for command_name in aws terraform kubectl helm python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'ERROR: required command is missing: %s\n' "$command_name" >&2
    exit 1
  fi
done

if [[ -z "${AWS_PROFILE:-}" ]]; then
  printf 'ERROR: set AWS_PROFILE to an explicit non-root deployment profile.\n' >&2
  exit 1
fi

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$CALLER_ARN" == *':root' ]]; then
  printf 'ERROR: root credentials are not accepted for public access management.\n' >&2
  exit 1
fi
printf 'AWS caller: %s\n' "$CALLER_ARN"

WORK_DIR="$(mktemp -d)"
KUBECONFIG_FILE="${WORK_DIR}/kubeconfig"
MODELGATE_MANIFEST="${WORK_DIR}/modelgate-public.yaml"
CONTROLLER_POLICY="${WORK_DIR}/controller-network-policy.yaml"
cleanup() {
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

tf() {
  terraform -chdir="$TF_DIR" "$@"
}

CLUSTER_NAME="$(tf output -raw cluster_name)"
AWS_REGION="$(tf output -raw region)"
OPERATOR_ROLE_ARN="$(tf output -raw cluster_operator_role_arn)"

aws eks update-kubeconfig \
  --name "$CLUSTER_NAME" \
  --region "$AWS_REGION" \
  --role-arn "$OPERATOR_ROLE_ARN" \
  --kubeconfig "$KUBECONFIG_FILE" >/dev/null
export KUBECONFIG="$KUBECONFIG_FILE"

render_manifests() {
  local enabled eip_allocation_id public_subnet_id public_subnet_cidr
  local kubernetes_service_ip vpc_cidr participant_cidrs_json

  enabled="$(tf output -raw modelgate_public_access_enabled)"
  if [[ "$enabled" != "true" ]]; then
    printf 'ERROR: apply Terraform with enable_modelgate_public_access=true first.\n' >&2
    exit 1
  fi

  eip_allocation_id="$(tf output -raw modelgate_public_eip_allocation_id)"
  public_subnet_id="$(tf output -raw modelgate_public_subnet_id)"
  public_subnet_cidr="$(tf output -raw modelgate_public_subnet_cidr)"
  kubernetes_service_ip="$(tf output -raw kubernetes_service_ip)"
  vpc_cidr="$(tf output -raw vpc_cidr)"
  participant_cidrs_json="$(tf output -json modelgate_participant_access_cidrs)"

  export EIP_ALLOCATION_ID="$eip_allocation_id"
  export PUBLIC_SUBNET_ID="$public_subnet_id"
  export PUBLIC_SUBNET_CIDR="$public_subnet_cidr"
  export KUBERNETES_SERVICE_IP="$kubernetes_service_ip"
  export VPC_CIDR="$vpc_cidr"
  export PARTICIPANT_CIDRS_JSON="$participant_cidrs_json"
  export MODELGATE_TEMPLATE="${SCRIPT_DIR}/modelgate-public.yaml.tpl"
  export CONTROLLER_TEMPLATE="${SCRIPT_DIR}/controller-network-policy.yaml.tpl"
  export MODELGATE_MANIFEST CONTROLLER_POLICY

  python3 - <<'PY'
import ipaddress
import json
import os
from pathlib import Path

participants = json.loads(os.environ["PARTICIPANT_CIDRS_JSON"])
if not participants:
    raise SystemExit("ERROR: participant_access_cidrs is empty")

for cidr in participants:
    network = ipaddress.ip_network(cidr, strict=True)
    if network.version != 4 or network.prefixlen != 32:
        raise SystemExit(f"ERROR: participant CIDR is not an IPv4 /32: {cidr}")

source_ranges = "\n".join(f'    - "{cidr}"' for cidr in participants)
policy_cidrs = [*participants, os.environ["PUBLIC_SUBNET_CIDR"]]
ip_blocks = "\n".join(
    f"        - ipBlock:\n            cidr: {cidr}" for cidr in policy_cidrs
)

modelgate = Path(os.environ["MODELGATE_TEMPLATE"]).read_text()
modelgate = modelgate.replace("__PUBLIC_SUBNET_ID__", os.environ["PUBLIC_SUBNET_ID"])
modelgate = modelgate.replace("__EIP_ALLOCATION_ID__", os.environ["EIP_ALLOCATION_ID"])
modelgate = modelgate.replace("__LOAD_BALANCER_SOURCE_RANGES__", source_ranges)
modelgate = modelgate.replace("__MODELGATE_INGRESS_IPBLOCKS__", ip_blocks)
Path(os.environ["MODELGATE_MANIFEST"]).write_text(modelgate)

controller = Path(os.environ["CONTROLLER_TEMPLATE"]).read_text()
controller = controller.replace("__VPC_CIDR__", os.environ["VPC_CIDR"])
controller = controller.replace(
    "__KUBERNETES_SERVICE_IP__", os.environ["KUBERNETES_SERVICE_IP"]
)
Path(os.environ["CONTROLLER_POLICY"]).write_text(controller)
PY
}

pin_modelgate_to_nlb_zone() {
  local public_subnet_id public_availability_zone
  public_subnet_id="$(tf output -raw modelgate_public_subnet_id)"
  public_availability_zone="$(aws ec2 describe-subnets \
    --region "$AWS_REGION" \
    --subnet-ids "$public_subnet_id" \
    --query 'Subnets[0].AvailabilityZone' \
    --output text)"

  if [[ -z "$public_availability_zone" || "$public_availability_zone" == "None" ]]; then
    printf 'ERROR: could not resolve the public NLB subnet availability zone.\n' >&2
    exit 1
  fi

  kubectl -n modelgate-lab patch deployment modelgate \
    --type=merge \
    --patch "{\"spec\":{\"strategy\":{\"type\":\"RollingUpdate\",\"rollingUpdate\":{\"maxSurge\":0,\"maxUnavailable\":1}},\"template\":{\"spec\":{\"nodeSelector\":{\"topology.kubernetes.io/zone\":\"${public_availability_zone}\"}}}}}"
  kubectl -n modelgate-lab rollout status deployment/modelgate --timeout=10m
  printf 'ModelGate pinned to the single NLB zone: %s\n' "$public_availability_zone"
}

unpin_modelgate_from_nlb_zone() {
  if ! kubectl -n modelgate-lab get deployment modelgate >/dev/null 2>&1; then
    return
  fi

  kubectl -n modelgate-lab patch deployment modelgate \
    --type=merge \
    --patch '{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":{"maxSurge":"25%","maxUnavailable":"25%"}},"template":{"spec":{"nodeSelector":{"topology.kubernetes.io/zone":null}}}}}'
  kubectl -n modelgate-lab rollout status deployment/modelgate --timeout=10m
}

wait_for_public_address() {
  local attempt hostname
  for attempt in $(seq 1 120); do
    hostname="$(kubectl -n modelgate-lab get service modelgate-public \
      -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
    if [[ -n "$hostname" ]]; then
      printf 'ModelGate NLB hostname: %s\n' "$hostname"
      printf 'ModelGate fixed IPv4: %s\n' "$(tf output -raw modelgate_public_eip)"
      return
    fi
    sleep 5
  done
  kubectl -n modelgate-lab describe service modelgate-public >&2
  printf 'ERROR: timed out waiting for the ModelGate NLB.\n' >&2
  exit 1
}

wait_for_healthy_target() {
  local hostname load_balancer_arn target_group_arn states attempt
  hostname="$(kubectl -n modelgate-lab get service modelgate-public \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"

  for attempt in $(seq 1 180); do
    load_balancer_arn="$(aws elbv2 describe-load-balancers \
      --region "$AWS_REGION" \
      --query "LoadBalancers[?DNSName=='${hostname}'].LoadBalancerArn | [0]" \
      --output text 2>/dev/null || true)"
    if [[ -z "$load_balancer_arn" || "$load_balancer_arn" == "None" ]]; then
      sleep 5
      continue
    fi

    target_group_arn="$(aws elbv2 describe-target-groups \
      --region "$AWS_REGION" \
      --load-balancer-arn "$load_balancer_arn" \
      --query 'TargetGroups[0].TargetGroupArn' \
      --output text 2>/dev/null || true)"
    if [[ -z "$target_group_arn" || "$target_group_arn" == "None" ]]; then
      sleep 5
      continue
    fi

    states="$(aws elbv2 describe-target-health \
      --region "$AWS_REGION" \
      --target-group-arn "$target_group_arn" \
      --query 'TargetHealthDescriptions[].TargetHealth.State' \
      --output text 2>/dev/null || true)"
    states="${states//$'\t'/ }"
    if [[ " $states " == *" healthy "* ]]; then
      printf 'ModelGate NLB target is healthy.\n'
      return
    fi
    sleep 5
  done

  if [[ -n "${target_group_arn:-}" && "$target_group_arn" != "None" ]]; then
    aws elbv2 describe-target-health \
      --region "$AWS_REGION" \
      --target-group-arn "$target_group_arn" >&2 || true
  fi
  printf 'ERROR: timed out waiting for a single healthy ModelGate NLB target.\n' >&2
  exit 1
}

wait_for_eip_disassociation() {
  local allocation_id association attempt
  allocation_id="$(tf output -raw modelgate_public_eip_allocation_id)"
  for attempt in $(seq 1 120); do
    association="$(aws ec2 describe-addresses \
      --region "$AWS_REGION" \
      --allocation-ids "$allocation_id" \
      --query 'Addresses[0].AssociationId' \
      --output text 2>/dev/null || true)"
    if [[ -z "$association" || "$association" == "None" ]]; then
      printf 'EIP is detached from the deleted NLB: %s\n' "$allocation_id"
      return
    fi
    sleep 5
  done
  printf 'ERROR: EIP is still attached; do not destroy the cluster yet.\n' >&2
  exit 1
}

case "$COMMAND" in
  deploy)
    render_manifests
    pin_modelgate_to_nlb_zone
    kubectl apply -f "$CONTROLLER_POLICY"
    helm repo add eks https://aws.github.io/eks-charts --force-update >/dev/null
    helm repo update eks >/dev/null
    helm upgrade --install "$LBC_RELEASE" eks/aws-load-balancer-controller \
      --namespace kube-system \
      --version "$LBC_CHART_VERSION" \
      --set "clusterName=${CLUSTER_NAME}" \
      --set "region=${AWS_REGION}" \
      --set "vpcId=$(tf output -raw vpc_id)" \
      --set serviceAccount.create=true \
      --set serviceAccount.name=aws-load-balancer-controller \
      --set replicaCount=1 \
      --set 'nodeSelector.lab\.vuln-mlops/node-role=general' \
      --wait \
      --timeout 10m
    kubectl -n kube-system rollout status \
      deployment/aws-load-balancer-controller --timeout=10m
    kubectl apply -f "$MODELGATE_MANIFEST"
    wait_for_public_address
    wait_for_healthy_target
    ;;
  status)
    kubectl -n kube-system get deployment aws-load-balancer-controller
    kubectl -n modelgate-lab get service modelgate-public -o wide
    printf 'Terraform-managed fixed IPv4: %s\n' "$(tf output -raw modelgate_public_eip)"
    ;;
  teardown)
    if [[ "$(tf output -raw modelgate_public_access_enabled)" != "true" ]]; then
      printf 'ERROR: Terraform public-access outputs are not enabled.\n' >&2
      exit 1
    fi
    kubectl -n modelgate-lab delete service modelgate-public \
      --ignore-not-found --wait=true
    kubectl -n modelgate-lab delete networkpolicy modelgate-public \
      --ignore-not-found
    wait_for_eip_disassociation
    helm uninstall "$LBC_RELEASE" --namespace kube-system --wait || true
    kubectl -n kube-system delete networkpolicy aws-load-balancer-controller \
      --ignore-not-found
    unpin_modelgate_from_nlb_zone
    printf '%s\n' 'Access layer removed. Run terraform destroy to release the EIP and IAM role.'
    ;;
esac
