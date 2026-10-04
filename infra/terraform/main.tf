module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.7.3"

  name = local.name
  cidr = var.vpc_cidr
  azs  = local.azs

  private_subnets = local.private_subnets
  public_subnets  = local.public_subnets

  enable_dns_support   = true
  enable_dns_hostnames = true

  enable_nat_gateway = true
  single_nat_gateway = true

  map_public_ip_on_launch = false

  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}

data "aws_iam_policy_document" "operator_assume_role" {
  statement {
    sid     = "AccountOperatorAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.expected_account_id}:root"]
    }
  }
}

resource "aws_iam_role" "cluster_operator" {
  name               = "${local.name}-cluster-operator"
  description        = "Temporary operator identity for the isolated vuln-mlops EKS lab"
  assume_role_policy = data.aws_iam_policy_document.operator_assume_role.json

  max_session_duration = 14400
}

data "aws_iam_policy_document" "cluster_operator" {
  statement {
    sid       = "DescribeOnlyThisLabCluster"
    actions   = ["eks:DescribeCluster"]
    resources = [module.eks.cluster_arn]
  }
}

resource "aws_iam_role_policy" "cluster_operator" {
  name   = "describe-lab-cluster"
  role   = aws_iam_role.cluster_operator.id
  policy = data.aws_iam_policy_document.cluster_operator.json
}

module "vpc_cni_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "2.9.0"

  name = "${local.name}-vpc-cni"

  attach_aws_vpc_cni_policy = true
  aws_vpc_cni_enable_ipv4   = true
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "21.26.0"

  name               = local.name
  kubernetes_version = var.kubernetes_version
  service_ipv4_cidr  = local.service_ipv4_cidr

  authentication_mode                      = "API"
  enable_cluster_creator_admin_permissions = false
  enable_irsa                              = false
  endpoint_private_access                  = true
  endpoint_public_access                   = true
  endpoint_public_access_cidrs             = var.public_access_cidrs
  deletion_protection                      = var.deletion_protection
  enabled_log_types                        = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  cloudwatch_log_group_retention_in_days   = var.log_retention_days
  cloudwatch_log_group_class               = "STANDARD"
  kms_key_administrators                   = ["arn:aws:iam::${var.expected_account_id}:root"]

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  create_security_group      = false
  security_group_id          = aws_security_group.eks_control_plane.id
  create_node_security_group = false

  addons = merge(
    {
      eks-pod-identity-agent = {
        before_compute = true
        most_recent    = true
      }
      kube-proxy = {
        most_recent = true
      }
      vpc-cni = {
        before_compute = true
        most_recent    = true
        configuration_values = jsonencode({
          enableNetworkPolicy = "true"
          env = {
            NETWORK_POLICY_ENFORCING_MODE = "strict"
          }
        })
        pod_identity_association = [{
          role_arn        = module.vpc_cni_pod_identity.iam_role_arn
          service_account = "aws-node"
        }]
      }
    },
    var.enable_coredns_addon ? {
      coredns = {
        most_recent = true
      }
    } : {}
  )

  access_entries = {
    operator = {
      principal_arn = aws_iam_role.cluster_operator.arn
      policy_associations = {
        cluster_admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }

  eks_managed_node_groups = {
    general = {
      name                       = "${local.name}-general"
      ami_type                   = "AL2023_x86_64_STANDARD"
      capacity_type              = "ON_DEMAND"
      instance_types             = var.general_instance_types
      disk_size                  = 30
      min_size                   = 1
      max_size                   = 4
      desired_size               = var.general_desired_size
      iam_role_attach_cni_policy = false
      iam_role_name              = "${var.lab_id}-general-node"
      iam_role_use_name_prefix   = false
      vpc_security_group_ids     = [aws_security_group.general_nodes.id]

      metadata_options = {
        http_endpoint               = "enabled"
        http_protocol_ipv6          = "disabled"
        http_put_response_hop_limit = 1
        http_tokens                 = "required"
        instance_metadata_tags      = "disabled"
      }

      update_config = {
        max_unavailable_percentage = 50
      }

      labels = {
        "lab.vuln-mlops/node-role" = "general"
      }

      tags = {
        "lab.vuln-mlops/node-role" = "general"
      }
    }

    escape = {
      name                       = "${local.name}-escape"
      ami_type                   = "AL2023_x86_64_STANDARD"
      capacity_type              = "ON_DEMAND"
      instance_types             = var.escape_instance_types
      disk_size                  = 30
      min_size                   = 1
      max_size                   = 1
      desired_size               = 1
      iam_role_attach_cni_policy = false
      iam_role_name              = "${var.lab_id}-escape-node"
      iam_role_use_name_prefix   = false
      vpc_security_group_ids     = [aws_security_group.escape_nodes.id]

      metadata_options = {
        http_endpoint               = "enabled"
        http_protocol_ipv6          = "disabled"
        http_put_response_hop_limit = 1
        http_tokens                 = "required"
        instance_metadata_tags      = "disabled"
      }

      update_config = {
        max_unavailable = 1
      }

      labels = {
        "lab.vuln-mlops/node-role" = "escape"
      }

      taints = {
        isolated = {
          key    = "lab.vuln-mlops/escape"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      }

      tags = {
        "lab.vuln-mlops/node-role" = "escape"
      }
    }
  }
}
