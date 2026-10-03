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
    assert "debian:bookworm-slim@sha256:" in expressions
    assert "volumes.size() == 3" in expressions
    assert "volumeMounts.size() == 3" in expressions
    assert "/usr/local/bin/crictl" in expressions


def test_privilege_host_namespace_and_serviceaccount_shortcuts_are_denied():
    policy = docs("admission-policy.yaml")[0]
    expressions = "\n".join(v["expression"] for v in policy["spec"]["validations"])

    assert "hostNetwork" in expressions and "hostPID" in expressions and "hostIPC" in expressions
    assert "!has(object.spec.template.spec.containers[0].securityContext.privileged)" in expressions
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


def test_stage5_has_no_ingress_or_egress_network_path():
    policy = docs("network-policy.yaml")[0]
    assert policy["spec"] == {
        "podSelector": {},
        "policyTypes": ["Ingress", "Egress"],
    }


def test_stage4_runtime_builder_is_removed_by_overlay():
    deletion = docs("delete-stage4-runtime-builder.yaml")[0]
    assert deletion["$patch"] == "delete"
    assert deletion["metadata"] == {
        "name": "runtime-builder",
        "namespace": "stage-04-gitops",
    }
