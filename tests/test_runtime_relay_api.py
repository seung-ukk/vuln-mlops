from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mlflow")

from modelgate.config import get_settings
from modelgate.main import app
from modelgate.proofs import RCE_PROOF_MARKER


class RuntimeKubernetes:
    def __init__(
        self,
        *,
        stage4_proof: str | None = "FLAG{stage_4_gitops_placeholder}",
        stage5_mode: str = "runtime-socket",
        sync: str = "Synced",
        health: str = "Healthy",
    ) -> None:
        self.stage4_proof = stage4_proof
        self.stage5_mode = stage5_mode
        self.sync = sync
        self.health = health
        self.calls: list[str] = []

    async def aclose(self) -> None:
        return None

    async def get(self, path: str, *, params: Any = None) -> httpx.Response:
        self.calls.append(path)
        if path.endswith("/jobs/stage-02-secret-reader"):
            return httpx.Response(200, json={"status": {"succeeded": 1}})
        if path.endswith("/applications/runtime-builder"):
            return httpx.Response(
                200,
                json={
                    "spec": {"destination": {"namespace": "stage-05-runtime"}},
                    "status": {
                        "sync": {"status": self.sync, "revision": "runtime-sha"},
                        "health": {"status": self.health},
                    },
                },
            )
        if path.endswith("/deployments/runtime-builder"):
            annotations = {}
            if self.stage4_proof is not None:
                annotations["lab.vuln-mlops/stage-04-proof"] = self.stage4_proof
            return httpx.Response(
                200,
                json={
                    "spec": {
                        "template": {
                            "metadata": {"annotations": annotations},
                            "spec": {
                                "containers": [
                                    {
                                        "name": "runtime-builder",
                                        "env": [
                                            {
                                                "name": "STAGE5_MODE",
                                                "value": self.stage5_mode,
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    }
                },
            )
        return httpx.Response(404, json={"message": "not found"})


class FixedRuntimeRelay:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "proof": "runtime",
            "success": True,
            "evidence": "synthetic escape-node proof observed",
            "flag": "FLAG{stage_5_node_placeholder}",
        }
        self.calls: list[tuple[str, bytes]] = []

    async def aclose(self) -> None:
        return None

    async def post(self, path: str, *, content: bytes) -> httpx.Response:
        self.calls.append((path, content))
        return httpx.Response(200, json=self.payload)


def _proof(tmp_path, monkeypatch):
    proof_id = uuid4()
    proof_root = tmp_path / "proofs"
    proof_root.mkdir()
    (proof_root / str(proof_id)).write_bytes(RCE_PROOF_MARKER)
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_RCE_PROOF_ROOT", str(proof_root))
    get_settings.cache_clear()
    return proof_id


def test_stage5_proof_runs_only_the_fixed_runtime_operation(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = RuntimeKubernetes()
    runtime = FixedRuntimeRelay()

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        app.state.runtime_http = runtime
        response = client.post(
            f"/api/lab/footholds/{proof_id}/stage-05/runtime/proof"
        )

    assert response.status_code == 200
    assert response.json() == runtime.payload
    assert runtime.calls == [("/proof", b"")]
    assert kubernetes.calls == [
        "/apis/batch/v1/namespaces/stage-02-rbac/jobs/stage-02-secret-reader",
        "/apis/argoproj.io/v1alpha1/namespaces/stage-04-gitops/"
        "applications/runtime-builder",
        "/apis/apps/v1/namespaces/stage-05-runtime/deployments/runtime-builder",
    ]


@pytest.mark.parametrize(
    "kubernetes",
    [
        RuntimeKubernetes(stage4_proof=None),
        RuntimeKubernetes(stage4_proof="wrong"),
        RuntimeKubernetes(stage5_mode="socket-present"),
        RuntimeKubernetes(sync="OutOfSync"),
        RuntimeKubernetes(health="Progressing"),
    ],
)
def test_stage5_relay_requires_reconciled_stage4_proof(
    tmp_path, monkeypatch, kubernetes
):
    proof_id = _proof(tmp_path, monkeypatch)
    runtime = FixedRuntimeRelay()

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        app.state.runtime_http = runtime
        response = client.post(
            f"/api/lab/footholds/{proof_id}/stage-05/runtime/proof"
        )

    assert response.status_code == 409
    assert runtime.calls == []


def test_stage5_relay_rejects_body_unknown_proof_and_untrusted_response(
    tmp_path, monkeypatch
):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = RuntimeKubernetes()
    runtime = FixedRuntimeRelay({"flag": "arbitrary node data"})

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        app.state.runtime_http = runtime
        body = client.post(
            f"/api/lab/footholds/{proof_id}/stage-05/runtime/proof",
            json={"command": "cat /etc/shadow"},
        )
        unknown = client.post(
            f"/api/lab/footholds/{uuid4()}/stage-05/runtime/proof"
        )
        invalid = client.post(
            f"/api/lab/footholds/{proof_id}/stage-05/runtime/proof"
        )

    assert body.status_code == 400
    assert unknown.status_code == 404
    assert invalid.status_code == 502
    assert runtime.calls == [("/proof", b"")]


def test_stage5_openapi_accepts_no_command_path_image_or_body(tmp_path, monkeypatch):
    _proof(tmp_path, monkeypatch)

    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/lab/footholds/{proof_id}/stage-05/runtime/proof"
        ]["post"]

    assert [parameter["name"] for parameter in operation["parameters"]] == [
        "proof_id"
    ]
    assert "requestBody" not in operation
