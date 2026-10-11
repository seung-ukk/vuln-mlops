#!/usr/bin/env bash
set -euo pipefail

# Fresh, isolated participant profile. This script is prepared for the attacker
# EC2; it is not run by the repository tests and does not apply Terraform.
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
CHAIN_DIR="${ROOT_DIR}/lab/participant-chain"
DELIVERY_DIR="${CHAIN_DIR}/delivery"
RUNTIME_DIR="${CHAIN_DIR}/runtime"
MODEL_EGRESS="${CHAIN_DIR}/modelgate-egress.yaml"
IMAGE="${3:-}"
ATTACKER_IP="${1:-}"
LISTENER_PORT="${2:-}"

if [[ ! "$IMAGE" =~ ^ghcr\.io/seung-ukk/vuln-mlops@sha256:[a-f0-9]{64}$ ]]; then
  echo 'usage: setup.sh <attacker EC2 private IPv4> <listener port> <reviewed ModelGate OCI digest>' >&2
  exit 2
fi
python3 - "$ATTACKER_IP" "$LISTENER_PORT" <<'PY'
import ipaddress
import sys

address = ipaddress.IPv4Address(sys.argv[1])
port = int(sys.argv[2])
if not address.is_private or address.is_loopback or address.is_link_local or not 1024 <= port <= 65535:
    raise SystemExit("attacker receiver must be a private EC2 IPv4 and a non-privileged port")
PY

for command_name in kubectl git curl openssl base64 mktemp sed tr; do
  command -v "$command_name" >/dev/null || { echo "missing command: $command_name" >&2; exit 1; }
done
CURRENT_CONTEXT="$(kubectl config current-context)"
[[ "$CURRENT_CONTEXT" == *vuln-mlops-personal-lab* ]] || {
  echo "unexpected kubectl context: $CURRENT_CONTEXT" >&2
  exit 1
}

