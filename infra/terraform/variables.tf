variable "expected_account_id" {
  description = "Twelve-digit AWS account that is allowed to receive this lab."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a twelve-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for the isolated lab."
  type        = string
  default     = "ap-northeast-2"
}

variable "lab_id" {
  description = "Short identifier used in names and required lab-boundary tags."
  type        = string
  default     = "vuln-mlops"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.lab_id))
    error_message = "lab_id must be 3-24 lowercase alphanumeric or hyphen characters."
  }
}

variable "environment" {
  description = "Environment tag. Use a separate value and state for each AWS account."
  type        = string
  default     = "personal-lab"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version. 1.36 is the reviewed default; 1.37 remains opt-in."
  type        = string
  default     = "1.36"

  validation {
    condition     = contains(["1.36", "1.37"], var.kubernetes_version)
    error_message = "Use a currently reviewed EKS standard-support version: 1.36 or 1.37."
  }
}

variable "vpc_cidr" {
  description = "Dedicated VPC CIDR for the lab."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr)) && tonumber(split("/", var.vpc_cidr)[1]) <= 20
    error_message = "vpc_cidr must be a valid IPv4 CIDR with enough room for the lab subnets."
  }
}

variable "availability_zone_count" {
  description = "Number of AZs used for public and private subnets."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count >= 2 && var.availability_zone_count <= 3
    error_message = "Use two or three availability zones."
  }
}

variable "public_access_cidrs" {
  description = "Exact operator public IPv4 /32 CIDRs allowed to reach the EKS API."
  type        = list(string)

  validation {
    condition = (
      length(var.public_access_cidrs) > 0 &&
      alltrue([for cidr in var.public_access_cidrs : can(cidrhost(cidr, 0)) && endswith(cidr, "/32")]) &&
      !contains(var.public_access_cidrs, "0.0.0.0/0")
    )
    error_message = "Provide at least one operator IPv4 /32; broad public CIDRs are forbidden."
  }
}

variable "enable_modelgate_public_access" {
  description = "Create the single-EIP infrastructure used by the optional ModelGate public NLB."
  type        = bool
  default     = false
}

variable "participant_access_cidrs" {
  description = "Exact participant public IPv4 /32 CIDRs allowed to reach the ModelGate NLB."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for cidr in var.participant_access_cidrs :
      can(cidrhost(cidr, 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", cidr)) &&
      endswith(cidr, "/32") &&
      cidr != "0.0.0.0/0"
    ])
    error_message = "Every participant CIDR must be an exact public IPv4 /32; broad CIDRs are forbidden."
  }
}

variable "general_instance_types" {
  description = "On-demand instance types for normal Stage 1-4 workloads."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "escape_instance_types" {
  description = "On-demand instance types for the isolated Stage 5 escape node."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "enable_hostpath_node_capstone" {
  description = "Opt in to the replacement hostPath lab's single-object S3 permission on the isolated escape worker role. Do not enable until the legacy runtime agent and Pod IRSA path are removed."
  type        = bool
  default     = false
}

variable "general_desired_size" {
  description = "Desired general worker count."
  type        = number
  default     = 2

  validation {
    condition     = var.general_desired_size >= 1 && var.general_desired_size <= 4
    error_message = "general_desired_size must be between one and four."
  }
}

variable "log_retention_days" {
  description = "CloudWatch retention for EKS control-plane logs."
  type        = number
  default     = 14
}

variable "deletion_protection" {
  description = "Protect the EKS cluster from accidental deletion; disable before a planned lab destroy."
  type        = bool
  default     = false
}

variable "enable_coredns_addon" {
  description = "Whether Terraform manages CoreDNS. The bootstrap script defers it until the strict-mode NetworkPolicy exists."
  type        = bool
  default     = true
}
