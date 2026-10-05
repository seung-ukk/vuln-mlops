#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${ROOT_DIR}/infra/terraform"
FOUNDATION_BOOTSTRAP="${TF_DIR}/bootstrap.sh"
STAGE4_DIR="${ROOT_DIR}/lab/stages/stage-04-gitops"
STAGE5_BASE="${ROOT_DIR}/lab/stages/stage-05-runtime/runtime-builder-base.yaml"
STAGE5_ADMISSION="${ROOT_DIR}/lab/stages/stage-05-runtime/admission-policy.yaml"
SCOPE_HOOK="${STAGE4_DIR}/scope-hook.sh"
STAGE3_OVERLAY="${SCRIPT_DIR}/stage-03"
STAGE5_OVERLAY="${SCRIPT_DIR}/stage-05"
IAM_STAGE5_DIR="${ROOT_DIR}/lab/stages/stage-05-iam-app"
IAM_STAGE5_OVERLAY="${SCRIPT_DIR}/stage-05-iam"
IAM_MIGRATION_OVERLAY="${SCRIPT_DIR}/stage-05-iam-migrate"
IAM_REPOSITORY_README="${IAM_STAGE5_DIR}/repository/runtime-builder/README.md"
IAM_TEMPLATE_HELPER="${SCRIPT_DIR}/iam_template.py"
ACCEPTANCE_SCRIPT="${SCRIPT_DIR}/acceptance.sh"

GITEA_NAMESPACE="stage-04-gitops"
GITEA_USER="stage3-lab-writer"
GITEA_TOKEN="SYNTHETIC_STAGE3_GIT_TOKEN"
GITEA_REPOSITORY="vuln-mlops-gitops"
GIT_BRANCH="stage4-lab"
FIELD_MANAGER="vuln-mlops-stage4"

COMMAND="${1:-}"
AUTO_APPROVE=false
SKIP_FOUNDATION=false
STAGE5_IAM=false

usage() {
  cat <<'EOF'
Usage:
  AWS_PROFILE=<non-root-profile> ./deploy/eks-lab/orchestrate.sh deploy [--auto-approve] [--skip-foundation]
  AWS_PROFILE=<non-root-profile> POC_PYTHON=<python-3.11> ./deploy/eks-lab/orchestrate.sh accept
  AWS_PROFILE=<non-root-profile> ./deploy/eks-lab/orchestrate.sh reset
  AWS_PROFILE=<non-root-profile> ./deploy/eks-lab/orchestrate.sh status
  AWS_PROFILE=<non-root-profile> RUNTIME_BUILDER_IMAGE=ghcr.io/seung-ukk/vuln-mlops@sha256:<digest> ./deploy/eks-lab/orchestrate.sh deploy --skip-foundation --stage5-iam

deploy provisions/resumes the Terraform foundation, applies the Stage 1-5 EKS
composition, and creates the fixed synthetic Gitea baseline. --skip-foundation
uses the existing Terraform outputs without applying infrastructure.
--stage5-iam selects the new IRSA/S3 capstone. It requires a published OCI
index digest and the Terraform runtime-builder role/bucket outputs.
EOF
}

if [[ -z "$COMMAND" ]]; then
  usage >&2
  exit 2
fi
shift

while (($#)); do
  case "$1" in
    --auto-approve) AUTO_APPROVE=true ;;
    --skip-foundation) SKIP_FOUNDATION=true ;;
    --stage5-iam) STAGE5_IAM=true ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$COMMAND" in
  deploy|accept|reset|status) ;;
  -h|--help) usage; exit 0 ;;
  *) printf 'ERROR: unknown command: %s\n' "$COMMAND" >&2; usage >&2; exit 2 ;;
esac

for command_name in aws terraform kubectl curl git base64 mktemp; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'ERROR: required command is missing: %s\n' "$command_name" >&2
    exit 1
  fi
done
if [[ "$STAGE5_IAM" == true ]] && ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for the reviewed IAM Deployment migration.\n' >&2
  exit 1
fi

if [[ -z "${AWS_PROFILE:-}" ]]; then
  printf 'ERROR: set AWS_PROFILE to an explicit non-root deployment profile.\n' >&2
  exit 1
fi

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$CALLER_ARN" == *':root' ]]; then
  printf 'ERROR: root credentials are not accepted for lab orchestration.\n' >&2
  exit 1
fi
printf 'AWS caller: %s\n' "$CALLER_ARN"

WORK_DIR="$(mktemp -d)"
KUBECONFIG_FILE="${WORK_DIR}/kubeconfig"
PORT_FORWARD_LOG="${WORK_DIR}/gitea-port-forward.log"
PORT_FORWARD_PID=""

