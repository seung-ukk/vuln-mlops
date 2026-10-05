import yaml
from tests.stage2_manifest_helpers import ROOT

STAGE = ROOT / "lab" / "stages" / "stage-04-gitops"
def docs(name): return [x for x in yaml.safe_load_all((STAGE / name).read_text(encoding="utf-8")) if x]

def test_controller_role_cannot_create_or_delete_resources():
    patch = docs("controller-role-patch.yaml")[0]
    assert patch[0]["op"] == "replace" and patch[0]["path"] == "/rules"
    rules = patch[0]["value"]
    verbs = {v for r in rules for v in r["verbs"]}
    assert "create" not in verbs and "delete" not in verbs and "deletecollection" not in verbs
    deployment = next(r for r in rules if "deployments" in r["resources"])
    assert deployment["resourceNames"] == ["runtime-builder"]
    wildcard = next(r for r in rules if r["resources"] == ["*"])
    assert wildcard["verbs"] == ["get", "list", "watch"]

def test_project_denies_cluster_rbac_secret_and_serviceaccount_resources():
    project = next(x for x in docs("argocd-config.yaml") if x["kind"] == "AppProject")
    assert project["spec"]["clusterResourceWhitelist"] == []
    blocked = {(x["group"], x["kind"]) for x in project["spec"]["namespaceResourceBlacklist"]}
    assert ("", "Secret") in blocked and ("", "ServiceAccount") in blocked
    assert ("rbac.authorization.k8s.io", "Role") in blocked
    assert ("rbac.authorization.k8s.io", "RoleBinding") in blocked

def test_admission_denies_other_deployments_host_access_and_privilege():
    policy = docs("admission-policy.yaml")[0]
    expressions = "\n".join(x["expression"] for x in policy["spec"]["validations"])
    assert "runtime-builder" in expressions
    assert "hostPath" in expressions
    assert "hostNetwork" in expressions and "hostPID" in expressions and "hostIPC" in expressions
    assert "privileged" in expressions

def test_no_runtime_socket_or_hostpath_is_added_in_stage4_workload():
    for path in ["runtime-builder-base.yaml", "repository/runtime-builder/deployment.yaml"]:
        text = (STAGE / path).read_text(encoding="utf-8")
        assert "hostPath" not in text
        assert "containerd.sock" not in text
        assert "privileged: true" not in text

def test_git_receive_hook_limits_branch_and_path():
    hook = (STAGE / "scope-hook.sh").read_text(encoding="utf-8")
    assert 'refs/heads/stage4-lab' in hook
    assert 'runtime-builder/*' in hook
    assert 'path denied' in hook

def test_unused_argocd_entrypoints_are_scaled_down_and_redis_has_no_api_client():
    kustomization = yaml.safe_load((STAGE / "kustomization.yaml").read_text(encoding="utf-8"))
    patches = kustomization["patches"]

    scaled_down = {
        item["target"]["name"]
        for item in patches
        if item["target"].get("kind") == "Deployment"
        and "replicas, value: 0" in item.get("patch", "")
    }
    assert {
        "argocd-applicationset-controller",
        "argocd-dex-server",
        "argocd-notifications-controller",
        "argocd-server",
    }.issubset(scaled_down)

    redis_patch = next(
        item for item in patches if item["target"].get("name") == "argocd-redis"
    )
    assert "automountServiceAccountToken" in redis_patch["patch"]
    assert "value: false" in redis_patch["patch"]
    assert "path: /spec/template/spec/initContainers" in redis_patch["patch"]


def test_participant_gateway_does_not_expose_gitea_or_broad_status_permissions():
    gitea_documents = docs("git-server.yaml")
    service = next(item for item in gitea_documents if item["kind"] == "Service")
    assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert not any(item["kind"] == "Ingress" for item in gitea_documents)

    role = next(
        item for item in docs("participant-status-rbac.yaml")
        if item["kind"] == "Role"
    )
    for rule in role["rules"]:
        assert rule["verbs"] == ["get"]
        assert rule["resourceNames"] == ["runtime-builder"]
        assert "list" not in rule["verbs"] and "watch" not in rule["verbs"]

    network = docs("network-policy.yaml")
    gateway_ingress = next(
        item for item in network
        if item["metadata"]["name"] == "modelgate-stage-04-git-ingress"
    )
    assert gateway_ingress["spec"]["podSelector"] == {
        "matchLabels": {"app": "gitea"}
    }
    modelgate_ingress = gateway_ingress["spec"]["ingress"][0]
    assert modelgate_ingress["ports"] == [{"protocol": "TCP", "port": 3000}]
