# EKS overlay

This overlay keeps the Stage 1 workload on the same restricted network boundary as
the base deployment. In particular, it does not add IMDS access or unrestricted
private-network egress.

All three ModelGate containers are rewritten from the base development tag to the
reviewed GHCR OCI index digest
`sha256:8f0a902437e5f276e4c316fdb7d77b0f955337c075199b8c221a9193b2158da9`.
Resolve and review a newly published index before deliberately updating this pin.

The overlay is AWS-account neutral. Do not add a personal account ID, cluster ARN,
operator role ARN, subnet/security-group ID, or operator CIDR here. Moving from a
personal account to a team account must require only a separate Terraform state and
tfvars, an explicit team deployment profile/role, and that account's approved `/32`
operator CIDRs. The Kubernetes manifests and public GHCR digest stay unchanged.

`stage-01-canary` contains a synthetic-only ClusterIP service. Its default-deny
NetworkPolicy accepts TCP 9000 only from the ModelGate Pod, has no egress, and is not
published through an Ingress, LoadBalancer, or NodePort. The ModelGate policy adds
only the matching namespace, Pod label, and port. For the personal-account smoke,
the public first hop remains the reviewed `https://httpbin.org/redirect-to`; set
`POC_CANARY_TARGET=eks` so its redirect lands on the fixed in-cluster canary. Replace
the first hop with a team-owned HTTPS redirector before the team exercise.

The Terraform foundation creates the VPC, EKS control plane, managed add-ons, and
separate general/escape node groups. The Stage 5 manifest uses the published,
digest-pinned runtime-client image without mounting a host binary.

The overlay composes the Stage 2 controls but deliberately excludes its
`attack-job.yaml`; creating that Job remains the boundary-crossing action. Terraform
fixes the Kubernetes Service CIDR at `172.20.0.0/16`, and the EKS-only patches replace
kind's API destinations with the single `172.20.0.1/32` Service IP on TCP 443. Current
control-plane ENI and public endpoint addresses are not committed, so the same
manifests remain usable in the personal and team accounts.

Stage 3 is also composed into this overlay. Its persistent, restricted
`monitoring-session` relay runs as `monitoring-runner` in `stage-02-rbac`; the temporary
`attack-client.yaml` remains excluded. The common monitoring policy permits only DNS
and the internal Grafana/credential-broker flows. A separate policy selects only
the Prometheus Pod and grants Kubernetes discovery access to `172.20.0.1/32` on TCP
443; Grafana and the credential broker neither receive that network path nor mount a
ServiceAccount token. All Stage 3 Services remain cluster-internal. ModelGate can reach
only the relay on TCP 8080, and the proof-bound participant API exposes only datasource
discovery, the fixed topology query, and exact credential-reference exchange.
The credential response points to a proof-bound Git smart-HTTP gateway on the same
ModelGate endpoint; it does not expose an additional public Service.

Stage 4 uses its own `stage-04/` EKS overlay because the vendored Argo CD CRDs require
server-side apply. This keeps the existing Stage 1-3 field ownership untouched while
the parent overlay still renders the complete Stage 1-4 composition. The common
Stage 4 policy permits only same-namespace and DNS traffic; a separate policy grants
only the Argo CD application controller access to `172.20.0.1/32` on TCP 443. Redis is
pinned to a reviewed OCI index digest and uses a synthetic pre-created password so its
upstream API-dependent secret initializer and ServiceAccount token can be removed.
Unused Argo CD entrypoints are scaled to zero, and Gitea remains ClusterIP-only.
ModelGate can reach only the Gitea Pod on TCP 3000 and proxies only the fixed lab
repository's smart-HTTP paths. Its read-only Kubernetes status Roles are restricted by
`resourceNames: [runtime-builder]`; participants observe Argo sync through the ModelGate
API rather than an operator kubeconfig.
AWS acceptance verified the restricted Git push, Argo reconciliation, admission/RBAC
denials, and audit evidence. Gitea data remains ephemeral and must be bootstrapped
again after its Pod is recreated.

Stage 5 is composed through `stage-05/`, which consumes the complete Stage 5 base and
reapplies the same two EKS-only Stage 4 network restrictions. Tests require those
small network files to stay identical to the Stage 4 EKS overlay. It moves only
`runtime-builder` into `stage-05-runtime`, fixes its destination and controller RBAC,
and mounts only `/run/containerd/containerd.sock` on the tainted escape worker.
The socket is mounted only in the fixed `runtime-relay` container. ModelGate can reach
that relay on TCP 8080 through exact ingress/egress policies and exposes only a bodyless,
proof-bound Stage 5 operation; participants do not receive `pods/exec` or an arbitrary
CRI command surface.
Terraform writes the fixed synthetic node proof during escape-node cloud-init; the
proof is not a credential, does not enter a Kubernetes manifest, and is absent from
general workers. Updating an existing foundation adds a launch-template version and
can roll the single escape node, so review the saved plan before applying it.