cleanup() {
  if [[ -n "$PORT_FORWARD_PID" ]] && kill -0 "$PORT_FORWARD_PID" 2>/dev/null; then
    kill "$PORT_FORWARD_PID" 2>/dev/null || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

render_iam_template() {
  sed \
    -e "s|__RUNTIME_BUILDER_IMAGE__|${RUNTIME_BUILDER_IMAGE}|g" \
    -e "s|__RUNTIME_BUILDER_ROLE_ARN__|${IAM_ROLE_ARN}|g" \
    -e "s|__RUNTIME_PROOF_BUCKET__|${IAM_PROOF_BUCKET}|g" \
    -e "s|__AWS_REGION__|${IAM_REGION}|g" \
    "$1"
}

prepare_iam_stage5() {
  if [[ ! "${RUNTIME_BUILDER_IMAGE:-}" =~ ^ghcr\.io/seung-ukk/vuln-mlops@sha256:[a-f0-9]{64}$ ]]; then
    printf 'ERROR: RUNTIME_BUILDER_IMAGE must be the reviewed GHCR OCI digest.\n' >&2
    exit 1
  fi
  IAM_ROLE_ARN="$(tf output -raw runtime_builder_irsa_role_arn)"
  IAM_PROOF_BUCKET="$(tf output -raw runtime_proof_bucket)"
  IAM_REGION="$(tf output -raw region)"
  if [[ ! "$IAM_ROLE_ARN" =~ ^arn:aws:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_-]+$ ||
        ! "$IAM_PROOF_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{2,62}$ ||
        ! "$IAM_REGION" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]]; then
    printf 'ERROR: unexpected Terraform runtime-builder role, bucket, or region output.\n' >&2
    exit 1
  fi
  STAGE5_BASE="${WORK_DIR}/runtime-builder-base.yaml"
  STAGE5_ADMISSION="${WORK_DIR}/admission-policy.yaml"
  STAGE5_OVERLAY="$IAM_MIGRATION_OVERLAY"
  render_iam_template "${IAM_STAGE5_DIR}/runtime-builder-base.yaml.in" >"$STAGE5_BASE"
  render_iam_template "${IAM_STAGE5_DIR}/admission-policy.yaml.in" >"$STAGE5_ADMISSION"
}

tf() {
  terraform -chdir="$TF_DIR" "$@"
}

configure_kubeconfig() {
  local cluster_name aws_region operator_role
  cluster_name="$(tf output -raw cluster_name)"
  aws_region="$(tf output -raw region)"
  operator_role="$(tf output -raw cluster_operator_role_arn)"

  aws eks update-kubeconfig \
    --name "$cluster_name" \
    --region "$aws_region" \
    --role-arn "$operator_role" \
    --kubeconfig "$KUBECONFIG_FILE" >/dev/null
  export KUBECONFIG="$KUBECONFIG_FILE"

  kubectl wait --for=condition=Ready nodes --all --timeout=15m
}

guard_active_stage5_profile() {
  local active_sa
  active_sa="$(kubectl -n stage-05-runtime get deployment/runtime-builder \
    -o jsonpath='{.spec.template.spec.serviceAccountName}' 2>/dev/null || true)"
  if [[ "$active_sa" == "runtime-builder-iam" && "$STAGE5_IAM" == false ]]; then
    printf 'ERROR: this cluster uses the IAM Stage 5 app; pass --stage5-iam and its pinned image.\n' >&2
    exit 1
  fi
}

apply_stage_composition() {
  local crd

  # Preserve the client-side ownership used by the existing Stage 1-3 deploy.
  # Argo CD resources are deliberately excluded from this apply unit.
  if [[ "$STAGE5_IAM" == true ]]; then
    kubectl kustomize "$STAGE3_OVERLAY" | \
      sed -E "s|ghcr\\.io/seung-ukk/vuln-mlops@sha256:[a-f0-9]{64}|${RUNTIME_BUILDER_IMAGE}|g" | \
      kubectl apply -f -
  else
    kubectl apply -k "$STAGE3_OVERLAY"
  fi

  for crd in \
    application-crd-v3.5.3.yaml \
    applicationset-crd-v3.5.3.yaml \
    appproject-crd-v3.5.3.yaml
  do
    kubectl apply \
      --server-side \
      --field-manager="$FIELD_MANAGER" \
      -f "${STAGE4_DIR}/vendor/${crd}"
  done

  if [[ "$STAGE5_IAM" == true ]]; then
    kubectl kustomize "$STAGE5_OVERLAY" | render_iam_template /dev/stdin | \
      kubectl apply --server-side --field-manager="$FIELD_MANAGER" -f -
  else
    kubectl apply \
      --server-side \
      --field-manager="$FIELD_MANAGER" \
      -k "$STAGE5_OVERLAY"
  fi
}

