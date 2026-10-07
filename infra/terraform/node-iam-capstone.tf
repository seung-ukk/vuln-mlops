# The replacement capstone uses the escape worker instance profile, not the
# runtime-builder Pod IRSA role. This is deliberately opt-in until the legacy
# workload is removed and the node is replaced for the new profile.
data "aws_iam_policy_document" "escape_node_s3_proof" {
  statement {
    sid       = "ReadOnlySyntheticProofObject"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.runtime_proof.arn}/${local.runtime_proof_object_key}"]
  }
}

resource "aws_iam_role_policy" "escape_node_s3_proof" {
  count  = var.enable_hostpath_node_capstone ? 1 : 0
  name   = "read-synthetic-node-proof"
  role   = module.eks.eks_managed_node_groups["escape"].iam_role_name
  policy = data.aws_iam_policy_document.escape_node_s3_proof.json
}
