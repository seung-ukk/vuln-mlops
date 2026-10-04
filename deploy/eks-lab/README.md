# EKS overlay

This overlay keeps the Stage 1 workload on the same restricted network boundary as
the base deployment. In particular, it does not add IMDS access or unrestricted
private-network egress.

All three ModelGate containers are rewritten from the base development tag to the
reviewed GHCR OCI index digest
`sha256:9953d23e8102114873c3a52eaecd0a2e80d260cb0b7ee09ae348c0af3d66a244`.
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

Stage 3 is also composed into this overlay, while its temporary `attack-client.yaml`
acceptance harness remains excluded. The common monitoring policy permits only DNS
and the internal Prometheus/credential-broker flows. A separate policy selects only
the Prometheus Pod and grants Kubernetes discovery access to `172.20.0.1/32` on TCP
443; Grafana and the credential broker neither receive that network path nor mount a
ServiceAccount token. All Stage 3 Services remain cluster-internal. AWS acceptance
used an operator-created temporary client Pod to exercise the datasource and broker
chain and removed it afterward; a participant-facing handoff that does not require
operator `exec` is still pending.

Stage 4 uses its own `stage-04/` EKS overlay because the vendored Argo CD CRDs require
server-side apply. This keeps the existing Stage 1-3 field ownership untouched while
the parent overlay still renders the complete Stage 1-4 composition. The common
Stage 4 policy permits only same-namespace and DNS traffic; a separate policy grants
only the Argo CD application controller access to `172.20.0.1/32` on TCP 443. Redis is
pinned to a reviewed OCI index digest and uses a synthetic pre-created password so its
upstream API-dependent secret initializer and ServiceAccount token can be removed.
Unused Argo CD entrypoints are scaled to zero, and Gitea remains ClusterIP-only.
AWS acceptance verified the restricted Git push, Argo reconciliation, admission/RBAC
denials, and audit evidence. Gitea data remains ephemeral and must be bootstrapped
again after its Pod is recreated.

Stage 5 is composed through `stage-05/`, which consumes the complete Stage 5 base and
reapplies the same two EKS-only Stage 4 network restrictions. Tests require those
small network files to stay identical to the Stage 4 EKS overlay. It moves only
`runtime-builder` into `stage-05-runtime`, fixes its destination and controller RBAC,
and mounts only `/run/containerd/containerd.sock` on the tainted escape worker.
Terraform writes the fixed synthetic node proof during escape-node cloud-init; the
proof is not a credential, does not enter a Kubernetes manifest, and is absent from
general workers. Updating an existing foundation adds a launch-template version and
can roll the single escape node, so review the saved plan before applying it.

`coredns-network-policy.yaml` is the bootstrap exception required by VPC CNI strict
mode. It selects only the managed CoreDNS Pods and permits DNS, Kubernetes API, probe,
and metrics ports. Apply this policy as soon as the nodes and VPC CNI are ready; other
Pods remain denied until their namespace policies are installed.
