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
    container = pod["containers"][0]

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
    mount = next(v for v in container["volumeMounts"] if v["name"] == "runtime-socket")
    assert mount["mountPath"] == "/run/stage5/containerd.sock"
    assert {v["name"] for v in pod["volumes"]} == {"runtime-socket", "tmp"}
    assert {v["name"] for v in container["volumeMounts"]} == {"runtime-socket", "tmp"}


def test_git_desired_state_retains_socket_boundary_and_stage_proofs():
    desired = docs("repository/runtime-builder/deployment.yaml")[0]
    template = desired["spec"]["template"]
    container = template["spec"]["containers"][0]
    env = {x["name"]: x["value"] for x in container["env"]}

    assert desired["metadata"]["namespace"] == "stage-05-runtime"
    assert env == {"STAGE4_MODE": "git-controlled", "STAGE5_MODE": "runtime-socket"}
    assert template["metadata"]["annotations"] == {
        "lab.vuln-mlops/stage-04-proof": "FLAG{stage_4_gitops_placeholder}",
        "lab.vuln-mlops/stage-05-ready": "runtime-socket",
    }
    assert container["image"] == RUNTIME_IMAGE
    assert template["spec"]["volumes"] == docs("runtime-builder-base.yaml")[0]["spec"]["template"]["spec"]["volumes"]


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
