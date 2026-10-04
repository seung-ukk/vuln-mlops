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

output "private_subnet_ids" {
  description = "Private subnets used by both managed node groups."
  value       = module.vpc.private_subnets
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
