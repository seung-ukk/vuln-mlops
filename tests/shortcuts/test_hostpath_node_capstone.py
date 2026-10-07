from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "lab" / "stages" / "stage-05-hostpath"
TF = ROOT / "infra" / "terraform"


def test_baseline_requires_both_uid_and_mount_changes():
    deployment = yaml.safe_load((STAGE / "runtime-builder-base.yaml.in").read_text())
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["serviceAccountName"] == "runtime-builder-hostpath"
    assert pod["automountServiceAccountToken"] is False
    assert pod["nodeSelector"]["lab.vuln-mlops/node-role"] == "escape"
    assert pod["securityContext"]["runAsUser"] == 10001
    assert pod["securityContext"]["runAsGroup"] == 10001
    assert container["volumeMounts"][1] == {
        "name": "host-maintenance", "mountPath": "/host-maintenance", "readOnly": True
    }
    assert pod["volumes"][1]["hostPath"] == {
        "path": "/var/lib/vuln-mlops/maintenance", "type": "Directory"
    }
    assert pod["volumes"][2]["hostPath"] == {
        "path": "/var/lib/vuln-mlops/node-evidence", "type": "Directory"
    }
    assert container["volumeMounts"][2] == {
        "name": "node-evidence", "mountPath": "/node-evidence", "readOnly": True
    }
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert all(v["name"] != "runtime-socket" for v in pod["volumes"])


def test_new_profile_excludes_legacy_agent_and_pod_iam():
    overlay = yaml.safe_load((STAGE / "kustomization.yaml").read_text())
    resources = "\n".join(overlay["resources"])
    assert "runtime-maintenance" not in resources
    assert "runtime-relay" not in resources
    assert "iam-app" not in resources
    assert "serviceaccount.yaml" in resources
    policy = (STAGE / "admission-policy.yaml.in").read_text()
    assert "runtime-builder-hostpath" in policy
    assert "__RUNTIME_BUILDER_IMAGE__" in policy
    assert "/var/lib/vuln-mlops/maintenance" in policy
    assert "object.spec.template.spec.containers[0].volumeMounts[2].readOnly == true" in policy
    assert "object.spec.template.spec.hostNetwork" in policy
    assert "object.spec.template.spec.containers.size() == 1" in policy


def test_node_permission_is_opt_in_and_old_pod_permission_is_removed():
    variable = (TF / "variables.tf").read_text()
    node = (TF / "node-iam-capstone.tf").read_text()
    old = (TF / "runtime-builder-iam.tf").read_text()
    assert "enable_hostpath_node_capstone" in variable
    assert "default     = false" in variable
    assert 'actions   = ["s3:GetObject"]' in node
    assert 'role   = module.eks.eks_managed_node_groups["escape"].iam_role_name' in node
    assert 'count  = var.enable_hostpath_node_capstone ? 0 : 1' in old
    assert "aws_iam_role_policy.runtime_builder_proof[0]" in old


def test_host_task_is_replaced_with_node_and_not_a_pod_side_agent():
    boot = (TF / "escape-node-maintenance.sh").read_text()
    assert "systemctl enable --now vuln-mlops-maintenance.path" in boot
    assert "PathChanged=/var/lib/vuln-mlops/maintenance/task.sh" in boot
    assert "User=root" in boot
    assert "ExecStart=/usr/bin/bash /var/lib/vuln-mlops/maintenance/task.sh" in boot
    assert "install -d -m 0700 -o root -g root /var/lib/vuln-mlops/node-evidence" in boot


def test_mentor_solution_generator_is_not_copied_into_public_app_image():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert (ROOT / "deploy" / "hostpath_capstone.py").is_file()
    assert not (ROOT / "poc" / "hostpath_capstone.py").exists()
    assert "COPY --chown=10001:10001 deploy" not in dockerfile
