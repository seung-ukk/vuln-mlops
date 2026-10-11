from __future__ import annotations

import subprocess
from pathlib import Path
import os

import pytest

from deploy.participant_hostpath import ROOT, desired_manifest, host_task


MARKER = "lab-proof20261008"


def test_host_task_and_deployment_preserve_fixed_boundaries() -> None:
    task = host_task(MARKER)
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if os.name == "nt" and git_bash.exists() else "bash"
    subprocess.run([bash, "-n"], input=task, text=True, check=True)
    assert "id -un" in task and "id -u" in task and "hostname" in task
    assert 'aws ec2 create-tags --resources "$instance_id"' in task
    assert f"Key=lab.vuln-mlops/proof,Value={MARKER}" in task
    assert 'assumed-role/vuln-mlops-escape-node/(i-[a-f0-9]' in task
    assert "aws s3api" not in task

    deployment = desired_manifest(MARKER)
    assert deployment["metadata"]["namespace"] == "runtime-lab"
    pod = deployment["spec"]["template"]["spec"]
    assert pod["containers"][0]["image"] == (
        "ghcr.io/seung-ukk/vuln-mlops@sha256:"
        "64dcffccfe54b2b8a22006c379f16c6b5eac02f9bd24c70845145e0f4d2738d5"
    )
    assert pod["automountServiceAccountToken"] is False
    assert pod["volumes"][1]["hostPath"]["path"] == "/var/lib/vuln-mlops/maintenance"
    assert pod["volumes"][2]["hostPath"]["path"] == "/var/lib/vuln-mlops/node-evidence"
    mounts = pod["containers"][0]["volumeMounts"]
    assert mounts[1]["readOnly"] is False and mounts[2]["readOnly"] is True
    assert "cat /node-evidence/context.json /node-evidence/result.json" in pod["containers"][0]["args"][0]


def test_participant_can_choose_a_short_proof_marker() -> None:
    assert "lab-x" in host_task("lab-x")


@pytest.mark.parametrize("marker", ["production", "lab-", "lab-foo;touch/tmp/pwned"])
def test_host_task_rejects_other_markers(marker: str) -> None:
    with pytest.raises(ValueError):
        host_task(marker)


def test_node_proof_permission_is_scoped_to_escape_instances_and_one_tag() -> None:
    policy = (ROOT / "infra/terraform/node-iam-capstone.tf").read_text(encoding="utf-8")
    node_group = (ROOT / "infra/terraform/main.tf").read_text(encoding="utf-8")
    assert 'actions   = ["ec2:CreateTags"]' in policy
    assert 'variable = "ec2:ResourceTag/lab.vuln-mlops/node-role"' in policy
    assert 'values   = ["escape"]' in policy
    assert 'variable = "aws:TagKeys"' in policy
    assert 'values   = ["lab.vuln-mlops/proof"]' in policy
    assert 'variable = "aws:RequestTag/lab.vuln-mlops/proof"' in policy
    assert '"lab.vuln-mlops/node-role" = "escape"' in node_group
    assert "launch_template_tags = {" in node_group
    assert "s3:GetObject" not in policy
