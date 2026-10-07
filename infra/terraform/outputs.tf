output "account_id" {
  description = "AWS account validated by the provider and check block."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS region containing the lab."
  value       = var.aws_region
}

output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API endpoint."
  value       = module.eks.cluster_endpoint
}

output "kubernetes_service_ip" {
  description = "Stable Kubernetes API Service IP used by restricted workload egress policies."
  value       = local.kubernetes_service_ip
}

output "vpc_id" {
  description = "Dedicated lab VPC."
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "Dedicated lab VPC CIDR used by the controller webhook policy."
  value       = var.vpc_cidr
}

output "private_subnet_ids" {
  description = "Private subnets used by both managed node groups."
  value       = module.vpc.private_subnets
}

output "modelgate_public_access_enabled" {
  description = "Whether Terraform created the optional public ModelGate access prerequisites."
  value       = var.enable_modelgate_public_access
}

output "modelgate_public_eip" {
  description = "Single participant-facing IPv4 address for the ModelGate NLB."
  value       = try(aws_eip.modelgate_public[0].public_ip, null)
}

output "modelgate_public_eip_allocation_id" {
  description = "Allocation ID attached to the single-AZ ModelGate NLB."
  value       = try(aws_eip.modelgate_public[0].allocation_id, null)
}

output "modelgate_public_subnet_id" {
  description = "Single public subnet selected for the deliberately non-HA lab NLB."
  value       = var.enable_modelgate_public_access ? module.vpc.public_subnets[0] : null
}

output "modelgate_public_subnet_cidr" {
  description = "CIDR used only for NLB health-check ingress to ModelGate."
  value       = var.enable_modelgate_public_access ? local.public_subnets[0] : null
}

output "modelgate_participant_access_cidrs" {
  description = "Reviewed participant /32 allowlist rendered into the NLB and NetworkPolicy."
  value       = var.enable_modelgate_public_access ? var.participant_access_cidrs : []
}

output "aws_load_balancer_controller_role_arn" {
  description = "Pod Identity role used only by the optional AWS Load Balancer Controller."
  value       = try(module.aws_load_balancer_controller_pod_identity[0].iam_role_arn, null)
}

output "runtime_builder_irsa_role_arn" {
  description = "IAM role trusted only by the Stage 5 runtime-builder ServiceAccount."
  value       = aws_iam_role.runtime_builder.arn
}

output "runtime_proof_bucket" {
  description = "Private lab-only S3 bucket. Terraform does not manage its proof object."
  value       = aws_s3_bucket.runtime_proof.bucket
}

output "runtime_proof_object_key" {
  description = "Synthetic proof object key for the legacy Pod IRSA and opt-in node IAM profiles."
  value       = local.runtime_proof_object_key
}

output "escape_node_role_arn" {
  description = "Instance-profile role of the isolated escape worker for the replacement capstone."
  value       = module.eks.eks_managed_node_groups["escape"].iam_role_arn
}

output "hostpath_node_capstone_enabled" {
  description = "Whether the escape node role has the single-object synthetic S3 permission."
  value       = var.enable_hostpath_node_capstone
}

output "node_security_group_ids" {
  description = "Distinct security-group boundaries for the general and escape workers."
  value = {
    general = aws_security_group.general_nodes.id
    escape  = aws_security_group.escape_nodes.id
  }
}

output "cluster_operator_role_arn" {
  description = "Role used for kubectl access through an EKS Access Entry."
  value       = aws_iam_role.cluster_operator.arn
}

output "assume_operator_command" {
  description = "Read-only hint; credentials are never stored in Terraform state."
  value       = "aws sts assume-role --role-arn ${aws_iam_role.cluster_operator.arn} --role-session-name vuln-mlops-operator"
}

output "update_kubeconfig_command" {
  description = "Command to configure kubectl after assuming the operator role."
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name} --role-arn ${aws_iam_role.cluster_operator.arn}"
}
