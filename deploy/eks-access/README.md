# Domainless ModelGate public entry point

This optional layer exposes only ModelGate through one internet-facing Network Load
Balancer in the first public subnet. Terraform allocates exactly one Elastic IP and
creates an EKS Pod Identity role for AWS Load Balancer Controller. The Kubernetes
deployment remains separate from the Stage 1-5 orchestrator.

Because a one-subnet NLB enables only one Availability Zone, the access manager pins
the ModelGate Pod to the matching zone. Without this pin a rollout could place the
new Pod in another zone and AWS would report the IP target as `Target.NotInUse`.
The single general node in that zone cannot always hold both old and new three-container
ModelGate Pods, so this layer also uses `maxSurge: 0` and `maxUnavailable: 1`. A reset
has a short intentional outage but cannot deadlock on an unschedulable surge Pod.
`teardown` removes the zone selector and restores the default rolling-update values.

This is deliberately a single-AZ, non-HA training entry point. It uses HTTP because
ACM public certificates require a DNS name. Only synthetic lab data may cross this
endpoint. Prometheus, Grafana, the credential broker, Gitea, Argo CD, MLflow, the
canary, and the Kubernetes API are not published by this layer.

Set the account-specific values in the local tfvars file:

```hcl
enable_modelgate_public_access = true
participant_access_cidrs = [
  "198.51.100.25/32",
]
```

Review and apply Terraform first. A plan for an existing cluster should add one EIP,
one Pod Identity association/role and policy, and the two port 9443 security-group
rules. It must not replace the cluster or node groups.

```bash
cd infra/terraform
terraform plan -input=false -out=/tmp/modelgate-access.tfplan
terraform apply /tmp/modelgate-access.tfplan

cd ../..
AWS_PROFILE=vuln-mlops-admin \
  bash deploy/eks-access/manage.sh deploy
```

The script prints the fixed participant IPv4. Verify from an allowlisted network:

```bash
curl -fsS http://FIXED_EIP/healthz
curl -fsS http://FIXED_EIP/readyz
```

Remove the access layer before destroying EKS:

```bash
AWS_PROFILE=vuln-mlops-admin \
  bash deploy/eks-access/manage.sh teardown

cd infra/terraform
terraform destroy
```

`teardown` waits until the NLB has detached the EIP before removing the controller.
It does not release the Terraform-managed EIP itself; a successful `terraform
destroy` releases it. If destroy is interrupted, inspect `aws ec2
describe-addresses` and release any remaining lab-tagged address only after it is no
longer associated.
