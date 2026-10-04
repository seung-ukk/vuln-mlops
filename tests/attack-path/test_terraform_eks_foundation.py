from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TF = ROOT / "infra" / "terraform"
MODELGATE_IMAGE_DIGEST = (
    "sha256:9953d23e8102114873c3a52eaecd0a2e80d260cb0b7ee09ae348c0af3d66a244"
)


def terraform_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(TF.glob("*.tf")))


def coredns_policy() -> dict:
    path = ROOT / "deploy" / "eks-lab" / "coredns-network-policy.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def eks_overlay() -> dict:
    path = ROOT / "deploy" / "eks-lab" / "kustomization.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_stage1_eks_overlay_pins_the_published_modelgate_image() -> None:
    overlay = eks_overlay()
    assert overlay["images"] == [
        {
            "name": "ghcr.io/seung-ukk/vuln-mlops",
            "newName": "ghcr.io/seung-ukk/vuln-mlops",
            "digest": MODELGATE_IMAGE_DIGEST,
        }
    ]

    deployment = yaml.safe_load(
        (ROOT / "deploy" / "base" / "deployment.yaml").read_text(encoding="utf-8")
    )
    containers = deployment["spec"]["template"]["spec"]["containers"]
    assert {container["name"] for container in containers} == {
        "api",
        "mlflow-registry",
        "validator",
    }
    assert {container["image"] for container in containers} == {
        "ghcr.io/seung-ukk/vuln-mlops:main"
    }


def test_eks_foundation_and_overlay_share_the_stage2_api_service_boundary() -> None:
    locals_text = (TF / "locals.tf").read_text(encoding="utf-8")
    main_text = (TF / "main.tf").read_text(encoding="utf-8")
    outputs_text = (TF / "outputs.tf").read_text(encoding="utf-8")
    overlay = eks_overlay()

    assert 'service_ipv4_cidr     = "172.20.0.0/16"' in locals_text
    assert "kubernetes_service_ip = cidrhost(local.service_ipv4_cidr, 1)" in locals_text
    assert "service_ipv4_cidr  = local.service_ipv4_cidr" in main_text
    assert 'output "kubernetes_service_ip"' in outputs_text
    assert "../../lab/stages/stage-02-rbac" in overlay["resources"]


def test_eks_overlay_targets_only_the_two_stage2_api_policies() -> None:
    overlay = eks_overlay()
    patch_targets = {
        item["path"]: item["target"]
        for item in overlay["patches"]
        if "stage-02-api-egress" in item["path"]
    }
    assert patch_targets == {
        "stage-02-api-egress-patch.yaml": {
            "group": "networking.k8s.io",
            "version": "v1",
            "kind": "NetworkPolicy",
            "name": "stage-02-api-egress",
            "namespace": "stage-02-rbac",
        },
        "modelgate-stage-02-api-egress-patch.yaml": {
            "group": "networking.k8s.io",
            "version": "v1",
            "kind": "NetworkPolicy",
            "name": "modelgate-stage-02-api-egress",
            "namespace": "modelgate-lab",
        },
    }