preapply_stage5_admission() {
  # A changed relay digest must be admitted before the baseline Git revision is
  # pushed. The existing Deployment stays in place until Argo reconciles it.
  kubectl apply \
    --server-side \
    --field-manager="$FIELD_MANAGER" \
    -f "$STAGE5_ADMISSION"
}

replace_iam_runtime_template() {
  local patch_file preview_file
  patch_file="${WORK_DIR}/iam-template-patch.json"
  preview_file="${WORK_DIR}/iam-template-preview.json"

  # SSA merges preserve old socket containers and volumes even with force.
  # Replace the reviewed Pod template atomically with a JSON patch instead.
  kubectl create --dry-run=client -f "$STAGE5_BASE" -o json | \
    python3 "$IAM_TEMPLATE_HELPER" patch >"$patch_file"
  kubectl -n stage-05-runtime patch deployment/runtime-builder \
    --type=json --patch-file="$patch_file" --dry-run=server -o json >"$preview_file"
  python3 "$IAM_TEMPLATE_HELPER" verify "$RUNTIME_BUILDER_IMAGE" <"$preview_file"
  kubectl -n stage-05-runtime patch deployment/runtime-builder \
    --type=json --patch-file="$patch_file"
  kubectl -n stage-05-runtime rollout status deployment/runtime-builder --timeout=10m
}

wait_for_workloads() {
  local namespace workload
  while IFS='|' read -r namespace workload; do
    kubectl -n "$namespace" rollout status "$workload" --timeout=15m
  done <<'EOF'
modelgate-lab|deployment/modelgate
stage-01-canary|deployment/lab-canary
stage-02-rbac|deployment/monitoring-session
stage-03-monitoring|deployment/prometheus
stage-03-monitoring|deployment/grafana
stage-03-monitoring|deployment/credential-broker
stage-04-gitops|deployment/argocd-redis
stage-04-gitops|deployment/argocd-repo-server
stage-04-gitops|statefulset/argocd-application-controller
stage-04-gitops|deployment/gitea
stage-05-runtime|deployment/runtime-builder
EOF
}

ensure_gitea_user() {
  if kubectl -n "$GITEA_NAMESPACE" exec deployment/gitea -- \
      gitea admin user list --config /etc/gitea/app.ini | \
      grep -Eq "(^|[[:space:]])${GITEA_USER}([[:space:]]|$)"
  then
    printf 'Gitea user already exists: %s\n' "$GITEA_USER"
    return
  fi

  kubectl -n "$GITEA_NAMESPACE" exec deployment/gitea -- \
    gitea admin user create \
      --config /etc/gitea/app.ini \
      --username "$GITEA_USER" \
      --password "$GITEA_TOKEN" \
      --email lab@example.invalid \
      --must-change-password=false
}

start_gitea_port_forward() {
  kubectl -n "$GITEA_NAMESPACE" port-forward \
    --address 127.0.0.1 \
    service/gitea :3000 \
    >"$PORT_FORWARD_LOG" 2>&1 &
  PORT_FORWARD_PID=$!

  local attempt
  for attempt in $(seq 1 60); do
    if ! kill -0 "$PORT_FORWARD_PID" 2>/dev/null; then
      cat "$PORT_FORWARD_LOG" >&2
      printf 'ERROR: Gitea port-forward stopped unexpectedly.\n' >&2
      exit 1
    fi
    if grep -Eq 'Forwarding from 127\.0\.0\.1:[0-9]+ -> 3000' "$PORT_FORWARD_LOG"; then
      return
    fi
    sleep 1
  done

  cat "$PORT_FORWARD_LOG" >&2
  printf 'ERROR: timed out waiting for the Gitea port-forward.\n' >&2
  exit 1
}

gitea_port() {
  sed -nE 's/.*127\.0\.0\.1:([0-9]+) -> 3000.*/\1/p' "$PORT_FORWARD_LOG" | head -n 1
}

