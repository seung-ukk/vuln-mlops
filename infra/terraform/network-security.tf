resource "aws_security_group" "eks_control_plane" {
  name                   = "${local.name}-control-plane"
  description            = "Control-plane boundary for the isolated vuln-mlops EKS lab"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name = "${local.name}-control-plane"
  }
}

resource "aws_security_group" "general_nodes" {
  name                   = "${local.name}-general-nodes"
  description            = "General worker boundary for Stage 1 through Stage 4"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name                                  = "${local.name}-general-nodes"
    "kubernetes.io/cluster/${local.name}" = "owned"
    "lab.vuln-mlops/node-role"            = "general"
  }
}

resource "aws_security_group" "escape_nodes" {
  name                   = "${local.name}-escape-nodes"
  description            = "Isolated Stage 5 escape worker boundary"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name                                  = "${local.name}-escape-nodes"
    "kubernetes.io/cluster/${local.name}" = "owned"
    "lab.vuln-mlops/node-role"            = "escape"
  }
}

locals {
  node_security_groups = {
    general = aws_security_group.general_nodes.id
    escape  = aws_security_group.escape_nodes.id
  }

  control_plane_to_nodes = {
    general_https   = { security_group_id = aws_security_group.general_nodes.id, port = 443 }
    general_kubelet = { security_group_id = aws_security_group.general_nodes.id, port = 10250 }
    escape_https    = { security_group_id = aws_security_group.escape_nodes.id, port = 443 }
    escape_kubelet  = { security_group_id = aws_security_group.escape_nodes.id, port = 10250 }
  }

  escape_dns_rules = {
    tcp = "tcp"
    udp = "udp"
  }
}

resource "aws_vpc_security_group_ingress_rule" "cluster_api_from_nodes" {
  for_each = local.node_security_groups

  security_group_id            = aws_security_group.eks_control_plane.id
  referenced_security_group_id = each.value
  description                  = "${each.key} nodes to Kubernetes API"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_vpc_security_group_egress_rule" "control_plane_to_nodes" {
  for_each = local.control_plane_to_nodes

  security_group_id            = aws_security_group.eks_control_plane.id
  referenced_security_group_id = each.value.security_group_id
  description                  = "Control plane to ${each.key}"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

resource "aws_vpc_security_group_ingress_rule" "nodes_from_control_plane" {
  for_each = local.control_plane_to_nodes

  security_group_id            = each.value.security_group_id
  referenced_security_group_id = aws_security_group.eks_control_plane.id
  description                  = "${each.key} from control plane"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

resource "aws_vpc_security_group_egress_rule" "control_plane_to_lbc_webhook" {
  count = var.enable_modelgate_public_access ? 1 : 0

  security_group_id            = aws_security_group.eks_control_plane.id
  referenced_security_group_id = aws_security_group.general_nodes.id
  description                  = "Control plane to AWS Load Balancer Controller webhook"
  ip_protocol                  = "tcp"
  from_port                    = 9443
  to_port                      = 9443
}

resource "aws_vpc_security_group_ingress_rule" "general_nodes_from_lbc_webhook" {
  count = var.enable_modelgate_public_access ? 1 : 0

  security_group_id            = aws_security_group.general_nodes.id
  referenced_security_group_id = aws_security_group.eks_control_plane.id
  description                  = "AWS Load Balancer Controller webhook from control plane"
  ip_protocol                  = "tcp"
  from_port                    = 9443
  to_port                      = 9443
}

resource "aws_vpc_security_group_ingress_rule" "general_node_tcp" {
  security_group_id            = aws_security_group.general_nodes.id
  referenced_security_group_id = aws_security_group.general_nodes.id
  description                  = "General worker and Pod TCP traffic"
  ip_protocol                  = "tcp"
  from_port                    = 1025
  to_port                      = 65535
}

resource "aws_vpc_security_group_ingress_rule" "general_dns" {
  for_each = {
    general_tcp = { source = aws_security_group.general_nodes.id, protocol = "tcp" }
    general_udp = { source = aws_security_group.general_nodes.id, protocol = "udp" }
    escape_tcp  = { source = aws_security_group.escape_nodes.id, protocol = "tcp" }
    escape_udp  = { source = aws_security_group.escape_nodes.id, protocol = "udp" }
  }

  security_group_id            = aws_security_group.general_nodes.id
  referenced_security_group_id = each.value.source
  description                  = "Cluster DNS from ${each.key}"
  ip_protocol                  = each.value.protocol
  from_port                    = 53
  to_port                      = 53
}

resource "aws_vpc_security_group_egress_rule" "general_all" {
  security_group_id = aws_security_group.general_nodes.id
  description       = "General workers require normal cluster and registry egress"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "escape_https" {
  security_group_id = aws_security_group.escape_nodes.id
  description       = "Escape worker bootstrap, EKS API, registry, and AWS API HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "escape_dns" {
  for_each = local.escape_dns_rules

  security_group_id            = aws_security_group.escape_nodes.id
  referenced_security_group_id = aws_security_group.general_nodes.id
  description                  = "Escape worker to cluster DNS over ${each.key}"
  ip_protocol                  = each.value
  from_port                    = 53
  to_port                      = 53
}
