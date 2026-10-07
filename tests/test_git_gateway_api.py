from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mlflow")

from modelgate.config import get_settings
from modelgate.git_gateway import GITEA_REPOSITORY_PATH, STAGE4_GIT_MAX_BYTES
from modelgate.main import app
from modelgate.proofs import RCE_PROOF_MARKER


class Stage4Kubernetes:
    def __init__(
        self, *, completed: bool = True, destination: str = "stage-05-runtime"
    ) -> None:
        self.completed = completed
        self.destination = destination
        self.calls: list[str] = []

    async def aclose(self) -> None:
        return None

    async def get(self, path: str, *, params: Any = None) -> httpx.Response:
        self.calls.append(path)
        if path.endswith("/jobs/stage-02-secret-reader"):
            return httpx.Response(
                200,
                json={"status": {"succeeded": 1 if self.completed else 0}},
            )
        if path.endswith("/applications/runtime-builder"):
            return httpx.Response(
                200,
                json={
                    "spec": {"destination": {"namespace": self.destination}},
                    "status": {
                        "sync": {"status": "Synced", "revision": "abc123"},
                        "health": {"status": "Healthy"},
                    }
                },
            )
        if "/stage-05-runtime/deployments/runtime-builder" in path:
            return httpx.Response(
                200,
                json={
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "lab.vuln-mlops/stage-04-proof": (
                                        "FLAG{stage_4_gitops_placeholder}"
                                    )
                                }
                            },
                            "spec": {
                                "containers": [
                                    {
                                        "env": [
                                            {
                                                "name": "STAGE5_MODE",
                                                "value": "runtime-socket",
                                            }
                                        ]
                                    }
                                ]
                            },
                        }
                    }
                },
            )
        return httpx.Response(404, json={"message": "not found"})


class FixedGitGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def aclose(self) -> None:
        return None

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "path": path, **kwargs})
        return httpx.Response(
            200,
            content=b"git-wire-response",
            headers={
                "content-type": "application/x-git-upload-pack-result",
                "cache-control": "no-cache",
                "set-cookie": "must-not-leak=yes",
                "location": "http://gitea.internal/admin",
            },
        )


def _proof(tmp_path, monkeypatch):
    proof_id = uuid4()
    proof_root = tmp_path / "proofs"
    proof_root.mkdir()
    (proof_root / str(proof_id)).write_bytes(RCE_PROOF_MARKER)
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_RCE_PROOF_ROOT", str(proof_root))
    get_settings.cache_clear()
    return proof_id


def _authorization() -> str:
    encoded = base64.b64encode(
        b"stage3-lab-writer:SYNTHETIC_STAGE3_GIT_TOKEN"
    ).decode()
    return f"Basic {encoded}"


def test_fixed_git_smart_http_gateway_preserves_auth_and_wire_data(
    tmp_path, monkeypatch
):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = Stage4Kubernetes()
    gateway = FixedGitGateway()
    prefix = (
        f"/api/lab/footholds/{proof_id}/stage-04/git/"
        "vuln-mlops-gitops.git"
    )

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        app.state.git_gateway_http = gateway
        info = client.get(
            f"{prefix}/info/refs",
            params={"service": "git-upload-pack"},
            headers={"Authorization": _authorization(), "Git-Protocol": "version=2"},
        )
        upload = client.post(
            f"{prefix}/git-upload-pack",
            content=b"upload-pack-request",
            headers={
                "Authorization": _authorization(),
                "Content-Type": "application/x-git-upload-pack-request",
            },
        )
        receive = client.post(
            f"{prefix}/git-receive-pack",
            content=b"receive-pack-request",
            headers={
                "Authorization": _authorization(),
                "Content-Type": "application/x-git-receive-pack-request",
            },
        )

    assert [response.status_code for response in (info, upload, receive)] == [200] * 3
    assert [call["path"] for call in gateway.calls] == [
        f"{GITEA_REPOSITORY_PATH}/info/refs",
        f"{GITEA_REPOSITORY_PATH}/git-upload-pack",
        f"{GITEA_REPOSITORY_PATH}/git-receive-pack",
    ]
    assert gateway.calls[0]["params"] == {"service": "git-upload-pack"}
    assert gateway.calls[0]["headers"]["authorization"] == _authorization()
    assert gateway.calls[0]["headers"]["git-protocol"] == "version=2"
    assert gateway.calls[2]["content"] == b"receive-pack-request"
    assert "set-cookie" not in receive.headers
    assert "location" not in receive.headers
    assert len(kubernetes.calls) == 3


