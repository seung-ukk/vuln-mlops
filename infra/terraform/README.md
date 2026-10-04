# Terraform EKS foundation

This directory creates only the AWS foundation for Stages 1-5:

- one dedicated VPC across two or three availability zones;
- public subnets for a single cost-conscious NAT gateway and later ingress;
- private subnets for every worker;
- an EKS control plane with private access and public access restricted to operator
  `/32` addresses;
- API-only EKS Access Entries and a separate cluster operator role;
- managed CoreDNS, kube-proxy, VPC CNI, and Pod Identity Agent add-ons;
- VPC CNI NetworkPolicy enforcement in strict mode;
- separate general and tainted escape managed node groups with distinct security
  groups;
- all five EKS control-plane log types retained in CloudWatch.

It intentionally does not create Stage 6 storage, CSI permissions, application AWS
identities, public load balancers, DNS, certificates, scoring services, or final flags.

The escape worker accepts control-plane traffic only on the reviewed EKS node ports.
It cannot initiate arbitrary traffic or connect to the general workers except for
TCP/UDP DNS on port 53; HTTPS egress remains available for bootstrap, EKS, registry,
and AWS API access. Kubernetes NetworkPolicy remains the workload-level boundary.

## Account portability

Use a different state and tfvars file for every AWS account. Never copy a state file
between personal and team accounts. Account IDs and operator CIDRs are inputs; access
keys and session tokens are never Terraform variables.

Do not use root credentials to bootstrap this lab. Terraform creates a separate
operator role and EKS Access Entry; the bootstrap caller should be a temporary
administrative user or role whose permissions are removed after validation. Team
deployment should likewise use a temporary administrative role rather than root.
The KMS key administrator principal is pinned to the account principal so changing
the Terraform caller does not rewrite the key policy; the EKS cluster role retains
only the key usage permissions required for Kubernetes secret encryption.

## Bootstrap a fresh account

VPC CNI enforces NetworkPolicy in strict mode. On a clean cluster, CoreDNS must not
be created until its reviewed `kube-system` policy exists. Use the orchestration
script rather than a direct one-shot `terraform apply`; it applies a saved
foundation plan, installs only the CoreDNS policy, enables the managed add-on, and
requires a final no-drift plan.

From WSL, select an explicit non-root administrative profile and run:

```bash
cd /mnt/c/Users/yoseb/Desktop/vuln-mlops/infra/terraform
export AWS_PROFILE=vuln-mlops-admin
./bootstrap.sh
```

The script prompts before each apply. Pass `--auto-approve` only after reviewing
the generated plans and when non-interactive execution is intentional. It can be
rerun after interruption: if CoreDNS is already in Terraform state, it will not
remove the add-on to repeat the first phase. Root caller credentials and an unset
`AWS_PROFILE` are rejected.

## Validate without creating resources

From WSL:

```bash
cd /mnt/c/Users/yoseb/Desktop/vuln-mlops/infra/terraform
terraform init
terraform fmt -check -recursive
terraform validate
```

Copy the example to an ignored, account-specific file and replace both placeholders:

```bash
cp personal.tfvars.example personal.auto.tfvars
```

The public endpoint input accepts only IPv4 `/32` values and explicitly rejects
`0.0.0.0/0`. Verify the plan before any apply:

```bash
terraform plan -out=personal.tfplan
terraform show personal.tfplan
```

Do not approve either apply until the resource count, account ID, region, estimated
cost, node sizes, and operator CIDRs have been reviewed. The local state contains
infrastructure metadata and must remain ignored and private.

## Cost and teardown

EKS control-plane hours, EC2 workers, one NAT gateway, public IPv4 addresses, and
CloudWatch logs incur cost. The escape group deliberately stays at exactly one node;
the general group defaults to two. When the exercise is finished, remove Kubernetes
load balancers first, set `deletion_protection = false`, and run `terraform destroy`.