`stage-03/coredns-network-policy.yaml` is the bootstrap exception required by VPC CNI strict
mode. It selects only the managed CoreDNS Pods and permits DNS, Kubernetes API, probe,
and metrics ports. Apply this policy as soon as the nodes and VPC CNI are ready; other
Pods remain denied until their namespace policies are installed.

## Stage 1-5 orchestration

`orchestrate.sh` joins the existing Terraform bootstrap and the account-neutral
Kubernetes composition without copying manifests into Terraform. It uses a temporary
kubeconfig for the Terraform-created operator role, applies Stage 1-3 with their
existing client-side ownership, then applies the vendored Argo CD CRDs and Stage 4-5
with the existing `vuln-mlops-stage4` server-side manager. On a resumed deployment it
restores the Git baseline before apply so Argo-owned runtime fields already match the
reviewed manifest. It then waits for the fixed workloads and recreates the synthetic
Gitea user, repository, scope hook, and Stage 5 baseline.

From WSL, with the account-specific `terraform.tfvars` and local state already selected:

```bash
export AWS_PROFILE=vuln-mlops-admin
./deploy/eks-lab/orchestrate.sh deploy
```

Use `--auto-approve` only after reviewing the Terraform plans. On an already converged
foundation, `--skip-foundation` avoids an infrastructure apply while still deriving the
cluster name, region, and operator role from Terraform outputs.

```bash
./deploy/eks-lab/orchestrate.sh deploy --skip-foundation
./deploy/eks-lab/orchestrate.sh status
./deploy/eks-lab/orchestrate.sh reset
```

After preparing the pinned Python 3.11 development environment, run the complete
post-reset acceptance chain with its interpreter path. The command resets ephemeral
proof state, exercises Stage 1 through Stage 5 in order, verifies representative
shortcut denials, and restores the reviewed Git baseline afterward.

```bash
POC_PYTHON=/tmp/vuln-mlops-poc-venv/bin/python \
  ./deploy/eks-lab/orchestrate.sh accept
```

To exercise the participant path through the allowlisted public ModelGate EIP instead
of the operator port-forward, set `POC_MODELGATE_URL` to the reviewed endpoint:

```bash
AWS_PROFILE=vuln-mlops-admin \
POC_PYTHON=/tmp/vuln-mlops-poc-venv/bin/python \
POC_MODELGATE_URL=http://<modelgate-eip> \
  ./deploy/eks-lab/orchestrate.sh accept
```

The harness still uses its temporary operator kubeconfig for setup, cleanup, and
shortcut-denial checks. Stage 1-5 participant API and Git gateway traffic uses the
specified ModelGate URL; the URL must be reachable from the allowlisted `/32`.

## Runtime Builder IAM migration draft

The current EKS deployment remains on the socket Stage 5 profile. After a new
ModelGate/runtime-builder image is published and its OCI index digest is reviewed,
`deploy --skip-foundation --stage5-iam` can migrate the existing Deployment to
the IRSA/S3 capstone. Set `RUNTIME_BUILDER_IMAGE` to the full
`ghcr.io/seung-ukk/vuln-mlops@sha256:<digest>` reference. The command reads the
Terraform role ARN, bucket, and region outputs; it uses the new image for both
ModelGate and runtime-builder, applies the IAM admission policy before pushing
the new Gitea baseline, and adds the participant README to that baseline.
It does not upload or rotate the synthetic S3 object.

The IAM migration requires an existing socket Stage 5 Deployment. The IAM
acceptance harness and public EIP validation remain pending. After migration,
use `reset --stage5-iam` with the same pinned image; the unqualified socket
deploy/reset/accept commands refuse to change an IAM Deployment.

`reset` compares the fixed `stage4-lab:runtime-builder/` baseline through the installed
pre-receive hook and creates a normal forward commit only when the content differs. It
removes the fixed Stage 2 Job and any legacy temporary Stage 3 client Pod if they exist,
and recreates the
ModelGate and runtime-builder Pods to clear ephemeral proof state. It does not force-push,
delete namespaces or Terraform resources, or broaden Stage 4/5 RBAC.
