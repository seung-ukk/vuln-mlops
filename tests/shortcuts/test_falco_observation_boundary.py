"""Guard the blue-team Falco pilot from widening lab attack boundaries."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
FALCO = ROOT / "deploy" / "falco"


def load(name: str) -> dict:
    return yaml.safe_load((FALCO / name).read_text(encoding="utf-8"))


def test_releases_select_disjoint_node_pools_and_exact_escape_taint() -> None:
    general = load("values-general.yaml")
    escape = load("values-escape.yaml")

    assert general["nodeSelector"] == {"lab.vuln-mlops/node-role": "general"}
    assert general["tolerations"] == []
    assert escape["nodeSelector"] == {"lab.vuln-mlops/node-role": "escape"}
    assert escape["tolerations"] == [
        {
            "key": "lab.vuln-mlops/escape",
            "operator": "Equal",
            "value": "true",
            "effect": "NoSchedule",
        }
    ]


def test_observation_has_no_response_action_or_sensitive_output() -> None:
    values = load("values-common.yaml")
    assert values["driver"] == {
        "kind": "modern_ebpf",
        "modernEbpf": {"leastPrivileged": True},
    }
    assert values["responseActions"]["enabled"] is False
    assert values["falcosidekick"]["enabled"] is False
    assert values["falcoctl"]["artifact"]["follow"]["enabled"] is False
    assert values["falco"]["rules_files"] == ["/etc/falco/rules.d"]
    assert values["falco"]["json_output"] is True
    assert values["falco"]["json_include_output_fields_property"] is False
    assert values["falco"]["append_output"] == []
    assert values["falco"]["http_output"]["enabled"] is False
    assert values["collectors"]["containerEngine"]["engines"]["cri"] == {
        "enabled": True,
        "sockets": ["/run/containerd/containerd.sock"],
    }

    rules = yaml.safe_load(values["customRules"]["lab-processes.yaml"])
    assert len(rules) == 1
    rule = rules[0]
    assert "k8s.ns.name in" in rule["condition"]
    assert "evt.type in (execve, execveat)" in rule["condition"]
    assert "evt.dir" not in rule["condition"]
    output = rule["output"]
    for forbidden in ("cmdline", "proc.args", "fd.name", "fd.path", "env", "flag"):
        assert forbidden not in output.lower()


def test_observation_network_policy_does_not_open_ingress() -> None:
    namespace = load("namespace.yaml")
    policy = load("network-policy.yaml")
    assert namespace["metadata"]["name"] == "falco-observe"
    assert policy["metadata"]["namespace"] == "falco-observe"
    assert policy["spec"]["podSelector"] == {}
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert policy["spec"]["ingress"] == []
    egress = policy["spec"]["egress"]
    assert len(egress) == 2
    assert {port["port"] for port in egress[0]["ports"]} == {53}
    assert egress[1]["ports"] == [{"protocol": "TCP", "port": 443}]
