import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "lab" / "stages" / "stage-05-iam-app" / "runtime-builder-base.yaml.in"
IMAGE = "ghcr.io/seung-ukk/vuln-mlops@sha256:" + "a" * 64
SPEC = importlib.util.spec_from_file_location("iam_template", ROOT / "deploy" / "eks-lab" / "iam_template.py")
assert SPEC is not None and SPEC.loader is not None
iam_template = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(iam_template)
make_patch = iam_template.make_patch
verify_preview = iam_template.verify_preview


def reviewed_deployment() -> dict:
    item = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    item["spec"]["template"]["spec"]["containers"][0]["image"] = IMAGE
    return item


def test_patch_replaces_only_the_reviewed_pod_template() -> None:
    item = reviewed_deployment()
    assert make_patch(item) == [{"op": "replace", "path": "/spec/template", "value": item["spec"]["template"]}]
    verify_preview(item, IMAGE)


@pytest.mark.parametrize("field,value", [
    ("tolerations", [{"key": "lab.vuln-mlops/escape"}]),
    ("initContainers", [{"name": "install-crictl"}]),
    ("volumes", [{"name": "runtime-socket", "hostPath": {"path": "/run/containerd/containerd.sock"}}]),
])
def test_preview_rejects_old_socket_fields(field: str, value: list) -> None:
    item = reviewed_deployment()
    item["spec"]["template"]["spec"][field] = value
    with pytest.raises(ValueError):
        verify_preview(item, IMAGE)


def test_patch_rejects_other_resource_name() -> None:
    item = reviewed_deployment()
    item["metadata"]["name"] = "other-workload"
    with pytest.raises(ValueError):
        make_patch(item)
