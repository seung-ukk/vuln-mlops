# EKS overlay

This overlay keeps the Stage 1 workload on the same restricted network boundary as
the base deployment. In particular, it does not add IMDS access or unrestricted
private-network egress.

The Terraform foundation creates the VPC, EKS control plane, managed add-ons, and
separate general/escape node groups. The Stage 5 manifest uses the published,
digest-pinned runtime-client image without mounting a host binary. Stage 2-5
cluster-specific API CIDRs remain work for the deployment-composition milestone;
they are intentionally not widened here as a placeholder.

`coredns-network-policy.yaml` is the bootstrap exception required by VPC CNI strict
mode. It selects only the managed CoreDNS Pods and permits DNS, Kubernetes API, probe,
and metrics ports. Apply this policy as soon as the nodes and VPC CNI are ready; other
Pods remain denied until their namespace policies are installed.