ensure_gitea_repository() {
  local port base_url status
  port="$(gitea_port)"
  base_url="http://127.0.0.1:${port}"

  for _ in $(seq 1 60); do
    if curl -fsS "${base_url}/api/healthz" >/dev/null; then
      break
    fi
    sleep 1
  done
  curl -fsS "${base_url}/api/healthz" >/dev/null

  status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -u "${GITEA_USER}:${GITEA_TOKEN}" \
    "${base_url}/api/v1/repos/${GITEA_USER}/${GITEA_REPOSITORY}")"
  case "$status" in
    200) printf 'Gitea repository already exists: %s/%s\n' "$GITEA_USER" "$GITEA_REPOSITORY" ;;
    404)
      curl -fsS \
        -u "${GITEA_USER}:${GITEA_TOKEN}" \
        -H 'Content-Type: application/json' \
        -d "{\"name\":\"${GITEA_REPOSITORY}\",\"private\":true}" \
        "${base_url}/api/v1/user/repos" >/dev/null
      ;;
    *) printf 'ERROR: unexpected Gitea repository status: %s\n' "$status" >&2; exit 1 ;;
  esac
}

install_scope_hook() {
  local gitea_pod hook_b64
  gitea_pod="$(kubectl -n "$GITEA_NAMESPACE" get pod \
    -l app=gitea \
    -o jsonpath='{.items[0].metadata.name}')"
  hook_b64="$(base64 < "$SCOPE_HOOK" | tr -d '\r\n')"

  kubectl -n "$GITEA_NAMESPACE" exec "$gitea_pod" -- sh -ceu \
    'hook_dir="$1"; hook_b64="$2"; mkdir -p "$hook_dir"; printf "%s" "$hook_b64" | base64 -d > "$hook_dir/scope"; chmod 0755 "$hook_dir/scope"' \
    sh \
    "/var/lib/gitea/git/repositories/${GITEA_USER}/${GITEA_REPOSITORY}.git/hooks/pre-receive.d" \
    "$hook_b64"
}

push_baseline() {
  local port repository_dir remote_url baseline_sha
  port="$(gitea_port)"
  repository_dir="${WORK_DIR}/repository"
  remote_url="http://${GITEA_USER}:${GITEA_TOKEN}@127.0.0.1:${port}/${GITEA_USER}/${GITEA_REPOSITORY}.git"

  rm -rf -- "$repository_dir"
  if ! git clone \
      --quiet \
      --branch "$GIT_BRANCH" \
      --single-branch \
      "$remote_url" \
      "$repository_dir" 2>/dev/null
  then
    mkdir -p "${repository_dir}/runtime-builder"
    git -C "$repository_dir" init -b "$GIT_BRANCH" >/dev/null
    git -C "$repository_dir" remote add origin "$remote_url"
  fi

  git -C "$repository_dir" config user.name "$GITEA_USER"
  git -C "$repository_dir" config user.email lab@example.invalid
  mkdir -p "${repository_dir}/runtime-builder"
  cp "$STAGE5_BASE" "${repository_dir}/runtime-builder/deployment.yaml"
  git -C "$repository_dir" add runtime-builder/deployment.yaml
  if [[ "$STAGE5_IAM" == true ]]; then
    cp "$IAM_REPOSITORY_README" "${repository_dir}/runtime-builder/README.md"
    git -C "$repository_dir" add runtime-builder/README.md
  fi

  if git -C "$repository_dir" diff --cached --quiet; then
    baseline_sha="$(git -C "$repository_dir" rev-parse HEAD)"
    printf 'Gitea baseline is already current at %s.\n' "$baseline_sha" >&2
    printf '%s\n' "$baseline_sha"
    return
  fi

  if git -C "$repository_dir" rev-parse --verify HEAD >/dev/null 2>&1; then
    git -C "$repository_dir" commit -m 'reset runtime-builder baseline' >/dev/null
  else
    git -C "$repository_dir" commit -m 'baseline runtime-builder' >/dev/null
  fi
  git -C "$repository_dir" push origin "HEAD:${GIT_BRANCH}" >/dev/null
  baseline_sha="$(git -C "$repository_dir" rev-parse HEAD)"
  printf '%s\n' "$baseline_sha"
}

wait_for_argo() {
  local expected_revision="$1" attempt sync health revision
  kubectl -n "$GITEA_NAMESPACE" annotate \
    application/runtime-builder \
    argocd.argoproj.io/refresh=hard \
    --overwrite >/dev/null

  for attempt in $(seq 1 120); do
    sync="$(kubectl -n "$GITEA_NAMESPACE" get application runtime-builder \
      -o jsonpath='{.status.sync.status}')"
    health="$(kubectl -n "$GITEA_NAMESPACE" get application runtime-builder \
      -o jsonpath='{.status.health.status}')"
    revision="$(kubectl -n "$GITEA_NAMESPACE" get application runtime-builder \
      -o jsonpath='{.status.sync.revision}')"
    if [[ "$sync" == "Synced" && "$health" == "Healthy" && "$revision" == "$expected_revision" ]]; then
      printf 'Argo CD baseline is Synced/Healthy at %s.\n' "$revision"
      return
    fi
    sleep 5
  done

  kubectl -n "$GITEA_NAMESPACE" get application runtime-builder -o yaml >&2
  printf 'ERROR: Argo CD did not reconcile the fixed baseline.\n' >&2
  exit 1
}

