import yaml

from tests.stage2_manifest_helpers import ROOT


STAGE = ROOT / "lab" / "stages" / "stage-05-runtime"
RUNTIME_IMAGE = (
    "ghcr.io/seung-ukk/vuln-mlops-runtime-client@sha256:"
    "556d3f1837edfcd0da44627a39dbe890822217c66b1beec2d31f5ff6c48a930b"
)


def docs(name):
    return [
        item
        for item in yaml.safe_load_all((STAGE / name).read_text(encoding="utf-8"))
        if item
    ]


def test_runtime_builder_is_pinned_to_escape_node_and_exact_socket():
    deployment = docs("runtime-builder-base.yaml")[0]
    pod = deployment["spec"]["template"]["spec"]
    container = next(c for c in pod["containers"] if c["name"] == "runtime-builder")
    relay = next(c for c in pod["containers"] if c["name"] == "runtime-relay")
    relay_env = {item["name"]: item.get("value") for item in relay["env"]}

    assert deployment["metadata"]["namespace"] == "stage-05-runtime"
    assert pod["nodeSelector"] == {"lab.vuln-mlops/node-role": "escape"}
    assert pod["tolerations"] == [
        {
            "key": "lab.vuln-mlops/escape",
            "operator": "Equal",
            "value": "true",
            "effect": "NoSchedule",
        }
    ]
    assert container["image"] == RUNTIME_IMAGE
    socket = next(v for v in pod["volumes"] if v["name"] == "runtime-socket")
    assert socket["hostPath"] == {
        "path": "/run/containerd/containerd.sock",
        "type": "Socket",
    }
    mount = next(v for v in relay["volumeMounts"] if v["name"] == "runtime-socket")
    assert mount["mountPath"] == "/run/stage5/containerd.sock"
    assert {v["name"] for v in pod["volumes"]} == {
        "runtime-socket", "tmp", "tools", "relay-code"
    }
    assert {v["name"] for v in relay["volumeMounts"]} == {
        "runtime-socket", "tmp", "tools", "relay-code"
    }
    assert "volumeMounts" not in container
    assert relay_env["RELAY_ENABLED"] == "false"


def test_git_desired_state_retains_socket_boundary_and_stage_proofs():
    desired = docs("repository/runtime-builder/deployment.yaml")[0]
    template = desired["spec"]["template"]
    container = next(
        c for c in template["spec"]["containers"] if c["name"] == "runtime-builder"
    )
    relay = next(
        c for c in template["spec"]["containers"] if c["name"] == "runtime-relay"
    )
    env = {x["name"]: x["value"] for x in container["env"]}

    assert desired["metadata"]["namespace"] == "stage-05-runtime"
    assert env == {"STAGE4_MODE": "git-controlled", "STAGE5_MODE": "runtime-socket"}
    assert template["metadata"]["annotations"] == {
        "lab.vuln-mlops/stage-04-proof": "FLAG{stage_4_gitops_placeholder}",
        "lab.vuln-mlops/stage-05-ready": "runtime-socket",
    }
    assert container["image"] == RUNTIME_IMAGE
    assert next(e for e in relay["env"] if e["name"] == "RELAY_ENABLED")["value"] == "true"
    assert template["spec"]["volumes"] == docs("runtime-builder-base.yaml")[0]["spec"]["template"]["spec"]["volumes"]


def test_relay_downward_api_fields_match_kubernetes_defaulting_in_both_states():
    for name in ("runtime-builder-base.yaml", "repository/runtime-builder/deployment.yaml"):
        deployment = docs(name)[0]
        containers = deployment["spec"]["template"]["spec"]["containers"]
        relay = next(item for item in containers if item["name"] == "runtime-relay")
        fields = {
            item["name"]: item["valueFrom"]["fieldRef"]
            for item in relay["env"]
            if "valueFrom" in item
        }
        assert fields == {
            "POD_NAME": {"apiVersion": "v1", "fieldPath": "metadata.name"},
            "POD_UID": {"apiVersion": "v1", "fieldPath": "metadata.uid"},
        }


def test_runtime_relay_is_internal_fixed_and_proof_bound():
    items = docs("runtime-relay.yaml")
    config = next(item for item in items if item["kind"] == "ConfigMap")
    service = next(item for item in items if item["kind"] == "Service")
    script = config["data"]["runtime-relay.py"]
    compile(script, "runtime-relay.py", "exec")

    assert service["metadata"]["name"] == "runtime-relay"
    assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 8080, "targetPort": "relay"}
    ]
    assert 'self.path != "/proof"' in script
    assert 'os.environ.get("RELAY_ENABLED") != "true"' in script
    assert 'self.headers.get("X-ModelGate-Relay")' in script
    assert 'Content-Length", "0") != "0"' in script
    assert '"create", sandboxes[0]' in script
    assert '"rm", container_id' in script
    assert "/var/lib/vuln-mlops" in script
    assert "stage-05-proof" in script


def test_argocd_chain_moves_only_runtime_builder_destination_to_stage5():
    patches = docs("argocd-stage5-patch.yaml")
    cluster = next(x for x in patches if x["kind"] == "Secret")
    project = next(x for x in patches if x["kind"] == "AppProject")
    application = next(x for x in patches if x["kind"] == "Application")

    assert cluster["stringData"]["namespaces"] == "stage-04-gitops,stage-05-runtime"
    assert project["spec"]["destinations"] == [
        {"server": "https://kubernetes.default.svc", "namespace": "stage-05-runtime"}
    ]
    assert application["spec"]["destination"] == {
        "server": "https://kubernetes.default.svc",
        "namespace": "stage-05-runtime",
    }


def test_controller_binding_crosses_only_into_stage5_namespace():
    items = docs("controller-rbac.yaml")
    binding = next(x for x in items if x["kind"] == "RoleBinding")
    assert binding["metadata"]["namespace"] == "stage-05-runtime"
    assert binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "argocd-application-controller",
            "namespace": "stage-04-gitops",
        }
    ]
