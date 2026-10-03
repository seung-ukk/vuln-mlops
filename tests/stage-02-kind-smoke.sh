#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cluster_name="stage-02-$PPID-$$"
kind_node_image="kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
temp_dir="$(mktemp -d)"
audit_dir="$temp_dir/audit"
kind_config="$temp_dir/kind-config.yaml"
mkdir -p "$audit_dir"

cleanup() {
  kind delete cluster --name "$cluster_name" >/dev/null 2>&1 || true
  rm -rf "$temp_dir"
}
trap cleanup EXIT

for command in kind kubectl base64; do
  command -v "$command" >/dev/null || {
    echo "required command not found: $command" >&2
    exit 1
  }
done

cat >"$kind_config" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  serviceSubnet: 10.96.0.0/12
nodes:
  - role: control-plane
    extraMounts:
      - hostPath: ${repo_root}/lab/stages/stage-02-rbac/audit-policy.yaml
        containerPath: /etc/kubernetes/stage-02-audit-policy.yaml
        readOnly: true
      - hostPath: ${audit_dir}
        containerPath: /var/log/kubernetes
    kubeadmConfigPatches:
      - |
        kind: ClusterConfiguration
        apiServer:
          extraArgs:
            audit-policy-file: /etc/kubernetes/stage-02-audit-policy.yaml
            audit-log-path: /var/log/kubernetes/audit.log
            audit-log-maxage: "1"
            audit-log-maxbackup: "1"
            audit-log-maxsize: "20"
          extraVolumes:
            - name: audit-policy
              hostPath: /etc/kubernetes/stage-02-audit-policy.yaml
              mountPath: /etc/kubernetes/stage-02-audit-policy.yaml
              readOnly: true
              pathType: File
            - name: audit-log
              hostPath: /var/log/kubernetes
              mountPath: /var/log/kubernetes
              pathType: DirectoryOrCreate
EOF

kind create cluster --name "$cluster_name" --image "$kind_node_image" --config "$kind_config"
kubectl apply -k "$repo_root/deploy/base"
kubectl apply -k "$repo_root/lab/stages/stage-02-rbac"

modelgate_user="system:serviceaccount:modelgate-lab:modelgate"

expect_no() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "shortcut unexpectedly allowed: $description" >&2
    exit 1
  fi
}

expect_can_i_no() {
  local description="$1"
  shift
  local answer
  answer="$(kubectl auth can-i "$@" || true)"
  if [ "$answer" != "no" ]; then
    echo "shortcut unexpectedly allowed: $description ($answer)" >&2
    exit 1
  fi
}

expect_apply_denied() {
  local description="$1"
  local patch="$2"
  if kubectl patch --local -f "$repo_root/lab/stages/stage-02-rbac/attack-job.yaml" \
      --type=json -p="$patch" -o yaml |
      kubectl apply --as="$modelgate_user" -f - >/dev/null 2>&1; then
    echo "admission shortcut unexpectedly allowed: $description" >&2
    exit 1
  fi
}

kubectl auth can-i create selfsubjectrulesreviews.authorization.k8s.io \
  --as="$modelgate_user" | grep -qx yes
kubectl auth can-i create jobs.batch -n stage-02-rbac \
  --as="$modelgate_user" | grep -qx yes

expect_no "direct Stage 2 Secret get" kubectl get secret stage-02-flag \
  -n stage-02-rbac --as="$modelgate_user"
expect_can_i_no "RoleBinding creation" create rolebindings.rbac.authorization.k8s.io \
  -n stage-02-rbac --as="$modelgate_user"
expect_can_i_no "ServiceAccount token minting" create serviceaccounts/token \
  -n stage-02-rbac --as="$modelgate_user"
expect_can_i_no "Pod exec" create pods/exec -n stage-02-rbac --as="$modelgate_user"
expect_can_i_no "node read" get nodes --as="$modelgate_user"
expect_can_i_no "default namespace Job creation" create jobs.batch \
  -n default --as="$modelgate_user"
expect_can_i_no "kube-system Job creation" create jobs.batch \
  -n kube-system --as="$modelgate_user"
expect_can_i_no "argocd Job creation" create jobs.batch \
  -n argocd --as="$modelgate_user"

expect_apply_denied "wrong ServiceAccount" \
  '[{"op":"replace","path":"/spec/template/spec/serviceAccountName","value":"default"}]'
expect_apply_denied "unapproved image" \
  '[{"op":"replace","path":"/spec/template/spec/containers/0/image","value":"registry.k8s.io/kubectl:latest"}]'
expect_apply_denied "privileged container" \
  '[{"op":"replace","path":"/spec/template/spec/containers/0/securityContext/privileged","value":true}]'
expect_apply_denied "hostPath mount" \
  '[{"op":"add","path":"/spec/template/spec/volumes","value":[{"name":"host","hostPath":{"path":"/"}}]}]'
expect_apply_denied "Secret volume shortcut" \
  '[{"op":"add","path":"/spec/template/spec/volumes","value":[{"name":"other-secret","secret":{"secretName":"stage-02-flag"}}]}]'
expect_apply_denied "environment override" \
  '[{"op":"add","path":"/spec/template/spec/containers/0/env","value":[{"name":"KUBERNETES_SERVICE_HOST","value":"attacker.invalid"}]}]'

kubectl apply --as="$modelgate_user" \
  -f "$repo_root/lab/stages/stage-02-rbac/attack-job.yaml"
kubectl wait --for=condition=complete job/stage-02-secret-reader \
  -n stage-02-rbac --timeout=240s || {
    kubectl get pods -n stage-02-rbac -o wide
    kubectl describe job stage-02-secret-reader -n stage-02-rbac
    kubectl describe pods -n stage-02-rbac -l job-name=stage-02-secret-reader
    kubectl logs -n stage-02-rbac -l job-name=stage-02-secret-reader --all-containers --prefix
    exit 1
  }

pod_name="$(kubectl get pods -n stage-02-rbac --as="$modelgate_user" \
  -l job-name=stage-02-secret-reader -o jsonpath='{.items[0].metadata.name}')"
encoded_flag="$(kubectl logs -n stage-02-rbac --as="$modelgate_user" "$pod_name")"
decoded_flag="$(printf '%s' "$encoded_flag" | base64 --decode)"
test "$decoded_flag" = 'FLAG{stage_2_rbac_chaining_placeholder}'

for _ in $(seq 1 20); do
  audit_text="$(docker exec "$cluster_name-control-plane" sh -c 'cat /var/log/kubernetes/audit.log' 2>/dev/null || true)"
  if grep -q 'system:serviceaccount:modelgate-lab:modelgate' <<<"$audit_text" &&
      grep -q 'stage-02-secret-reader' <<<"$audit_text"; then
    echo "Stage 2 intended path, shortcut denials, and audit evidence verified."
    exit 0
  fi
  sleep 1
done

echo "Stage 2 audit evidence was not observed" >&2
exit 1
