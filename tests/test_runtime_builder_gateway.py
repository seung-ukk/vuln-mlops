from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from modelgate.main import app
from tests.test_runtime_relay_api import RuntimeKubernetes, _proof


class FakeBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    async def aclose(self) -> None:
        return None

    async def get(self, path: str) -> httpx.Response:
        self.calls.append(("GET", path, None))
        if path == "/build/info":
            return httpx.Response(200, json={"service": "runtime-builder", "mode": "legacy-build"})
        if path == "/proof":
            return httpx.Response(
                200,
                json={
                    "account": "123456789012",
                    "role": "arn:aws:sts::123456789012:assumed-role/lab-runtime-builder/session",
                    "flag": "FLAG{stage_5_iam_placeholder}",
                },
            )
        return httpx.Response(404)

    async def post(self, path: str, *, json: dict[str, str]) -> httpx.Response:
        self.calls.append(("POST", path, json))
        return httpx.Response(200, json={"status": "completed"})


def test_participant_gateway_forwards_only_build_input_and_validated_proof(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    builder = FakeBuilder()
    with TestClient(app) as client:
        app.state.kubernetes_http = RuntimeKubernetes(stage5_mode="iam-build")
        app.state.runtime_builder_http = builder
        status = client.get(f"/api/lab/footholds/{proof_id}/stage-04/application")
        info = client.get(f"/api/lab/footholds/{proof_id}/stage-05/build/info")
        build = client.post(
            f"/api/lab/footholds/{proof_id}/stage-05/build",
            json={"source_ref": "main; cd /opt/modelgate && python -m runtime_builder.aws_proof; #"},
        )
        result = client.get(f"/api/lab/footholds/{proof_id}/stage-05/aws-proof")

    assert status.json()["builder_endpoint"].endswith("/stage-05/build/info")
    assert info.status_code == 200
    assert info.json()["next"].endswith("/stage-05/build")
    assert info.json()["input_field"] == "source_ref"
    assert info.json()["resolver"] == "legacy shell-based source lookup"
    assert build.json() == {"status": "completed"}
    assert result.json()["flag"] == "FLAG{stage_5_iam_placeholder}"
    assert builder.calls == [
        ("GET", "/build/info", None),
        ("POST", "/build", {"source_ref": "main; cd /opt/modelgate && python -m runtime_builder.aws_proof; #"}),
        ("GET", "/proof", None),
    ]


def test_gateway_rejects_early_or_unknown_proofs_before_reaching_builder(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    builder = FakeBuilder()
    with TestClient(app) as client:
        app.state.kubernetes_http = RuntimeKubernetes(stage5_mode="socket-present")
        app.state.runtime_builder_http = builder
        early = client.post(
            f"/api/lab/footholds/{proof_id}/stage-05/build",
            json={"source_ref": "main"},
        )
        early_info = client.get(f"/api/lab/footholds/{proof_id}/stage-05/build/info")
        unknown = client.get(f"/api/lab/footholds/{uuid4()}/stage-05/aws-proof")
    assert early.status_code == 409
    assert early_info.status_code == 409
    assert unknown.status_code == 404
    assert builder.calls == []
