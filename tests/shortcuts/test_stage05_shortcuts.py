import yaml

from tests.stage2_manifest_helpers import ROOT


STAGE = ROOT / "lab" / "stages" / "stage-05-runtime"


def docs(name):
    return [
        item
        for item in yaml.safe_load_all((STAGE / name).read_text(encoding="utf-8"))
        if item
    ]


def test_argocd_cannot_create_delete_or_mutate_another_workload():
    role = next(x for x in docs("controller-rbac.yaml") if x["kind"] == "Role")
    verbs = {verb for rule in role["rules"] for verb in rule["verbs"]}
    mutation = next(rule for rule in role["rules"] if "update" in rule["verbs"])

    assert not {"create", "delete", "deletecollection"} & verbs
    assert mutation["resources"] == ["deployments"]
    assert mutation["resourceNames"] == ["runtime-builder"]
    assert mutation["verbs"] == ["update", "patch"]
    wildcard = next(rule for rule in role["rules"] if rule["resources"] == ["*"])
    assert wildcard["verbs"] == ["get", "list", "watch"]


def test_admission_fixes_node_socket_image_and_container_shape():
    policy = docs("admission-policy.yaml")[0]
    expressions = "\n".join(v["expression"] for v in policy["spec"]["validations"])

    assert "lab.vuln-mlops/node-role" in expressions and "escape" in expressions
    assert "/run/containerd/containerd.sock" in expressions
    assert "/run/stage5/containerd.sock" in expressions
    assert "ghcr.io/seung-ukk/vuln-mlops-runtime-client@sha256:556d3f" in expressions
    assert "volumes.size() == 4" in expressions
    assert "containers.size() == 2" in expressions
    assert "initContainers.size() == 1" in expressions
    assert "runtime-relay.py" in expressions
    assert "The runtime relay is enabled only by the reviewed Stage 4 desired state." in (
        STAGE / "admission-policy.yaml"
    ).read_text(encoding="utf-8")
    assert "['cp', '/usr/local/bin/crictl', '/tools/crictl']" in expressions
    assert "runtime-client'" not in expressions


def test_privilege_host_namespace_and_serviceaccount_shortcuts_are_denied():
    policy = docs("admission-policy.yaml")[0]
    expressions = "\n".join(v["expression"] for v in policy["spec"]["validations"])

    assert "hostNetwork" in expressions and "hostPID" in expressions and "hostIPC" in expressions
    assert "containers.all(c" in expressions
    assert "initContainers.all(c" in expressions
    assert "privileged == false" in expressions
    assert "allowPrivilegeEscalation == false" in expressions
    assert "readOnlyRootFilesystem == true" in expressions
    assert "automountServiceAccountToken == false" in expressions


def test_node_proof_and_aws_credentials_are_not_present_in_manifests():
    manifest_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in STAGE.rglob("*.yaml")
        if path.name != "audit-policy.yaml"
    )
    assert "FLAG{stage_5_node_placeholder}" not in manifest_text
    assert "/var/lib/vuln-mlops/stage-05-proof" not in manifest_text
    assert "eks.amazonaws.com/role-arn" not in manifest_text
    assert "AWS_ACCESS_KEY_ID" not in manifest_text
    assert "hostPath: {path: /usr/local/bin/crictl" not in manifest_text


def test_stage5_has_no_ingress_or_egress_network_path():
    policy = docs("network-policy.yaml")[0]
    assert policy["spec"] == {
        "podSelector": {},
        "policyTypes": ["Ingress", "Egress"],
    }


def test_runtime_relay_network_is_modelgate_only_and_not_public():
    items = docs("runtime-relay.yaml")
    policies = {
        item["metadata"]["name"]: item
        for item in items
        if item["kind"] == "NetworkPolicy"
    }
    ingress = policies["runtime-relay-ingress"]["spec"]
    egress = policies["modelgate-runtime-relay-egress"]["spec"]
    assert ingress["podSelector"] == {"matchLabels": {"app": "runtime-builder"}}
    assert ingress["ingress"][0]["ports"] == [{"protocol": "TCP", "port": 8080}]
    assert egress["podSelector"] == {
        "matchLabels": {"app.kubernetes.io/name": "modelgate"}
    }
    assert egress["egress"][0]["ports"] == [{"protocol": "TCP", "port": 8080}]
    assert not any(item["kind"] == "Ingress" for item in items)


def test_stage4_runtime_builder_is_removed_by_overlay():
    deletion = docs("delete-stage4-runtime-builder.yaml")[0]
    assert deletion["$patch"] == "delete"
    assert deletion["metadata"] == {
        "name": "runtime-builder",
        "namespace": "stage-04-gitops",
    }


def test_modelgate_can_only_read_the_fixed_stage5_runtime_builder_status():
    role = next(
        item for item in docs("participant-status-rbac.yaml")
        if item["kind"] == "Role"
    )
    assert role["rules"] == [
        {
            "apiGroups": ["apps"],
            "resources": ["deployments"],
            "resourceNames": ["runtime-builder"],
            "verbs": ["get"],
        }
    ]
