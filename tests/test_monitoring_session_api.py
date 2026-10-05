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


class CompletedStage2:
    def __init__(self, succeeded: int = 1) -> None:
        self.succeeded = succeeded
        self.calls: list[str] = []

    async def aclose(self) -> None:
        return None

    async def get(self, path: str, *, params: Any = None) -> httpx.Response:
        self.calls.append(path)
        return httpx.Response(200, json={"status": {"succeeded": self.succeeded}})


class FakeMonitoringSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def aclose(self) -> None:
        return None

    async def get(self, path: str) -> httpx.Response:
        self.calls.append(path)
        if path == "/datasources":
            return httpx.Response(
                200,
                json=[
                    {
                        "uid": "stage3-prometheus",
                        "name": "Stage 3 Prometheus",
                        "type": "prometheus",
                        "url": "http://prometheus.stage-03-monitoring.svc:9090",
                        "password": "must-not-be-forwarded",
                    }
                ],
            )
        if path == "/query":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "result": [
                            {
                                "metric": {
                                    "__name__": "gitops_debug_info",
                                    "credential_ref": "stage3-lab-repo-writer",
                                    "broker": "http://credential-broker.stage-03-monitoring.svc:8080",
                                    "repository": "lab-git.internal/vuln-mlops-gitops",
                                    "branch": "stage4-lab",
                                    "path": "runtime-builder/",
                                    "application": "runtime-builder",
                                    "destination": "stage-04-gitops",
                                    "instance": "10.0.0.7:8080",
                                }
                            }
                        ]
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "flag": "FLAG{stage_3_monitoring_trust_placeholder}",
                "username": "stage3-lab-writer",
                "token": "SYNTHETIC_STAGE3_GIT_TOKEN",
                "repository": "lab-git.internal/vuln-mlops-gitops",
                "branch": "stage4-lab",
                "path": "runtime-builder/",
                "application": "runtime-builder",
                "destination": "stage-04-gitops",
                "extra": "must-not-be-forwarded",
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


def test_completed_stage2_session_reaches_fixed_monitoring_chain(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    kubernetes = CompletedStage2()
    monitoring = FakeMonitoringSession()

    with TestClient(app) as client:
        app.state.kubernetes_http = kubernetes
        app.state.monitoring_http = monitoring
        datasources = client.get(
            f"/api/lab/footholds/{proof_id}/stage-03/datasources"
        )
        topology = client.get(f"/api/lab/footholds/{proof_id}/stage-03/query")
        credential = client.get(
            f"/api/lab/footholds/{proof_id}/stage-03/exchange/"
            "stage3-lab-repo-writer"
        )

    assert datasources.status_code == 200
    assert datasources.json()["datasources"] == [
        {
            "uid": "stage3-prometheus",
            "name": "Stage 3 Prometheus",
            "type": "prometheus",
        }
    ]
    assert "password" not in datasources.text
    assert topology.status_code == 200
    assert topology.json()["credential_ref"] == "stage3-lab-repo-writer"
    assert "instance" not in topology.text
    assert credential.status_code == 200
    assert credential.json()["token"] == "SYNTHETIC_STAGE3_GIT_TOKEN"
    assert "extra" not in credential.text
    assert monitoring.calls == [
        "/datasources",
        "/query",
        "/exchange/stage3-lab-repo-writer",
    ]
    assert len(kubernetes.calls) == 3


def test_stage3_requires_completed_stage2_job(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    monitoring = FakeMonitoringSession()

    with TestClient(app) as client:
        app.state.kubernetes_http = CompletedStage2(succeeded=0)
        app.state.monitoring_http = monitoring
        response = client.get(
            f"/api/lab/footholds/{proof_id}/stage-03/datasources"
        )

    assert response.status_code == 409
    assert monitoring.calls == []


def test_arbitrary_credential_reference_never_reaches_broker(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    monitoring = FakeMonitoringSession()

    with TestClient(app) as client:
        app.state.kubernetes_http = CompletedStage2()
        app.state.monitoring_http = monitoring
        response = client.get(
            f"/api/lab/footholds/{proof_id}/stage-03/exchange/arbitrary-reference"
        )

    assert response.status_code == 404
    assert monitoring.calls == []


def test_stage3_api_accepts_no_arbitrary_query_or_target(tmp_path, monkeypatch):
    _proof(tmp_path, monkeypatch)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    prefix = "/api/lab/footholds/{proof_id}/stage-03"
    datasources = schema["paths"][f"{prefix}/datasources"]["get"]
    query = schema["paths"][f"{prefix}/query"]["get"]
    exchange = schema["paths"][f"{prefix}/exchange/{{credential_ref}}"]["get"]
    assert [x["name"] for x in datasources["parameters"]] == ["proof_id"]
    assert [x["name"] for x in query["parameters"]] == ["proof_id"]
    assert [x["name"] for x in exchange["parameters"]] == [
        "proof_id",
        "credential_ref",
    ]
    for operation in (datasources, query, exchange):
        assert "requestBody" not in operation
