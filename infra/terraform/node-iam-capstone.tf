# The participant capstone uses the dedicated worker's instance profile. The
# launch template applies the node-role tag to EC2 instances, not just the EKS
# node group. Keep this opt-in until the old Pod IRSA workload is removed.
data "aws_iam_policy_document" "escape_node_tag_proof" {
  statement {
    sid       = "WriteOnlyDedicatedNodeProofTag"
    actions   = ["ec2:CreateTags"]
    resources = ["arn:aws:ec2:${var.aws_region}:${var.expected_account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "ec2:ResourceTag/lab.vuln-mlops/node-role"
      values   = ["escape"]
    }

    condition {
      test     = "StringLike"
      variable = "aws:RequestTag/lab.vuln-mlops/proof"
      values   = ["lab-*"]
    }

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "aws:TagKeys"
      values   = ["lab.vuln-mlops/proof"]
    }

    condition {
      test     = "Null"
      variable = "aws:RequestTag/lab.vuln-mlops/proof"
      values   = ["false"]
    }
  }
}

resource "aws_iam_role_policy" "escape_node_tag_proof" {
  count  = var.enable_hostpath_node_capstone ? 1 : 0
  name   = "write-dedicated-node-proof-tag"
  role   = module.eks.eks_managed_node_groups["escape"].iam_role_name
  policy = data.aws_iam_policy_document.escape_node_tag_proof.json
}
