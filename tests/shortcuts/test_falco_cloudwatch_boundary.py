"""Keep CloudWatch collection scoped to synthetic Falco alerts."""

import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
FALCO = ROOT / "deploy" / "falco"
spec = importlib.util.spec_from_file_location("render_cloudwatch_iam", FALCO / "render_cloudwatch_iam.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_iam_limited_to_exact_pod_identity_and_log_streams() -> None:
    trust, policy = module.documents("123456789012")
    statement = trust["Statement"][0]
    assert statement["Principal"] == {"Service": "pods.eks.amazonaws.com"}
    assert statement["Condition"]["StringEquals"] == {
        "aws:RequestTag/eks-cluster-arn": "arn:aws:eks:ap-northeast-2:123456789012:cluster/vuln-mlops-personal-lab",
        "aws:RequestTag/kubernetes-namespace": "falco-observe",
        "aws:RequestTag/kubernetes-service-account": "falco-cloudwatch",
    }
    assert policy["Statement"] == [{
        "Effect": "Allow",
        "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": "arn:aws:logs:ap-northeast-2:123456789012:log-group:/vuln-mlops/vuln-mlops-personal-lab/falco:log-stream:falco-*",
    }]
    with pytest.raises(ValueError):
        module.documents("not-an-account")


def test_collector_reads_only_falco_alerts_and_escape_node() -> None:
    values = yaml.safe_load((FALCO / "cloudwatch-values.yaml").read_text(encoding="utf-8"))
    assert values["rbac"] == {"create": False}
    assert values["serviceAccount"]["name"] == "falco-cloudwatch"
    assert values["nodeSelector"] == {"kubernetes.io/os": "linux"}
    assert values["tolerations"] == [{
        "key": "lab.vuln-mlops/escape", "operator": "Equal", "value": "true", "effect": "NoSchedule"
    }]
    assert "falco-*_falco-observe_falco-*.log" in values["config"]["inputs"]
    assert "Regex log Lab.(container.process.started|escape.host.maintenance.started)" in values["config"]["filters"]
    assert "Log_Key log" in values["config"]["outputs"]
    assert "Auto_Create_Group Off" in values["config"]["outputs"]
    assert "Retry_Limit False" in values["config"]["outputs"]
    assert values["daemonSetVolumes"][0]["hostPath"]["path"] == "/var/log"
    assert values["daemonSetVolumeMounts"][0]["readOnly"] is True
    assert values["securityContext"]["allowPrivilegeEscalation"] is False


def test_only_collector_can_reach_pod_identity_agent() -> None:
    policy = yaml.safe_load((FALCO / "cloudwatch-network-policy.yaml").read_text(encoding="utf-8"))
    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/instance": "falco-cloudwatch"
    }
    assert policy["spec"]["ingress"] == []
    assert policy["spec"]["egress"] == [{
        "to": [{"ipBlock": {"cidr": "169.254.170.23/32"}}],
        "ports": [{"protocol": "TCP", "port": 80}],
    }]