def test_eks_overlay_composes_stage3_with_prometheus_only_api_egress() -> None:
    overlay = eks_overlay()
    assert "../../lab/stages/stage-03-monitoring" in overlay["resources"]
    assert "stage-03-prometheus-api-egress.yaml" in overlay["resources"]

    monitoring_patch = next(
        item
        for item in overlay["patches"]
        if item["path"] == "stage-03-monitoring-flows-patch.yaml"
    )
    assert monitoring_patch["target"] == {
        "group": "networking.k8s.io",
        "version": "v1",
        "kind": "NetworkPolicy",
        "name": "monitoring-flows",
        "namespace": "stage-03-monitoring",
    }

    api_policy = yaml.safe_load(
        (ROOT / "deploy" / "eks-lab" / "stage-03-prometheus-api-egress.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert api_policy["spec"]["podSelector"]["matchLabels"] == {"app": "prometheus"}
    assert api_policy["spec"]["egress"] == [
        {
            "to": [{"ipBlock": {"cidr": "172.20.0.1/32"}}],
            "ports": [{"protocol": "TCP", "port": 443}],
        }
    ]


def test_eks_overlay_composes_stage4_with_controller_only_api_egress() -> None:
    overlay = eks_overlay()
    assert "stage-04" in overlay["resources"]

    stage4_dir = ROOT / "deploy" / "eks-lab" / "stage-04"
    stage4_overlay = yaml.safe_load(
        (stage4_dir / "kustomization.yaml").read_text(encoding="utf-8")
    )
    assert "../../../lab/stages/stage-04-gitops" in stage4_overlay["resources"]
    assert "controller-api-egress.yaml" in stage4_overlay["resources"]

    internal_patch = next(
        item
        for item in stage4_overlay["patches"]
        if item["path"] == "internal-egress-patch.yaml"
    )
    assert internal_patch["target"] == {
        "group": "networking.k8s.io",
        "version": "v1",
        "kind": "NetworkPolicy",
        "name": "stage-04-internal",
        "namespace": "stage-04-gitops",
    }

    api_policy = yaml.safe_load(
        (stage4_dir / "controller-api-egress.yaml").read_text(encoding="utf-8")
    )
    assert api_policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "argocd-application-controller"
    }
    assert api_policy["spec"]["egress"] == [
        {
            "to": [{"ipBlock": {"cidr": "172.20.0.1/32"}}],
            "ports": [{"protocol": "TCP", "port": 443}],
        }
    ]


def test_eks_foundation_has_general_and_escape_workers() -> None:
    text = terraform_text()
    assert 'general = {' in text
    assert 'escape = {' in text
    assert '"lab.vuln-mlops/node-role" = "general"' in text
    assert '"lab.vuln-mlops/node-role" = "escape"' in text
    assert 'key    = "lab.vuln-mlops/escape"' in text
    assert 'effect = "NO_SCHEDULE"' in text
    assert 'iam_role_name              = "${var.lab_id}-general-node"' in text
    assert 'iam_role_name              = "${var.lab_id}-escape-node"' in text
    assert text.count("iam_role_use_name_prefix   = false") == 2
    assert "vpc_security_group_ids     = [aws_security_group.general_nodes.id]" in text
    assert "vpc_security_group_ids     = [aws_security_group.escape_nodes.id]" in text


def test_control_plane_can_reach_both_node_boundaries() -> None:
    network = (TF / "network-security.tf").read_text(encoding="utf-8")
    assert 'general_kubelet = { security_group_id = aws_security_group.general_nodes.id, port = 10250 }' in network
    assert 'escape_kubelet  = { security_group_id = aws_security_group.escape_nodes.id, port = 10250 }' in network
    assert 'resource "aws_vpc_security_group_ingress_rule" "cluster_api_from_nodes"' in network
    assert 'from_port                    = 443' in network


def test_cluster_uses_access_entry_and_managed_addons() -> None:
    text = terraform_text()
    assert 'authentication_mode' in text and '"API"' in text
    assert "enable_cluster_creator_admin_permissions" in text
    assert 'principal_arn = aws_iam_role.cluster_operator.arn' in text
    assert "enable_irsa                              = false" in text
    for addon in ["coredns", "eks-pod-identity-agent", "kube-proxy", "vpc-cni"]:
        assert addon in text


def test_private_workers_and_network_policy_are_enabled() -> None:
    text = terraform_text()
    assert "subnet_ids               = module.vpc.private_subnets" in text
    assert 'enableNetworkPolicy = "true"' in text
    assert 'NETWORK_POLICY_ENFORCING_MODE = "strict"' in text
    assert "iam_role_attach_cni_policy = false" in text


def test_coredns_bootstrap_policy_allows_dns_api_and_health_probes() -> None:
    policy = coredns_policy()
    assert policy["metadata"]["namespace"] == "kube-system"
    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "eks.amazonaws.com/component": "coredns",
        "k8s-app": "kube-dns",
    }
    ingress = {(rule["protocol"], rule["port"]) for rule in policy["spec"]["ingress"][0]["ports"]}
    egress = {(rule["protocol"], rule["port"]) for rule in policy["spec"]["egress"][0]["ports"]}
    assert ingress == {("UDP", 53), ("TCP", 53), ("TCP", 8080), ("TCP", 8181), ("TCP", 9153)}
    assert egress == {("UDP", 53), ("TCP", 53), ("TCP", 443)}


def test_bootstrap_orders_strict_network_policy_before_coredns() -> None:
    variables = (TF / "variables.tf").read_text(encoding="utf-8")
    main = (TF / "main.tf").read_text(encoding="utf-8")
    script = (TF / "bootstrap.sh").read_text(encoding="utf-8")

    assert 'variable "enable_coredns_addon"' in variables
    assert "default     = true" in variables.split('variable "enable_coredns_addon"', 1)[1]
    assert "var.enable_coredns_addon ?" in main

    foundation = script.index("-var=enable_coredns_addon=false")
    policy = script.index('kubectl apply -f "$COREDNS_POLICY"')
    coredns = script.index("-var=enable_coredns_addon=true")
    final = script.rindex("-var=enable_coredns_addon=true")
    assert foundation < policy < coredns < final
    assert 'AWS_REGION="$(tf output -raw region)"' in script
    assert "aws eks wait addon-active" in script
    assert "Terraform has no drift" in script
