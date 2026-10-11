resource "aws_security_group" "attacker_receiver" {
  count                  = var.enable_attacker_receiver_security_group ? 1 : 0
  name                   = "${local.name}-attacker-receiver"
  description            = "Dedicated, no-IAM lab attacker EC2 receiver"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name                     = "${local.name}-attacker-receiver"
    "lab.vuln-mlops/purpose" = "participant-receiver"
  }
}

resource "aws_vpc_security_group_ingress_rule" "attacker_receiver_from_general" {
  count                        = var.enable_attacker_receiver_security_group ? 1 : 0
  security_group_id            = aws_security_group.attacker_receiver[0].id
  referenced_security_group_id = aws_security_group.general_nodes.id
  description                  = "ModelGate validator Pod reverse connection on any TCP port"
  ip_protocol                  = "tcp"
  from_port                    = 1
  to_port                      = 65535
}

resource "aws_vpc_security_group_ingress_rule" "attacker_receiver_ssh" {
  for_each          = var.enable_attacker_receiver_security_group ? toset(var.participant_access_cidrs) : toset([])
  security_group_id = aws_security_group.attacker_receiver[0].id
  description       = "Team SSH to dedicated attacker EC2"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "attacker_receiver_egress" {
  count             = var.enable_attacker_receiver_security_group ? 1 : 0
  security_group_id = aws_security_group.attacker_receiver[0].id
  description       = "Attacker workstation outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
