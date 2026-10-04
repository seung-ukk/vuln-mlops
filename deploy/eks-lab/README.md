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
digest-pinned runtime-client image without mounting a host binary. Stage 2-5
cluster-specific API CIDRs remain work for the deployment-composition milestone;
they are intentionally not widened here as a placeholder.

`coredns-network-policy.yaml` is the bootstrap exception required by VPC CNI strict
mode. It selects only the managed CoreDNS Pods and permits DNS, Kubernetes API, probe,
and metrics ports. Apply this policy as soon as the nodes and VPC CNI are ready; other
Pods remain denied until their namespace policies are installed.
