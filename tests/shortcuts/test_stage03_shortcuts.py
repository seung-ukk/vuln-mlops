from tests.stage2_manifest_helpers import ROOT
import yaml

STAGE = ROOT / "lab" / "stages" / "stage-03-monitoring"

def docs(name):
    return [x for x in yaml.safe_load_all((STAGE / name).read_text(encoding="utf-8")) if x]

def test_monitoring_rbac_has_no_secret_workload_node_or_exec_access():
    role = next(x for x in docs("rbac.yaml") if x["kind"] == "Role")
    resources = {v for r in role["rules"] for v in r["resources"]}
    assert resources.isdisjoint({"secrets", "deployments", "jobs", "pods/exec", "nodes", "nodes/proxy"})
    assert "*" not in resources

def test_services_are_cluster_ip_only_and_no_ingress_exists():
    for service in docs("services.yaml"):
        assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert not list(STAGE.glob("*ingress*"))

def test_metrics_contain_no_token_flag_or_aws_material():
    config = next(x for x in docs("config.yaml") if x["metadata"]["name"] == "credential-broker-config")
    metric = config["data"]["default.conf"].split("location = /exchange", 1)[0]
    assert "SYNTHETIC_STAGE3_GIT_TOKEN" not in metric
    assert "FLAG{" not in metric
    assert "AWS_" not in metric
    assert "argocd" not in metric.lower()

def test_default_deny_and_only_stage2_client_ingress_are_present():
    policies = docs("network-policy.yaml")
    assert any(p["metadata"]["name"] == "default-deny" and p["spec"]["podSelector"] == {} for p in policies)
    text = (STAGE / "network-policy.yaml").read_text(encoding="utf-8")
    assert "stage-02-rbac" in text
    assert "stage-03-client" in text
    assert "modelgate-lab" not in text

