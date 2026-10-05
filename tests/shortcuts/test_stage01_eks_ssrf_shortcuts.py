from pathlib import Path

import pytest
import yaml

from modelgate.discovery import build_system_info
from poc.ssrf_canary import CANARY_TARGETS, selected_canary_target


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "eks-lab" / "stage-03"


def manifest_documents() -> list[dict]:
    return list(
        yaml.safe_load_all(
            (OVERLAY / "ssrf-canary.yaml").read_text(encoding="utf-8")
        )
    )


def test_poc_rejects_an_arbitrary_internal_target(monkeypatch) -> None:
    monkeypatch.setenv("POC_CANARY_TARGET", "http://169.254.169.254/latest/meta-data")
    with pytest.raises(ValueError, match="must be one of: compose, eks"):
        selected_canary_target()

    monkeypatch.setenv("POC_CANARY_TARGET", "monitoring")
    with pytest.raises(ValueError, match="must be one of: compose, eks"):
        selected_canary_target()


def test_poc_has_no_raw_canary_url_override() -> None:
    source = (ROOT / "poc" / "ssrf_canary.py").read_text(encoding="utf-8")
    assert set(CANARY_TARGETS) == {"compose", "eks"}
    assert "POC_CANARY_URL" not in source
    assert "169.254.169.254" not in source
    assert "kubernetes.default" not in source


def test_system_info_exposes_only_bounded_synthetic_topology() -> None:
    serialized = build_system_info("kubernetes-lab").model_dump_json().lower()
    forbidden = [
        "http://",
        "https://",
        "svc.cluster.local",
        "clusterip",
        "169.254.169.254",
        "arn:aws:",
        "access_key",
        "secret_key",
        "password",
        "token",
        "credential",
    ]
    for value in forbidden:
        assert value not in serialized

    local_probe = build_system_info("local-compose").legacy_webhook_probe
    assert local_probe.namespace is None


def test_canary_has_no_external_or_host_exposure() -> None:
    documents = manifest_documents()
    service = next(document for document in documents if document["kind"] == "Service")
    deployment = next(
        document for document in documents if document["kind"] == "Deployment"
    )
    text = (OVERLAY / "ssrf-canary.yaml").read_text(encoding="utf-8")

    assert service["spec"]["type"] == "ClusterIP"
    assert "nodePort" not in service["spec"]["ports"][0]
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["automountServiceAccountToken"] is False
    assert "hostNetwork" not in pod_spec
    assert "hostPID" not in pod_spec
    assert "hostIPC" not in pod_spec
    assert "hostPath" not in text
    assert "privileged" not in text


def test_canary_contains_only_synthetic_account_neutral_data() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(OVERLAY.glob("*.yaml"))
    )
    forbidden = [
        "707605822656",
        "arn:aws:",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "serviceaccount/token",
        "/run/containerd/containerd.sock",
    ]
    for value in forbidden:
        assert value not in text


def test_canary_policy_has_no_egress_or_broad_ingress() -> None:
    policy = next(
        document
        for document in manifest_documents()
        if document["kind"] == "NetworkPolicy"
    )
    assert policy["spec"]["egress"] == []
    assert "ipBlock" not in str(policy["spec"])
    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "lab-canary"
    }
    assert policy["spec"]["ingress"][0]["ports"] == [
        {"protocol": "TCP", "port": 9000}
    ]
