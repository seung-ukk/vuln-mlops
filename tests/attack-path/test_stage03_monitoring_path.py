from tests.stage2_manifest_helpers import ROOT
import yaml

STAGE = ROOT / "lab" / "stages" / "stage-03-monitoring"

def docs(name):
    return [x for x in yaml.safe_load_all((STAGE / name).read_text(encoding="utf-8")) if x]

def test_prometheus_and_grafana_are_current_digest_pinned():
    deployments = {x["metadata"]["name"]: x for x in docs("workloads.yaml")}
    images = {k: v["spec"]["template"]["spec"]["containers"][0]["image"] for k, v in deployments.items()}
    assert images["prometheus"] == "prom/prometheus:v3.14.0@sha256:5ce7540c3c00ef4ab0c9d2c995c6a5b9c421f44b4a115d97a2c7af3b1c21cbb0"
    assert images["grafana"] == "grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0"

    for deployment in deployments.values():
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert container["readinessProbe"]["httpGet"]["port"] == "http"
        assert container["livenessProbe"]["httpGet"]["port"] == "http"
        assert container["resources"]["requests"]["cpu"]
        assert container["resources"]["requests"]["memory"]
        assert container["resources"]["limits"]["cpu"]
        assert container["resources"]["limits"]["memory"]

def test_discovery_to_datasource_to_broker_path_is_wired():
    text = (STAGE / "config.yaml").read_text(encoding="utf-8")
    assert "kubernetes_sd_configs" in text
    assert "uid: stage3-prometheus" in text
    assert "gitops_debug_info" in text
    assert "credential_ref=\"stage3-lab-repo-writer\"" in text
    assert "/exchange/stage3-lab-repo-writer" in text
    assert "FLAG{stage_3_monitoring_trust_placeholder}" in text
    assert '"branch":"stage4-lab"' in text
    assert '"path":"runtime-builder/"' in text

def test_prometheus_discovery_rbac_is_namespaced_and_read_only():
    role = next(x for x in docs("rbac.yaml") if x["kind"] == "Role")
    assert role["metadata"]["namespace"] == "stage-03-monitoring"
    assert {v for r in role["rules"] for v in r["verbs"]} == {"get", "list", "watch"}

def test_attack_client_is_not_part_of_stage_install():
    kustomization = yaml.safe_load((STAGE / "kustomization.yaml").read_text(encoding="utf-8"))
    assert "attack-client.yaml" not in kustomization["resources"]
