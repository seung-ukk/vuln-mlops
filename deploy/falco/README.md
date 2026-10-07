# Falco observation pilot

This layer is separate from the attack-path overlays. It does not change Argo,
ModelGate, runtime-builder, runtime-maintenance, admission, IAM, or node groups.
It only records selected process-start events; it never takes response actions.

The two Helm releases use the reviewed official `falcosecurity/falco` chart **9.2.0**
(Falco **0.45.0**). `modern_ebpf` is an engine choice, not a separately pinned kernel
module version. The container metadata plugin is pinned at **0.7.4** and automatic
artifact follow is off. The chart pulls this plugin once during Pod startup. No
kernel-module driver loader or Falco Talon is installed.

The `falco-observe` namespace is the only privileged-Pod-Security exception for
this blue-team layer. Falco requires kernel capabilities and a containerd socket
for local event capture and container metadata. Its ServiceAccount has no IRSA
annotation. The namespace NetworkPolicy allows DNS and HTTPS egress for plugin
download, denies ingress, and grants no traffic from lab workloads to Falco.
Treat Falco's socket access as trusted node-level operator access. This is not a
participant workload or a new Stage 5 attack path.

## What is captured

The sole enabled custom rule records process starts in `modelgate-lab`,
`stage-02-rbac`, `stage-04-gitops`, and `stage-05-runtime`. JSON output has
namespace, Pod, container, and executable name. It intentionally omits arguments,
environment, file paths, URLs, output, credentials, and Flag content. Upstream
default rules are not loaded because their outputs can include command lines or
file paths. Falco metrics snapshots are emitted every five minutes to help spot
event drops and resource pressure. There is no blocking or response integration.

Falco is not a complete HTTP or Kubernetes audit trail. In particular, Stage 1
deserialization may run inside an existing Python process and emit no process-start
alert. Correlate Falco with existing ModelGate/Argo logs, EKS audit logs, and
CloudTrail. `kubectl logs` is a pilot inspection channel, not durable retention;
plan a restricted log shipper and retention before a real team exercise.

For the reviewed manual CloudWatch 7-day collection procedure, see
[`CLOUDWATCH.md`](CLOUDWATCH.md). It was deployed to the personal EKS cluster
on 2026-10-06; follow the linked runbook for verification and cleanup.

## Preflight

Run these commands from WSL with the existing operator kubeconfig. The expected
node labels are two `general` and one `escape`; the latter has the exact
`lab.vuln-mlops/escape=true:NoSchedule` taint. Metrics Server is currently absent,
so `kubectl top` is not a reliable check. Review Node allocated resources and
conditions before and after adding Falco. Falco requests 100m CPU/512Mi memory
and is limited to 500m CPU/1Gi memory on each selected node.

```bash
cd /mnt/c/Users/yoseb/Desktop/vuln-mlops
kubectl get nodes -L lab.vuln-mlops/node-role
ESCAPE_NODE="$(kubectl get nodes -l lab.vuln-mlops/node-role=escape -o jsonpath='{.items[0].metadata.name}')"
kubectl describe node "$ESCAPE_NODE"
kubectl -n stage-05-runtime get deployment runtime-maintenance
helm template falco-general falco --repo https://falcosecurity.github.io/charts \
  --version 9.2.0 -n falco-observe \
  -f deploy/falco/values-common.yaml -f deploy/falco/values-general.yaml >/tmp/falco-general.yaml
helm template falco-escape falco --repo https://falcosecurity.github.io/charts \
  --version 9.2.0 -n falco-observe \
  -f deploy/falco/values-common.yaml -f deploy/falco/values-escape.yaml >/tmp/falco-escape.yaml
```

## Staged installation

Apply the namespace and network policy before either DaemonSet because the VPC CNI
uses strict NetworkPolicy startup. The general and escape releases have disjoint
node selectors, so each node gets one Falco Pod. Install general first, check its
logs and ModelGate readiness, then install escape. Review Helm output before each
next command. Neither release should change an existing lab Deployment.

```bash
kubectl apply -f deploy/falco/namespace.yaml
kubectl apply -f deploy/falco/network-policy.yaml
helm upgrade --install falco-general falco \
  --repo https://falcosecurity.github.io/charts --version 9.2.0 \
  -n falco-observe --wait --atomic --timeout 10m \
  -f deploy/falco/values-common.yaml -f deploy/falco/values-general.yaml
kubectl -n falco-observe rollout status daemonset/falco-general --timeout=10m
kubectl -n falco-observe get pods -o wide
curl -fsS http://3.35.2.114/readyz
```

Only after general has stayed healthy:

```bash
helm upgrade --install falco-escape falco \
  --repo https://falcosecurity.github.io/charts --version 9.2.0 \
  -n falco-observe --wait --atomic --timeout 10m \
  -f deploy/falco/values-common.yaml -f deploy/falco/values-escape.yaml
kubectl -n falco-observe rollout status daemonset/falco-escape --timeout=10m
kubectl -n falco-observe get pods -o wide
kubectl -n stage-05-runtime get deployment runtime-maintenance
kubectl describe node "$ESCAPE_NODE"
```

Read JSON alerts without exporting Pod logs to the participant entrypoint:

```bash
kubectl -n falco-observe logs -l app.kubernetes.io/instance=falco-general \
  -c falco --since=20m --prefix --max-log-requests=2
kubectl -n falco-observe logs daemonset/falco-escape -c falco --since=20m
```

For a small **operator-only sensor check**, start a harmless Python process in
each existing Stage 5 container and look for `Lab container process started` in
the corresponding Falco release. This checks event capture without changing the
Git/Argo participant state. It is not a Stage 5 attack-path acceptance result.

```bash
kubectl -n stage-05-runtime exec deployment/runtime-builder -c runtime-builder -- python -c pass
kubectl -n stage-05-runtime exec deployment/runtime-maintenance -c runtime-relay -- python -c pass
kubectl -n falco-observe logs -l app.kubernetes.io/instance=falco-general \
  -c falco --since=5m --prefix --max-log-requests=2 | grep 'Lab container process started'
kubectl -n falco-observe logs daemonset/falco-escape -c falco --since=5m \
  | grep 'Lab container process started'
```

If the escape Pod fails, shows kernel/BPF errors, has event drops, or causes Node
pressure, remove only that release and check `runtime-maintenance` readiness:

```bash
helm uninstall falco-escape -n falco-observe --wait
kubectl -n stage-05-runtime get deployment runtime-maintenance
```

Do not infer full Stage 1-5 observability from a successful Falco rollout. After
installation, run one controlled 5-A and 5-B participant exercise and correlate
Falco event timestamps with the existing proof-bound application and audit logs.
