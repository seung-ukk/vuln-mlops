from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TF_DIR = ROOT / "infra" / "terraform"
ACCESS_DIR = ROOT / "deploy" / "eks-access"


def rendered_modelgate_documents() -> list[dict]:
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


def test_terraform_creates_one_optional_eip_and_lbc_pod_identity() -> None:
    main = (TF_DIR / "main.tf").read_text()

    assert 'resource "aws_eip" "modelgate_public"' in main
    assert "count = var.enable_modelgate_public_access ? 1 : 0" in main
    assert 'domain = "vpc"' in main
    assert 'module "aws_load_balancer_controller_pod_identity"' in main
    assert "attach_aws_lb_controller_policy = true" in main
    assert 'namespace       = "kube-system"' in main
    assert 'service_account = "aws-load-balancer-controller"' in main
    assert "cluster_name = module.eks.cluster_name" in main


def test_public_service_is_single_subnet_fixed_eip_nlb() -> None:
    service, policy = rendered_modelgate_documents()
    annotations = service["metadata"]["annotations"]

    assert service["kind"] == "Service"
    assert service["metadata"]["name"] == "modelgate-public"
    assert service["metadata"]["namespace"] == "modelgate-lab"
    assert service["spec"]["type"] == "LoadBalancer"
    assert service["spec"]["loadBalancerClass"] == "service.k8s.aws/nlb"
    assert service["spec"]["loadBalancerSourceRanges"] == ["198.51.100.25/32"]
    assert service["spec"]["selector"] == {"app.kubernetes.io/name": "modelgate"}
    assert service["spec"]["ports"] == [
        {"name": "http", "protocol": "TCP", "port": 80, "targetPort": "http"}
    ]
    assert annotations["service.beta.kubernetes.io/aws-load-balancer-scheme"] == "internet-facing"
    assert annotations["service.beta.kubernetes.io/aws-load-balancer-nlb-target-type"] == "ip"
    assert annotations["service.beta.kubernetes.io/aws-load-balancer-subnets"] == "subnet-0123456789abcdef0"
    assert annotations["service.beta.kubernetes.io/aws-load-balancer-eip-allocations"] == "eipalloc-0123456789abcdef0"
    assert annotations["service.beta.kubernetes.io/aws-load-balancer-healthcheck-path"] == "/healthz"
    assert policy["kind"] == "NetworkPolicy"


def test_access_manager_pins_controller_and_waits_for_nlb() -> None:
    script = (ACCESS_DIR / "manage.sh").read_text()

    assert 'LBC_CHART_VERSION="1.14.0"' in script
    assert "eks/aws-load-balancer-controller" in script
    assert "serviceAccount.name=aws-load-balancer-controller" in script
    assert "deployment/aws-load-balancer-controller --timeout=10m" in script
    assert "pin_modelgate_to_nlb_zone" in script
    assert "topology.kubernetes.io/zone" in script
    assert r'\"maxSurge\":0' in script
    assert r'\"maxUnavailable\":1' in script
    assert "wait_for_public_address" in script
    assert "wait_for_healthy_target" in script
    assert "TargetHealthDescriptions[].TargetHealth.State" in script
    assert "tf output -raw modelgate_public_eip" in script


def test_controller_has_required_strict_mode_network_paths() -> None:
    text = (ACCESS_DIR / "controller-network-policy.yaml.tpl").read_text()
    text = text.replace("__VPC_CIDR__", "10.42.0.0/16")
    text = text.replace("__KUBERNETES_SERVICE_IP__", "172.20.0.1")
    policy = yaml.safe_load(text)

    assert policy["metadata"] == {
        "name": "aws-load-balancer-controller",
        "namespace": "kube-system",
    }
    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "aws-load-balancer-controller"
    }
    serialized = yaml.safe_dump(policy)
    assert "10.42.0.0/16" in serialized
    assert "172.20.0.1/32" in serialized
    assert "169.254.170.23/32" in serialized
    assert "9443" in serialized
