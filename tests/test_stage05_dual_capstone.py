"""The two final proofs share Stage 4 but not a Pod, socket, or AWS identity."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
IAM = ROOT / "lab" / "stages" / "stage-05-iam-app"
RELAY = ROOT / "lab" / "stages" / "runtime-relay"


def manifest(name: str) -> dict:
    return yaml.safe_load((IAM / name).read_text(encoding="utf-8"))


def test_runtime_agent_uses_the_existing_fixed_cri_operation_on_escape_worker() -> None:
    agent = manifest("runtime-maintenance.yaml.in")
    pod = agent["spec"]["template"]["spec"]
    relay = pod["containers"][0]
    old_relay = list(yaml.safe_load_all((RELAY / "runtime-relay.yaml").read_text(encoding="utf-8")))[0]

    assert agent["metadata"]["name"] == "runtime-maintenance"
    assert pod["nodeSelector"]["lab.vuln-mlops/node-role"] == "escape"
    assert pod["serviceAccountName"] == "runtime-maintenance"
    assert pod["automountServiceAccountToken"] is False
    assert len(pod["containers"]) == 1
    assert relay["name"] == "runtime-relay"
    assert relay["image"] == "__RUNTIME_BUILDER_IMAGE__"
    assert relay["command"] == ["python", "/relay/runtime-relay.py"]
    assert {item["name"]: item["value"] for item in relay["env"] if "value" in item}["RELAY_ENABLED"] == "true"
    assert next(volume for volume in pod["volumes"] if volume["name"] == "runtime-socket")["hostPath"] == {
        "path": "/run/containerd/containerd.sock", "type": "Socket"
    }
    assert '"create", sandboxes[0]' in old_relay["data"]["runtime-relay.py"]
    assert "host_path\": \"/var/lib/vuln-mlops\"" in old_relay["data"]["runtime-relay.py"]


def test_iam_builder_stays_on_general_worker_without_runtime_socket() -> None:
    builder = manifest("runtime-builder-base.yaml.in")["spec"]["template"]["spec"]
    assert builder["serviceAccountName"] == "runtime-builder-iam"
    assert builder["nodeSelector"]["lab.vuln-mlops/node-role"] == "general"
    assert all("hostPath" not in volume for volume in builder["volumes"])
    agent_sa = manifest("runtime-maintenance-sa.yaml")
    assert "eks.amazonaws.com/role-arn" not in agent_sa["metadata"].get("annotations", {})
    assert agent_sa["automountServiceAccountToken"] is False


def test_iam_overlay_routes_runtime_service_only_to_dedicated_agent() -> None:
    overlay = (IAM / "kustomization.yaml").read_text(encoding="utf-8")
    assert "../runtime-relay" in overlay
    assert "runtime-maintenance.yaml.in" in overlay
    assert "runtime-maintenance-sa.yaml" in overlay
    assert "/spec/selector/app, value: runtime-maintenance" in overlay
    assert "/spec/podSelector/matchLabels/app, value: runtime-maintenance" in overlay
    assert "app: runtime-builder" in overlay
    assert "delete-modelgate-runtime-relay-egress.yaml" in overlay
    deletion = manifest("delete-modelgate-runtime-relay-egress.yaml")
    assert deletion["$patch"] == "delete"
    assert deletion["metadata"]["name"] == "modelgate-runtime-relay-egress"
    egress = list(yaml.safe_load_all((IAM / "network-policy.yaml").read_text(encoding="utf-8")))[-1]
    assert egress["metadata"]["name"] == "runtime-builder-maintenance-egress"
    assert egress["spec"]["podSelector"] == {"matchLabels": {"app": "runtime-builder"}}
    assert egress["spec"]["egress"][0]["to"] == [
        {"podSelector": {"matchLabels": {"app": "runtime-maintenance"}}}
    ]


def test_runtime_agent_admission_fixes_identity_node_and_socket() -> None:
    policy, binding = yaml.safe_load_all((IAM / "runtime-maintenance-policy.yaml.in").read_text(encoding="utf-8"))
    expressions = "\n".join(item["expression"] for item in policy["spec"]["validations"])
    assert "runtime-maintenance" in policy["spec"]["matchConditions"][0]["expression"]
    assert "serviceAccountName == 'runtime-maintenance'" in expressions
    assert "automountServiceAccountToken == false" in expressions
    assert "'lab.vuln-mlops/node-role': 'escape'" in expressions
    assert "__RUNTIME_BUILDER_IMAGE__" in expressions
    assert "/run/containerd/containerd.sock" in expressions
    assert "containers.size() == 1" in expressions
    assert "volumes.size() == 4" in expressions
    assert binding["spec"]["validationActions"] == ["Deny", "Audit"]


def test_reset_and_deploy_wait_for_both_independent_workloads() -> None:
    script = (ROOT / "deploy" / "eks-lab" / "orchestrate.sh").read_text(encoding="utf-8")
    assert 'rollout status deployment/runtime-maintenance --timeout=15m' in script
    assert 'delete pod -l app=runtime-maintenance --wait=true' in script
    assert 'f "$STAGE5_RUNTIME_ADMISSION"' in script
    assert "delete networkpolicy/modelgate-runtime-relay-egress" in script
