from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TF = ROOT / "infra" / "terraform"
PROBE = ROOT / "lab" / "stages" / "stage-05-iam-probe"


def test_runtime_builder_role_trusts_only_its_service_account() -> None:
    text = (TF / "runtime-builder-iam.tf").read_text(encoding="utf-8")
    assert 'actions = ["sts:AssumeRoleWithWebIdentity"]' in text
    assert 'values   = ["sts.amazonaws.com"]' in text
    assert 'values   = ["system:serviceaccount:stage-05-runtime:runtime-builder-iam"]' in text
    assert 'identifiers = [module.eks.oidc_provider_arn]' in text


def test_runtime_builder_can_read_only_the_synthetic_object() -> None:
    text = (TF / "runtime-builder-iam.tf").read_text(encoding="utf-8")
    assert 'runtime_proof_object_key  = "proof/final-flag.txt"' in text
    assert 'actions   = ["s3:GetObject"]' in text
    assert 'resources = ["${aws_s3_bucket.runtime_proof.arn}/${local.runtime_proof_object_key}"]' in text
    assert 'resource "aws_s3_bucket_public_access_block" "runtime_proof"' in text
    assert 'resource "aws_s3_object"' not in text
    assert 'FLAG{stage_5_iam_' not in text


def test_probe_uses_exact_irsa_identity_and_synthetic_proof() -> None:
    service_account = yaml.safe_load((PROBE / "serviceaccount.yaml").read_text(encoding="utf-8"))
    job = yaml.safe_load((PROBE / "job.yaml.in").read_text(encoding="utf-8"))
    pod = job["spec"]["template"]["spec"]
    assert service_account["metadata"]["name"] == pod["serviceAccountName"]
    assert service_account["metadata"]["namespace"] == job["metadata"]["namespace"]
    assert pod["nodeSelector"] == {
        "lab.vuln-mlops/node-role": "general",
        "kubernetes.io/arch": "amd64",
    }
    assert pod["automountServiceAccountToken"] is False
    script = pod["containers"][0]["args"][0]
    assert "aws sts get-caller-identity" in script
    assert "aws s3api get-object" in script
    assert "Unexpected proof object shape" in script
    assert "bucket-wide access denied" in script
