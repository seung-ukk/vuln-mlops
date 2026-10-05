from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TF_DIR = ROOT / "infra" / "terraform"
ACCESS_DIR = ROOT / "deploy" / "eks-access"


def render_documents() -> list[dict]:
    text = (ACCESS_DIR / "modelgate-public.yaml.tpl").read_text()
    text = text.replace("__PUBLIC_SUBNET_ID__", "subnet-0123456789abcdef0")
    text = text.replace("__EIP_ALLOCATION_ID__", "eipalloc-0123456789abcdef0")
    text = text.replace("__LOAD_BALANCER_SOURCE_RANGES__", '    - "198.51.100.25/32"')
    text = text.replace(
        "__MODELGATE_INGRESS_IPBLOCKS__",
        "        - ipBlock:\n"
        "            cidr: 198.51.100.25/32\n"
        "        - ipBlock:\n"
        "            cidr: 10.42.128.0/20",
    )
    return list(yaml.safe_load_all(text))


def test_public_access_is_opt_in_and_rejects_broad_participant_cidrs() -> None:
    variables = (TF_DIR / "variables.tf").read_text()
    locals = (TF_DIR / "locals.tf").read_text()

    assert 'variable "enable_modelgate_public_access"' in variables
    assert "default     = false" in variables
    assert 'cidr != "0.0.0.0/0"' in variables
    assert 'endswith(cidr, "/32")' in variables
    assert 'can(regex("^([0-9]{1,3}\\\\.){3}[0-9]{1,3}/32$", cidr))' in variables
    assert 'check "modelgate_participant_boundary"' in locals
    assert "length(var.participant_access_cidrs) > 0" in locals


def test_only_modelgate_is_published_and_internal_service_stays_clusterip() -> None:
    service, _ = render_documents()
    base_service = yaml.safe_load((ROOT / "deploy" / "base" / "service.yaml").read_text())
    template = (ACCESS_DIR / "modelgate-public.yaml.tpl").read_text()

    assert service["spec"]["selector"] == {"app.kubernetes.io/name": "modelgate"}
    assert base_service["spec"]["type"] == "ClusterIP"
    for forbidden in ("grafana", "prometheus", "gitea", "argocd", "credential-broker", "mlflow"):
        assert forbidden not in template.lower()


def test_participant_and_healthcheck_sources_are_the_only_public_policy_inputs() -> None:
    _, policy = render_documents()
    ingress = policy["spec"]["ingress"]
    cidrs = [entry["ipBlock"]["cidr"] for entry in ingress[0]["from"]]

    assert cidrs == ["198.51.100.25/32", "10.42.128.0/20"]
    assert "0.0.0.0/0" not in cidrs
    assert ingress[0]["ports"] == [{"protocol": "TCP", "port": 8080}]


def test_access_endpoint_has_no_https_or_certificate_shortcut() -> None:
    service, _ = render_documents()
    annotations = service["metadata"]["annotations"]

    assert service["spec"]["ports"][0]["port"] == 80
    assert not any("ssl" in key or "certificate" in key for key in annotations)


def test_teardown_removes_service_before_controller_and_keeps_eip_for_terraform() -> None:
    script = (ACCESS_DIR / "manage.sh").read_text()
    service_delete = script.index("delete service modelgate-public")
    detach_wait = script.index("wait_for_eip_disassociation", service_delete)
    helm_uninstall = script.index('helm uninstall "$LBC_RELEASE"', detach_wait)

    assert service_delete < detach_wait < helm_uninstall
    assert "aws ec2 release-address" not in script
    assert "Run terraform destroy to release the EIP" in script
    assert "unpin_modelgate_from_nlb_zone" in script
    assert '"topology.kubernetes.io/zone":null' in script
    assert '\"maxSurge\":\"25%\"' in script
    assert '\"maxUnavailable\":\"25%\"' in script


def test_webhook_security_group_rules_are_conditional_and_general_only() -> None:
    network = (TF_DIR / "network-security.tf").read_text()

    assert 'resource "aws_vpc_security_group_egress_rule" "control_plane_to_lbc_webhook"' in network
    assert 'resource "aws_vpc_security_group_ingress_rule" "general_nodes_from_lbc_webhook"' in network
    assert network.count("count = var.enable_modelgate_public_access ? 1 : 0") >= 2
    assert "referenced_security_group_id = aws_security_group.general_nodes.id" in network
    assert "from_port                    = 9443" in network
    assert "aws_security_group.escape_nodes.id" not in network[
        network.index('resource "aws_vpc_security_group_egress_rule" "control_plane_to_lbc_webhook"') :
        network.index('resource "aws_vpc_security_group_ingress_rule" "general_node_tcp"')
    ]