WORK_DIR="$(mktemp -d)"
PORT_FORWARD_PID=""
cleanup() {
  if [[ -n "$PORT_FORWARD_PID" ]]; then
    kill "$PORT_FORWARD_PID" 2>/dev/null || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

kubectl apply -f "${CHAIN_DIR}/observability/namespace.yaml"
kubectl apply -f "${DELIVERY_DIR}/namespace.yaml"
kubectl apply -f "${RUNTIME_DIR}/namespace.yaml"

# A random per-deployment Git credential is deliberately logged by the
# operations-log Pod. No token is kept in source control.
TOKEN_FILE="${WORK_DIR}/git-token"
if kubectl -n observability-lab get secret git-writer-credential >/dev/null 2>&1; then
  kubectl -n observability-lab get secret git-writer-credential \
    -o jsonpath='{.data.token}' | base64 -d >"$TOKEN_FILE"
else
  openssl rand -hex 24 | tr -d '\r\n' >"$TOKEN_FILE"
  kubectl -n observability-lab create secret generic git-writer-credential \
    --from-file=token="$TOKEN_FILE" >/dev/null
fi
chmod 600 "$TOKEN_FILE"

REDIS_FILE="${WORK_DIR}/redis-auth"
if kubectl -n delivery-lab get secret argocd-redis >/dev/null 2>&1; then
  kubectl -n delivery-lab get secret argocd-redis \
    -o jsonpath='{.data.auth}' | base64 -d >"$REDIS_FILE"
else
  openssl rand -hex 24 | tr -d '\r\n' >"$REDIS_FILE"
fi
kubectl -n delivery-lab create secret generic argocd-redis \
  --from-file=auth="$REDIS_FILE" --dry-run=client -o yaml | kubectl apply -f -

VENDOR_DIR="${ROOT_DIR}/lab/stages/stage-04-gitops/vendor"
for crd in application-crd-v3.5.3.yaml applicationset-crd-v3.5.3.yaml appproject-crd-v3.5.3.yaml; do
  kubectl apply --server-side -f "${VENDOR_DIR}/${crd}"
done
kubectl apply --server-side -k "$DELIVERY_DIR"
# Argo owns the mutable fields of this Deployment after the first Git sync.
# Reapplying the base with kubectl on a reset would conflict with Argo's field
# manager. Refresh the supporting resources, and create the base only once.
kubectl apply --server-side \
  -f "${RUNTIME_DIR}/serviceaccount.yaml" \
  -f "${RUNTIME_DIR}/service.yaml" \
  -f "${RUNTIME_DIR}/controller-rbac.yaml" \
  -f "${RUNTIME_DIR}/validator-rbac.yaml" \
  -f "${RUNTIME_DIR}/default-deny.yaml" \
  -f "${RUNTIME_DIR}/admission-policy.yaml"
if ! kubectl -n runtime-lab get deployment runtime-builder >/dev/null 2>&1; then
  kubectl apply --server-side -f "${RUNTIME_DIR}/runtime-builder-base.yaml"
fi
# The previous profile used STAGE5_MODE. That env entry can remain owned by
# the original kubectl field manager after Argo switches to MAINTENANCE_PROFILE,
# causing the fixed-env admission rule to reject the new Git revision.
if kubectl -n runtime-lab get deployment runtime-builder \
  -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' | grep -qw STAGE5_MODE; then
  kubectl -n runtime-lab set env deployment/runtime-builder STAGE5_MODE-
fi
kubectl apply -k "${CHAIN_DIR}/observability"
kubectl -n observability-lab set image deployment/operations-log "operations-log=${IMAGE}"

# Keep the listener-port argument for existing setup/reset callers. The
# receiver policy now permits TCP to this one private IP on any port.
sed -e "s|__ATTACKER_PRIVATE_IP__|${ATTACKER_IP}|g" \
    "$MODEL_EGRESS" | kubectl apply -f -
kubectl -n modelgate-lab set image deployment/modelgate \
  "api=${IMAGE}" "mlflow-registry=${IMAGE}" "validator=${IMAGE}"
kubectl -n modelgate-lab set env deployment/modelgate --containers=api \
  MODELGATE_PROFILE=participant-chain MODELGATE_ENABLE_WEBHOOKS=false

kubectl -n delivery-lab rollout status deployment/gitea --timeout=10m
TOKEN="$(cat "$TOKEN_FILE")"
if kubectl -n delivery-lab exec deployment/gitea -- \
  gitea admin user list --config /etc/gitea/app.ini | grep -Eq '(^|[[:space:]])lab-git-writer([[:space:]]|$)'; then
  kubectl -n delivery-lab exec deployment/gitea -- \
    gitea admin user change-password --config /etc/gitea/app.ini \
      --username lab-git-writer --password "$TOKEN" \
      --must-change-password=false >/dev/null
else
  kubectl -n delivery-lab exec deployment/gitea -- \
    gitea admin user create --config /etc/gitea/app.ini \
      --username lab-git-writer --password "$TOKEN" \
      --email lab@example.invalid --must-change-password=false >/dev/null
fi

kubectl -n delivery-lab port-forward --address 127.0.0.1 service/gitea :3000 \
  >"${WORK_DIR}/port-forward.log" 2>&1 &
PORT_FORWARD_PID=$!
for _ in $(seq 1 60); do
  PORT="$(sed -nE 's/.*127\.0\.0\.1:([0-9]+) -> 3000.*/\1/p' "${WORK_DIR}/port-forward.log" | head -n 1)"
  [[ -n "$PORT" ]] && break
  sleep 1
done
[[ -n "${PORT:-}" ]] || { cat "${WORK_DIR}/port-forward.log" >&2; exit 1; }
GITEA_URL="http://127.0.0.1:${PORT}"
for _ in $(seq 1 60); do
  curl -fsS "${GITEA_URL}/api/healthz" >/dev/null && break
  sleep 1
done

STATUS="$(curl -sS -o /dev/null -w '%{http_code}' -u "lab-git-writer:${TOKEN}" \
  "${GITEA_URL}/api/v1/repos/lab-git-writer/vuln-mlops-gitops")"
if [[ "$STATUS" == 404 ]]; then
  curl -fsS -u "lab-git-writer:${TOKEN}" -H 'Content-Type: application/json' \
    -d '{"name":"vuln-mlops-gitops","private":true}' \
    "${GITEA_URL}/api/v1/user/repos" >/dev/null
elif [[ "$STATUS" != 200 ]]; then
  echo "unexpected Gitea repository status: $STATUS" >&2
  exit 1
fi

HOOK_B64="$(base64 <"${DELIVERY_DIR}/scope-hook.sh" | tr -d '\r\n')"
kubectl -n delivery-lab exec deployment/gitea -- sh -ceu \
  'mkdir -p "$1"; printf "%s" "$2" | base64 -d > "$1/scope"; chmod 0755 "$1/scope"' \
  sh '/var/lib/gitea/git/repositories/lab-git-writer/vuln-mlops-gitops.git/hooks/pre-receive.d' "$HOOK_B64"

kubectl -n delivery-lab create secret generic runtime-git-repository \
  --from-literal=type=git \
  --from-literal=url='http://gitea.delivery-lab.svc:3000/lab-git-writer/vuln-mlops-gitops.git' \
  --from-literal=username=lab-git-writer \
  --from-file=password="$TOKEN_FILE" --dry-run=client -o yaml | \
  kubectl label --local -f - argocd.argoproj.io/secret-type=repository -o yaml | \
  kubectl apply -f -

cat >"${WORK_DIR}/askpass" <<'SH'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' lab-git-writer ;;
  *Password*) cat "$LAB_GIT_TOKEN_FILE" ;;
