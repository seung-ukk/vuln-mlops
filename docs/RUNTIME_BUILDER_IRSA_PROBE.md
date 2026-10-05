# Runtime-builder IRSA → S3 proof: operator validation

This is the first, infrastructure-only step toward replacing the socket-based
Stage 5. The current `runtime-builder` Deployment and its public participant
flow remain unchanged. A one-shot Job uses the **future** runtime-builder
ServiceAccount to verify AWS identity and read one synthetic S3 object. Do not
report this operator-run probe as participant end-to-end success.

Terraform creates one private bucket, an EKS OIDC provider, one IAM role trusted
only by `stage-05-runtime/runtime-builder-iam`, and `s3:GetObject` on exactly
`proof/final-flag.txt` in that bucket. The object body is deliberately outside
Terraform state. The role has no bucket listing, IAM mutation, or node rights.

## 1. Review the saved Terraform plan

Run from the repository root with the account-specific Terraform tfvars already
selected. The administrator runs all AWS/EKS commands locally:

```bash
AWS_PROFILE=vuln-mlops-admin terraform -chdir=infra/terraform plan \
  -input=false -out=/tmp/vuln-mlops-runtime-irsa.tfplan
AWS_PROFILE=vuln-mlops-admin terraform -chdir=infra/terraform show \
  /tmp/vuln-mlops-runtime-irsa.tfplan
```

Confirm the account/region and that no existing EKS cluster, managed node group,
security group, or workload resource is replaced or destroyed. Share the plan
before applying it. After review, apply **that saved plan**:

```bash
AWS_PROFILE=vuln-mlops-admin terraform -chdir=infra/terraform apply \
  -input=false /tmp/vuln-mlops-runtime-irsa.tfplan
```

## 2. Put the synthetic object outside Terraform

```bash
BUCKET=$(terraform -chdir=infra/terraform output -raw runtime_proof_bucket)
ROLE_ARN=$(terraform -chdir=infra/terraform output -raw runtime_builder_irsa_role_arn)
REGION=$(terraform -chdir=infra/terraform output -raw region)
FLAG_FILE=$(mktemp)
chmod 600 "$FLAG_FILE"
printf 'FLAG{stage_5_iam_placeholder}\n' > "$FLAG_FILE"
AWS_PROFILE=vuln-mlops-admin aws s3api put-object \
  --region "$REGION" --bucket "$BUCKET" --key proof/final-flag.txt \
  --body "$FLAG_FILE" --server-side-encryption AES256
rm -f "$FLAG_FILE"
```

Only the synthetic placeholder is stored. Do not upload actual credentials or
other data. Terraform does not read or store this object body.

## 3. Run the temporary in-cluster probe

Use the kubeconfig already configured for `vuln-mlops-personal-lab`. This Job is
on a general worker and has no runtime socket or host mount. Its only purpose is
to prove the exact ServiceAccount → IRSA → object path. It prints the account,
assumed-role ARN, validated synthetic Flag, and bucket-wide access denial; it
never prints temporary credentials or the web identity token.

```bash
kubectl apply -f lab/stages/stage-05-iam-probe/serviceaccount.yaml
kubectl -n stage-05-runtime annotate serviceaccount runtime-builder-iam \
  eks.amazonaws.com/role-arn="$ROLE_ARN" --overwrite
kubectl apply -f lab/stages/stage-05-iam-probe/network-policy.yaml
sed -e "s/__PROOF_BUCKET__/$BUCKET/g" \
    -e "s/__AWS_REGION__/$REGION/g" \
  lab/stages/stage-05-iam-probe/job.yaml.in | kubectl apply -f -
kubectl -n stage-05-runtime wait --for=condition=complete \
  job/runtime-builder-irsa-probe --timeout=5m
kubectl -n stage-05-runtime logs job/runtime-builder-irsa-probe
```

The temporary Job is automatically removed one hour after completion. The
ServiceAccount and NetworkPolicy are retained for the next app integration step;
they do not affect the existing socket workload. If the probe fails, inspect
`kubectl -n stage-05-runtime describe job runtime-builder-irsa-probe` and the Pod
events before changing any IAM permissions.

The first probe image pin accidentally selected the `linux/arm64` manifest and
failed with `exec format error` on an `amd64` general worker before making any
AWS calls. The reviewed template now pins the `linux/amd64` manifest and node
architecture. To rerun only the probe after updating this source:

```bash
kubectl -n stage-05-runtime delete job runtime-builder-irsa-probe --ignore-not-found
sed -e "s/__PROOF_BUCKET__/$BUCKET/g" \
    -e "s/__AWS_REGION__/$REGION/g" \
  lab/stages/stage-05-iam-probe/job.yaml.in | kubectl apply -f -
kubectl -n stage-05-runtime wait --for=condition=complete \
  job/runtime-builder-irsa-probe --timeout=5m
kubectl -n stage-05-runtime logs job/runtime-builder-irsa-probe
```

## Interpretation

A successful Job demonstrates only that this ServiceAccount can assume its IRSA
role and read the fixed synthetic S3 object. It does **not** demonstrate command
injection, Stage 4 gating, participant access, or node compromise. Those claims
require the later runtime-builder app implementation and public-EIP test.

Before the participant exercise, replace the known placeholder with a newly
generated **synthetic** Flag. Keep it only in the private S3 object and the
operator's local validation notes, not in Git, Terraform state, or app manifests.
An unknown Flag is necessary for an observed participant response to demonstrate
that the S3 object was actually read instead of a public placeholder being
written into the Pod's proof file.
