from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TF = ROOT / "infra" / "terraform"


def terraform_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(TF.glob("*.tf")))


def coredns_policy() -> dict:
    path = ROOT / "deploy" / "eks-lab" / "coredns-network-policy.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_account_and_public_endpoint_are_bounded() -> None:
    versions = (TF / "versions.tf").read_text(encoding="utf-8")
    variables = (TF / "variables.tf").read_text(encoding="utf-8")
    assert "allowed_account_ids = [var.expected_account_id]" in versions
    assert 'endswith(cidr, "/32")' in variables
    assert '!contains(var.public_access_cidrs, "0.0.0.0/0")' in variables


def test_nodes_have_no_stage6_storage_permissions() -> None:
    text = terraform_text()
    assert "enable_irsa                              = false" in text
    forbidden = [
        "AmazonEBSCSIDriverPolicy",
        "ec2:AttachVolume",
        "ec2:CreateSnapshot",
        "elasticfilesystem:",
        "kms:Decrypt",
        "s3:GetObject",
    ]
    for permission in forbidden:
        assert permission not in text


def test_kms_administrator_does_not_follow_the_current_terraform_caller() -> None:
    main = (TF / "main.tf").read_text(encoding="utf-8")
    assert 'kms_key_administrators                   = ["arn:aws:iam::${var.expected_account_id}:root"]' in main
    assert "data.aws_iam_session_context" not in main


def test_instance_metadata_and_logs_are_bounded() -> None:
    text = terraform_text()
    assert 'http_tokens                 = "required"' in text
    assert "http_put_response_hop_limit = 1" in text
    assert 'instance_metadata_tags      = "disabled"' in text
    for log_type in ["api", "audit", "authenticator", "controllerManager", "scheduler"]:
        assert log_type in text


def test_eks_overlay_does_not_restore_imds_or_private_wildcards() -> None:
    overlay = (ROOT / "deploy" / "eks-lab" / "kustomization.yaml").read_text(encoding="utf-8")
    assert "169.254.169.254" not in overlay
    assert "10.0.0.0/8" not in overlay
    assert "0.0.0.0/0" not in overlay


def test_escape_worker_does_not_share_the_general_node_security_group() -> None:
    main = (TF / "main.tf").read_text(encoding="utf-8")
    network = (TF / "network-security.tf").read_text(encoding="utf-8")
    assert "depends_on = [" not in main
    assert "create_node_security_group = false" in main
    assert "node_security_group_enable_recommended_rules" not in main
    assert main.count("vpc_security_group_ids     = [aws_security_group.general_nodes.id]") == 1
    assert main.count("vpc_security_group_ids     = [aws_security_group.escape_nodes.id]") == 1
    assert 'resource "aws_security_group" "general_nodes"' in network
    assert 'resource "aws_security_group" "escape_nodes"' in network


def test_escape_worker_has_no_general_lateral_ingress_or_unrestricted_egress() -> None:
    network = (TF / "network-security.tf").read_text(encoding="utf-8")
    ingress_resources = "\n".join(
        block
        for block in network.split('resource "')
        if block.startswith("aws_vpc_security_group_ingress_rule")
    )
    assert 'resource "aws_vpc_security_group_egress_rule" "escape_https"' in network
    assert 'resource "aws_vpc_security_group_egress_rule" "escape_dns"' in network
    assert 'resource "aws_vpc_security_group_egress_rule" "escape_all"' not in network
    assert "security_group_id            = aws_security_group.escape_nodes.id" not in ingress_resources
    assert "referenced_security_group_id = aws_security_group.eks_control_plane.id" in ingress_resources


def test_coredns_bootstrap_policy_does_not_open_other_pods_or_arbitrary_ports() -> None:
    policy = coredns_policy()
    spec = policy["spec"]
    assert spec["podSelector"]["matchLabels"]
    assert set(spec["policyTypes"]) == {"Ingress", "Egress"}
    assert all(rule and "ports" in rule for rule in spec["ingress"] + spec["egress"])
    assert "ipBlock" not in str(spec)
    assert {port["port"] for port in spec["egress"][0]["ports"]} == {53, 443}

    overlay = yaml.safe_load(
        (ROOT / "deploy" / "eks-lab" / "kustomization.yaml").read_text(encoding="utf-8")
    )
    assert overlay["resources"].count("coredns-network-policy.yaml") == 1


def test_bootstrap_rejects_privileged_shortcuts_and_is_resume_safe() -> None:
    script = (TF / "bootstrap.sh").read_text(encoding="utf-8")

    assert '[[ -z "${AWS_PROFILE:-}" ]]' in script
    assert "get-caller-identity" in script
    assert "== *':root'" in script
    assert "-target" not in script
    assert 'kubectl apply -f "$COREDNS_POLICY"' in script
    assert "kubectl apply -k" not in script
    assert 'if ! tf state list 2>/dev/null | grep -Fqx "$COREDNS_ADDRESS"' in script
    assert 'tf apply -input=false "$PHASE1_PLAN"' in script
    assert 'tf apply -input=false "$PHASE2_PLAN"' in script
    assert "AWS_SECRET_ACCESS_KEY" not in script
    assert "AWS_SESSION_TOKEN" not in script