esac
SH
chmod 700 "${WORK_DIR}/askpass"
export GIT_ASKPASS="${WORK_DIR}/askpass" LAB_GIT_TOKEN_FILE="$TOKEN_FILE" GIT_TERMINAL_PROMPT=0
REPO_URL="${GITEA_URL}/lab-git-writer/vuln-mlops-gitops.git"
REPO_DIR="${WORK_DIR}/repository"
if ! git clone --quiet --branch lab-runtime "$REPO_URL" "$REPO_DIR" 2>/dev/null; then
  mkdir -p "$REPO_DIR"
  git -C "$REPO_DIR" init -b lab-runtime >/dev/null
  git -C "$REPO_DIR" remote add origin "$REPO_URL"
fi
mkdir -p "${REPO_DIR}/runtime-builder"
cp "${CHAIN_DIR}/repository/runtime-builder/deployment.yaml" "${REPO_DIR}/runtime-builder/deployment.yaml"
cp "${CHAIN_DIR}/repository/runtime-builder/README.md" "${REPO_DIR}/runtime-builder/README.md"
git -C "$REPO_DIR" config user.name lab-git-writer
git -C "$REPO_DIR" config user.email lab@example.invalid
git -C "$REPO_DIR" add runtime-builder
if ! git -C "$REPO_DIR" diff --cached --quiet; then
  git -C "$REPO_DIR" commit -m 'establish runtime maintenance baseline' >/dev/null
  git -C "$REPO_DIR" push origin HEAD:lab-runtime >/dev/null
fi
EXPECTED_REVISION="$(git -C "$REPO_DIR" rev-parse HEAD)"
kubectl -n delivery-lab annotate application/runtime-builder argocd.argoproj.io/refresh=hard --overwrite >/dev/null
for _ in $(seq 1 120); do
  SYNC="$(kubectl -n delivery-lab get application/runtime-builder -o jsonpath='{.status.sync.status}')"
  HEALTH="$(kubectl -n delivery-lab get application/runtime-builder -o jsonpath='{.status.health.status}')"
  REVISION="$(kubectl -n delivery-lab get application/runtime-builder -o jsonpath='{.status.sync.revision}')"
  if [[ "$SYNC" == Synced && "$HEALTH" == Healthy && "$REVISION" == "$EXPECTED_REVISION" ]]; then
    break
  fi
  sleep 5
done
[[ "$SYNC" == Synced && "$HEALTH" == Healthy && "$REVISION" == "$EXPECTED_REVISION" ]] || {
  echo 'Argo CD did not reach the baseline revision' >&2
  exit 1
}
kubectl -n modelgate-lab rollout status deployment/modelgate --timeout=10m
kubectl -n observability-lab rollout status deployment/operations-log --timeout=10m
kubectl -n runtime-lab rollout status deployment/runtime-builder --timeout=10m
printf 'Prepared participant profile; baseline revision %s\n' "$EXPECTED_REVISION"