def test_git_gateway_rejects_shortcuts_before_contacting_gitea(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = Stage4Kubernetes()
    gateway = FixedGitGateway()
    prefix = (
        f"/api/lab/footholds/{proof_id}/stage-04/git/"
        "vuln-mlops-gitops.git"
    )

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        app.state.git_gateway_http = gateway
        no_auth = client.get(
            f"{prefix}/info/refs", params={"service": "git-upload-pack"}
        )
        arbitrary_service = client.get(
            f"{prefix}/info/refs",
            params={"service": "git-admin"},
            headers={"Authorization": _authorization()},
        )
        arbitrary_repo = client.get(
            f"/api/lab/footholds/{proof_id}/stage-04/git/other.git/info/refs",
            params={"service": "git-upload-pack"},
            headers={"Authorization": _authorization()},
        )
        oversized = client.post(
            f"{prefix}/git-receive-pack",
            content=b"x",
            headers={
                "Authorization": _authorization(),
                "Content-Length": str(STAGE4_GIT_MAX_BYTES + 1),
            },
        )

    assert no_auth.status_code == 401
    assert arbitrary_service.status_code == 404
    assert arbitrary_repo.status_code == 404
    assert oversized.status_code == 413
    assert gateway.calls == []


def test_git_gateway_requires_proof_and_completed_stage2(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    gateway = FixedGitGateway()
    suffix = "/stage-04/git/vuln-mlops-gitops.git/info/refs"

    with TestClient(app) as client:
        app.state.kubernetes_http = Stage4Kubernetes(completed=False)
        app.state.git_gateway_http = gateway
        incomplete = client.get(
            f"/api/lab/footholds/{proof_id}{suffix}",
            params={"service": "git-upload-pack"},
            headers={"Authorization": _authorization()},
        )
        unknown = client.get(
            f"/api/lab/footholds/{uuid4()}{suffix}",
            params={"service": "git-upload-pack"},
            headers={"Authorization": _authorization()},
        )

    assert incomplete.status_code == 409
    assert unknown.status_code == 404
    assert gateway.calls == []


def test_stage4_application_status_is_fixed_and_normalized(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = Stage4Kubernetes()

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        response = client.get(
            f"/api/lab/footholds/{proof_id}/stage-04/application"
        )

    assert response.status_code == 200
    assert response.json() == {
        "name": "runtime-builder",
        "namespace": "stage-05-runtime",
        "sync": "Synced",
        "health": "Healthy",
        "revision": "abc123",
        "stage4_proof": "FLAG{stage_4_gitops_placeholder}",
        "stage5_mode": "runtime-socket",
        "runtime_relay": (
            f"/api/lab/footholds/{proof_id}/stage-05/runtime/proof"
        ),
        "builder_endpoint": None,
        "node_result_endpoint": None,
    }
    assert kubernetes.calls[-2:] == [
        "/apis/argoproj.io/v1alpha1/namespaces/stage-04-gitops/"
        "applications/runtime-builder",
        "/apis/apps/v1/namespaces/stage-05-runtime/deployments/runtime-builder",
    ]


def test_stage4_status_rejects_an_unexpected_argo_destination(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = Stage4Kubernetes(destination="default")

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        response = client.get(
            f"/api/lab/footholds/{proof_id}/stage-04/application"
        )

    assert response.status_code == 502
    assert not any("/deployments/" in path for path in kubernetes.calls)
