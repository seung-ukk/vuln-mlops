# Security policy

This repository intentionally pins a vulnerable MLflow release for an authorized,
isolated Kubernetes security lab. It must not be deployed on the public Internet or
in a cluster containing production credentials, workloads, or data.

## Supported use

- Dedicated test cluster or account only.
- Short-lived IAM credentials with explicit resource and tag restrictions.
- Canary data and disposable infrastructure only.
- NetworkPolicy enabled before the workload is exposed.
- Logs and CloudTrail retained for the exercise.

## Prohibited deployment

- Public ingress or public load balancer.
- Production AWS account, VPC, bucket, secret, database, or IAM role.
- Privileged containers, host mounts, host namespaces, or runtime sockets.
- Reuse of real credentials or real customer model artifacts.

The default `deploy/base` policy blocks private and link-local egress. The
`deploy/eks-lab` overlay deliberately enables selected lab paths and must only be
used after the target CIDRs and IAM controls have been reviewed.

For vulnerability details and remediation, see the upstream MLflow advisories
linked from the README.
