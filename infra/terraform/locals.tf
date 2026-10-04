data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name                  = "${var.lab_id}-${var.environment}"
  azs                   = slice(data.aws_availability_zones.available.names, 0, var.availability_zone_count)
  service_ipv4_cidr     = "172.20.0.0/16"
  kubernetes_service_ip = cidrhost(local.service_ipv4_cidr, 1)

  private_subnets = [
    for index, az in local.azs : cidrsubnet(var.vpc_cidr, 4, index)
  ]
  public_subnets = [
    for index, az in local.azs : cidrsubnet(var.vpc_cidr, 4, index + 8)
  ]

  common_tags = {
    Project     = "vuln-mlops"
    LabId       = var.lab_id
    Environment = var.environment
    ManagedBy   = "terraform"
    Boundary    = "isolated-security-lab"
  }
}

check "target_account" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == var.expected_account_id
    error_message = "The active AWS credential does not match expected_account_id."
  }
}

check "availability_zones" {
  assert {
    condition     = length(data.aws_availability_zones.available.names) >= var.availability_zone_count
    error_message = "The selected region does not expose enough available zones."
  }
}
