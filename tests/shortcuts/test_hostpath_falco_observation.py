from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_escape_only_host_rule_observes_without_exposing_command_or_path():
    values = yaml.safe_load(
        (ROOT / "deploy/eks-lab/stage-05-hostpath/falco-values.yaml").read_text()
    )
    assert list(values) == ["customRules"]
    rule = yaml.safe_load(values["customRules"]["lab-host-maintenance.yaml"])[0]
    assert "container.id = host" in rule["condition"]
    assert 'proc.cmdline contains "/var/lib/vuln-mlops/maintenance/task.sh"' in rule["condition"]
    assert "host-maintenance" in rule["tags"]
    assert "observe-only" in rule["tags"]
    assert "cmdline" not in rule["output"]
    assert "/var/lib/vuln-mlops" not in rule["output"]
