from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "lab" / "stages" / "stage-05-iam-probe"


def test_probe_network_access_is_scoped_to_dns_and_https() -> None:
    policy = yaml.safe_load((PROBE / "network-policy.yaml").read_text(encoding="utf-8"))
    assert policy["spec"]["podSelector"] == {"matchLabels": {"app": "runtime-builder-irsa-probe"}}
    assert policy["spec"]["policyTypes"] == ["Egress"]
    assert policy["spec"]["egress"][0]["ports"] == [
        {"protocol": "UDP", "port": 53},
        {"protocol": "TCP", "port": 53},
    ]
    assert policy["spec"]["egress"][1]["ports"] == [{"protocol": "TCP", "port": 443}]


def test_probe_cannot_inherit_node_credentials_or_mount_host_resources() -> None:
    job = yaml.safe_load((PROBE / "job.yaml.in").read_text(encoding="utf-8"))
    pod = job["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert {item["name"]: item["value"] for item in container["env"]}[
        "AWS_EC2_METADATA_DISABLED"
    ] == "true"
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert all("hostPath" not in volume for volume in pod["volumes"])
