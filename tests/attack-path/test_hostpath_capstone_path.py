from __future__ import annotations

import sys

import pytest
import yaml

from deploy.hostpath_capstone import desired_manifest, host_task, main


IMAGE = "ghcr.io/seung-ukk/vuln-mlops@sha256:" + "a" * 64
BUCKET = "vuln-mlops-personal-lab-707605822656-runtime-proof"


def test_git_manifest_changes_both_denied_fields_and_uses_host_systemd_path():
    manifest = desired_manifest(IMAGE, BUCKET)
    template = manifest["spec"]["template"]
    pod = template["spec"]
    container = pod["containers"][0]
    assert template["metadata"]["annotations"]["lab.vuln-mlops/stage-04-proof"]
    assert pod["securityContext"]["runAsUser"] == 0
    assert pod["securityContext"]["runAsGroup"] == 0
    assert container["volumeMounts"][1]["readOnly"] is False
    assert container["command"] == ["/bin/sh", "-c"]
    assert "cat > /host-maintenance/task.sh" in container["args"][0]
    assert "exec uvicorn runtime_builder.main:app" in container["args"][0]
    assert "aws s3api get-object" in container["args"][0]
    assert "proof/final-flag.txt" in container["args"][0]
    assert "vuln-mlops-escape-node" in container["args"][0]
    assert "/var/lib/vuln-mlops/node-evidence/result.json" in container["args"][0]
    assert container["volumeMounts"][2]["readOnly"] is True
    assert pod["serviceAccountName"] == "runtime-builder-hostpath"
    assert pod["automountServiceAccountToken"] is False


def test_generator_rejects_unreviewed_image_and_s3_target():
    with pytest.raises(ValueError):
        desired_manifest("nginx:latest", BUCKET)
    with pytest.raises(ValueError):
        desired_manifest(IMAGE, "other-bucket")
    with pytest.raises(ValueError):
        host_task("vuln-mlops-personal-lab-000000000000-other")


def test_generated_git_yaml_preserves_lf_for_host_bash(tmp_path, monkeypatch):
    output = tmp_path / "deployment.yaml"
    monkeypatch.setattr(
        sys, "argv", ["hostpath_capstone.py", "--image", IMAGE, "--bucket", BUCKET, "--output", str(output)]
    )
    main()
    raw = output.read_bytes()
    assert b"\r" not in raw
    script = yaml.safe_load(raw)["spec"]["template"]["spec"]["containers"][0]["args"][0]
    assert "\r" not in script
    assert "\nHOSTTASK\nexec uvicorn" in script
