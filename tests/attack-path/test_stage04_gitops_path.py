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
