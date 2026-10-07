# The IAM proof is separate from the existing socket workload until its app
# replacement has been validated. Terraform never manages the object's body.
locals {
  runtime_proof_bucket_name = "${var.lab_id}-${var.environment}-${var.expected_account_id}-runtime-proof"
  runtime_proof_object_key  = "proof/final-flag.txt"
  eks_oidc_issuer           = trimprefix(module.eks.cluster_oidc_issuer_url, "https://")
}

check "runtime_proof_bucket_name" {
  assert {
    condition = (
      length(local.runtime_proof_bucket_name) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", local.runtime_proof_bucket_name))
    )
    error_message = "The lab_id and environment combination must form a valid S3 bucket name of at most 63 characters."
  }
}

resource "aws_s3_bucket" "runtime_proof" {
  bucket        = local.runtime_proof_bucket_name
  force_destroy = true

  tags = {
    Purpose = "synthetic-runtime-iam-proof"
  }
}

resource "aws_s3_bucket_public_access_block" "runtime_proof" {
  bucket = aws_s3_bucket.runtime_proof.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "runtime_proof" {
  bucket = aws_s3_bucket.runtime_proof.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "runtime_builder_assume_role" {
  statement {
    sid     = "OnlyRuntimeBuilderServiceAccount"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.eks_oidc_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.eks_oidc_issuer}:sub"
      values   = ["system:serviceaccount:stage-05-runtime:runtime-builder-iam"]
    }
  }
}

resource "aws_iam_role" "runtime_builder" {
  name               = "${local.name}-runtime-builder"
  description        = "Synthetic S3 proof identity for the runtime-builder lab workload"
  assume_role_policy = data.aws_iam_policy_document.runtime_builder_assume_role.json
}

data "aws_iam_policy_document" "runtime_builder_proof" {
  statement {
    sid       = "ReadOnlySyntheticProofObject"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.runtime_proof.arn}/${local.runtime_proof_object_key}"]
  }
}

resource "aws_iam_role_policy" "runtime_builder_proof" {
  count  = var.enable_hostpath_node_capstone ? 0 : 1
  name   = "read-synthetic-runtime-proof"
  role   = aws_iam_role.runtime_builder.id
  policy = data.aws_iam_policy_document.runtime_builder_proof.json
}

# Preserve the old singleton's state address during the profile transition.
moved {
  from = aws_iam_role_policy.runtime_builder_proof
  to   = aws_iam_role_policy.runtime_builder_proof[0]
}
