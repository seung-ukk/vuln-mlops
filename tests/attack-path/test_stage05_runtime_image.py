from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "images" / "runtime-client"


def test_runtime_client_packages_reviewed_crictl_for_eks() -> None:
    dockerfile = (IMAGE / "Dockerfile").read_text(encoding="utf-8")
    assert "crictl-v1.36.0-linux-amd64.tar.gz" in dockerfile
    assert "83855e114566a8a8c44c548d515670f51de3a5e1da8b2effb59870e2f10c25a3" in dockerfile
    assert "COPY --from=crictl /out/crictl /usr/local/bin/crictl" in dockerfile


def test_runtime_client_defaults_to_the_stage5_socket() -> None:
    config = yaml.safe_load((IMAGE / "crictl.yaml").read_text(encoding="utf-8"))
    endpoint = "unix:///run/stage5/containerd.sock"
    assert config == {
        "runtime-endpoint": endpoint,
        "image-endpoint": endpoint,
        "timeout": 10,
        "debug": False,
        "pull-image-on-create": False,
    }


def test_ci_builds_the_runtime_client_without_pushing_pull_requests() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "ghcr.io/${{ github.repository }}-runtime-client" in workflow
    assert "file: images/runtime-client/Dockerfile" in workflow
    assert "platforms: linux/amd64" in workflow
    assert "push: ${{ github.event_name != 'pull_request' }}" in workflow
