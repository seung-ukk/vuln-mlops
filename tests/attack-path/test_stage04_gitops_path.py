from pathlib import Path
import hashlib
import yaml
from tests.stage2_manifest_helpers import ROOT

STAGE = ROOT / "lab" / "stages" / "stage-04-gitops"

def docs(name):
    return [x for x in yaml.safe_load_all((STAGE / name).read_text(encoding="utf-8")) if x]

def test_vendored_argocd_353_inputs_are_exact():
    expected = {
        "application-crd-v3.5.3.yaml": "5dde0e229249b6b707beb98674c1deae3949d5c319a6c45b9f5a80c99618e40c",
        "applicationset-crd-v3.5.3.yaml": "7d282054f41ca2b71a22bab04a8caf0000e07e53a62432e6ea292dae5ab4f07d",
        "appproject-crd-v3.5.3.yaml": "ab225266944322750136f1198d93786e4a79a0e43c8d149abfba44da30a3eac8",
        "argocd-namespace-install-v3.5.3.yaml": "df727dfc83666dbcc78dceef969505cf9c1659af774c64f9c08a204b09bd7dba",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((STAGE / "vendor" / name).read_bytes()).hexdigest() == digest

def test_application_is_auto_synced_from_only_runtime_builder_path():
    items = docs("argocd-config.yaml")
    app = next(x for x in items if x["kind"] == "Application")
    project = next(x for x in items if x["kind"] == "AppProject")
    assert app["spec"]["source"]["targetRevision"] == "stage4-lab"
    assert app["spec"]["source"]["path"] == "runtime-builder"
    assert app["spec"]["syncPolicy"]["automated"] == {"prune": False, "selfHeal": True, "allowEmpty": False}
    assert project["spec"]["destinations"] == [{"server": "https://kubernetes.default.svc", "namespace": "stage-04-gitops"}]
    assert project["spec"]["namespaceResourceWhitelist"] == [{"group": "apps", "kind": "Deployment"}]

def test_git_change_controls_existing_workload_and_emits_proof():
    baseline = docs("runtime-builder-base.yaml")[0]
    desired = docs("repository/runtime-builder/deployment.yaml")[0]
    assert baseline["metadata"]["name"] == desired["metadata"]["name"] == "runtime-builder"
    assert baseline["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] == "baseline"
    assert desired["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] == "git-controlled"
    assert desired["spec"]["template"]["metadata"]["annotations"]["lab.vuln-mlops/stage-04-proof"] == "FLAG{stage_4_gitops_placeholder}"

    for deployment in [baseline, desired]:
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert container["readinessProbe"]["httpGet"] == {"path": "/", "port": "http"}
        assert container["livenessProbe"]["httpGet"] == {"path": "/", "port": "http"}
        assert container["resources"]["requests"] == {"cpu": "10m", "memory": "32Mi"}
        assert container["resources"]["limits"] == {"cpu": "100m", "memory": "64Mi"}

def test_stage4_operational_images_and_gitea_health_are_pinned():
    kustomization = yaml.safe_load((STAGE / "kustomization.yaml").read_text(encoding="utf-8"))
    images = {item["name"]: item for item in kustomization["images"]}
    assert images["public.ecr.aws/docker/library/redis"]["digest"] == (
        "sha256:08ad0b1d280850169a790dba1393ff7a90aef951fc19632cf4d3ce4f78e679ba"
    )

    gitea = docs("git-server.yaml")[0]
    container = gitea["spec"]["template"]["spec"]["containers"][0]
    assert "@sha256:" in container["image"]
    assert container["readinessProbe"]["httpGet"] == {"path": "/api/healthz", "port": "http"}
    assert container["livenessProbe"]["httpGet"] == {"path": "/api/healthz", "port": "http"}
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]

    redis_secret = docs("redis-secret.yaml")[0]
    assert redis_secret["metadata"]["name"] == "argocd-redis"
    assert redis_secret["stringData"] == {"auth": "SYNTHETIC_STAGE4_REDIS_PASSWORD"}


def test_modelgate_can_reach_only_gitea_and_read_fixed_reconciliation_status():
    policies = docs("network-policy.yaml")
    egress = next(
        item for item in policies
        if item["metadata"]["name"] == "modelgate-stage-04-git-egress"
    )
    assert egress["metadata"]["namespace"] == "modelgate-lab"
    assert egress["spec"]["podSelector"] == {
        "matchLabels": {"app.kubernetes.io/name": "modelgate"}
    }
    assert egress["spec"]["egress"] == [
        {
            "to": [
                {
                    "namespaceSelector": {
                        "matchLabels": {
                            "kubernetes.io/metadata.name": "stage-04-gitops"
                        }
                    },
                    "podSelector": {"matchLabels": {"app": "gitea"}},
                }
            ],
            "ports": [{"protocol": "TCP", "port": 3000}],
        }
    ]

    role = next(
        item for item in docs("participant-status-rbac.yaml")
        if item["kind"] == "Role"
    )
    assert role["rules"] == [
        {
            "apiGroups": ["argoproj.io"],
            "resources": ["applications"],
            "resourceNames": ["runtime-builder"],
            "verbs": ["get"],
        },
        {
            "apiGroups": ["apps"],
            "resources": ["deployments"],
            "resourceNames": ["runtime-builder"],
            "verbs": ["get"],
        },
    ]