bootstrap_git_baseline() {
  ensure_gitea_user
  start_gitea_port_forward
  ensure_gitea_repository
  install_scope_hook
  local baseline_sha
  baseline_sha="$(push_baseline)"
  wait_for_argo "$baseline_sha"
}

restore_existing_git_baseline() {
  if ! kubectl -n "$GITEA_NAMESPACE" get application runtime-builder >/dev/null 2>&1; then
    return
  fi
  if ! kubectl -n "$GITEA_NAMESPACE" rollout status deployment/gitea --timeout=30s >/dev/null 2>&1; then
    return
  fi

  printf 'Existing GitOps deployment detected; restoring its baseline before apply.\n'
  bootstrap_git_baseline
}

reset_transient_resources() {
  kubectl -n stage-02-rbac delete job/stage-02-secret-reader --ignore-not-found
  kubectl -n stage-02-rbac delete pod/stage-03-client --ignore-not-found
  kubectl -n modelgate-lab rollout restart deployment/modelgate
  kubectl -n modelgate-lab rollout status deployment/modelgate --timeout=10m
  kubectl -n stage-05-runtime delete pod -l app=runtime-builder --wait=true
  kubectl -n stage-05-runtime rollout status deployment/runtime-builder --timeout=10m
}

show_status() {
  kubectl get nodes -L lab.vuln-mlops/node-role
  kubectl -n modelgate-lab get deployment modelgate
  kubectl -n stage-03-monitoring get deployment prometheus grafana credential-broker
  kubectl -n stage-04-gitops get deployment argocd-redis argocd-repo-server gitea
  kubectl -n stage-04-gitops get statefulset argocd-application-controller
  kubectl -n stage-04-gitops get application runtime-builder \
    -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision'
  kubectl -n stage-05-runtime get deployment runtime-builder
}

case "$COMMAND" in
  deploy)
    if [[ "$SKIP_FOUNDATION" == false ]]; then
      bootstrap_args=()
      if [[ "$AUTO_APPROVE" == true ]]; then
        bootstrap_args+=(--auto-approve)
      fi
      "$FOUNDATION_BOOTSTRAP" "${bootstrap_args[@]}"
    fi
    configure_kubeconfig
    guard_active_stage5_profile
    if [[ "$STAGE5_IAM" == true ]]; then
      if ! kubectl -n stage-05-runtime get deployment/runtime-builder >/dev/null 2>&1; then
        printf 'ERROR: --stage5-iam currently requires the existing Stage 5 Deployment.\n' >&2
        exit 1
      fi
      prepare_iam_stage5
      preapply_stage5_admission
      apply_stage_composition
      wait_for_workloads
      replace_iam_runtime_template
      bootstrap_git_baseline
      kubectl -n stage-05-runtime rollout status deployment/runtime-builder --timeout=10m
      show_status
      exit 0
    fi
    preapply_stage5_admission
    restore_existing_git_baseline
    apply_stage_composition
    wait_for_workloads
    bootstrap_git_baseline
    show_status
    ;;
  reset)
    configure_kubeconfig
    guard_active_stage5_profile
    if [[ "$STAGE5_IAM" == true ]]; then
      if [[ "$(kubectl -n stage-05-runtime get deployment/runtime-builder \
          -o jsonpath='{.spec.template.spec.serviceAccountName}')" != "runtime-builder-iam" ]]; then
        printf 'ERROR: deploy the IAM Stage 5 app before using --stage5-iam reset.\n' >&2
        exit 1
      fi
      prepare_iam_stage5
    fi
    wait_for_workloads
    bootstrap_git_baseline
    reset_transient_resources
    show_status
    ;;
  accept)
    if [[ "$STAGE5_IAM" == false ]]; then
      configure_kubeconfig
      guard_active_stage5_profile
    fi
    if [[ "$STAGE5_IAM" == true ]]; then
      printf 'ERROR: IAM acceptance is not implemented yet; use the participant PoC.\n' >&2
      exit 2
    fi
    wait_for_workloads
    bootstrap_git_baseline
    reset_transient_resources
    bash "$ACCEPTANCE_SCRIPT"
    show_status
    ;;
  status)
    configure_kubeconfig
    show_status
    ;;
esac
