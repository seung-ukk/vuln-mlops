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


class FakeKubernetesClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    async def aclose(self) -> None:
        return None

    async def post(self, path: str, *, json: Any) -> httpx.Response:
        self.calls.append(("POST", path, json))
        if path.endswith("selfsubjectrulesreviews"):
            return httpx.Response(
                201,
                json={
                    "status": {
                        "resourceRules": [
                            {
                                "verbs": ["create"],
                                "apiGroups": ["batch"],
                                "resources": ["jobs"],
                                "resourceNames": [],
                            }
                        ],
                        "nonResourceRules": [],
                        "incomplete": False,
                    }
                },
            )
        return httpx.Response(201, json={"status": {"active": 1}})

    async def get(self, path: str, *, params: Any = None) -> httpx.Response:
        self.calls.append(("GET", path, params))
        if path.endswith("/pods"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "metadata": {
                                "name": "stage-02-secret-reader-abc12",
                                "ownerReferences": [
                                    {
                                        "kind": "Job",
                                        "name": "stage-02-secret-reader",
                                        "uid": "fixed-job-uid",
                                        "controller": True,
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        if path.endswith("/log"):
            return httpx.Response(
                200,
                text="RkxBR3tzdGFnZV8yX3JiYWNfY2hhaW5pbmdfcGxhY2Vob2xkZXJ9",
            )
        return httpx.Response(
            200,
            json={
                "metadata": {"uid": "fixed-job-uid"},
                "status": {"succeeded": 1},
            },
        )


def _create_proof(tmp_path, monkeypatch):
    proof_id = uuid4()
    proof_root = tmp_path / "proofs"
    proof_root.mkdir()
    (proof_root / str(proof_id)).write_bytes(RCE_PROOF_MARKER)
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_RCE_PROOF_ROOT", str(proof_root))
    get_settings.cache_clear()
    return proof_id


def test_rce_foothold_exposes_only_fixed_stage2_workflow(tmp_path, monkeypatch):
    proof_id = _create_proof(tmp_path, monkeypatch)
    kube = FakeKubernetesClient()

    with TestClient(app) as client:
        app.state.kubernetes_http = kube
        rules = client.get(f"/api/lab/footholds/{proof_id}/self-rules")
        created = client.post(
            f"/api/lab/footholds/{proof_id}/stage-02/job",
            json={
                "metadata": {"name": "attacker-job", "namespace": "default"},
                "spec": {"template": {"spec": {"hostNetwork": True}}},
            },
        )
        job = client.get(f"/api/lab/footholds/{proof_id}/stage-02/job")
        log = client.get(f"/api/lab/footholds/{proof_id}/stage-02/log")

    assert rules.status_code == 200
    assert rules.json()["namespace"] == "stage-02-rbac"
    assert created.status_code == 200
    assert created.json() == {
        "name": "stage-02-secret-reader",
        "namespace": "stage-02-rbac",
        "created": True,
        "active": 1,
        "succeeded": 0,
        "failed": 0,
    }
    assert job.json()["succeeded"] == 1
    assert log.json() == {
        "name": "stage-02-secret-reader",
        "namespace": "stage-02-rbac",
        "pod": "stage-02-secret-reader-abc12",
        "encoded_proof": (
            "RkxBR3tzdGFnZV8yX3JiYWNfY2hhaW5pbmdfcGxhY2Vob2xkZXJ9"
        ),
        "next": f"/api/lab/footholds/{proof_id}/stage-03/datasources",
    }

    paths = [(method, path) for method, path, _ in kube.calls]
    assert paths == [
        ("POST", "/apis/authorization.k8s.io/v1/selfsubjectrulesreviews"),
        ("POST", "/apis/batch/v1/namespaces/stage-02-rbac/jobs"),
        (
            "GET",
            "/apis/batch/v1/namespaces/stage-02-rbac/jobs/stage-02-secret-reader",
        ),
        (
            "GET",
            "/apis/batch/v1/namespaces/stage-02-rbac/jobs/stage-02-secret-reader",
        ),
        ("GET", "/api/v1/namespaces/stage-02-rbac/pods"),
        (
            "GET",
            "/api/v1/namespaces/stage-02-rbac/pods/"
            "stage-02-secret-reader-abc12/log",
        ),
    ]
    assert kube.calls[1][2]["metadata"] == {
        "name": "stage-02-secret-reader",
        "namespace": "stage-02-rbac",
        "labels": {"lab.vuln-mlops/stage": "02"},
    }


def test_unknown_proof_cannot_reach_kubernetes(tmp_path, monkeypatch):
    _create_proof(tmp_path, monkeypatch)
    kube = FakeKubernetesClient()

    with TestClient(app) as client:
        app.state.kubernetes_http = kube
        response = client.post(
            f"/api/lab/footholds/{uuid4()}/stage-02/job",
            json={"metadata": {"name": "attacker-job"}},
        )

    assert response.status_code == 404
    assert kube.calls == []


def test_foothold_schema_has_no_arbitrary_proxy_or_request_body(tmp_path, monkeypatch):
    _create_proof(tmp_path, monkeypatch)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    paths = {
        path: operation
        for path, operation in schema["paths"].items()
        if path.startswith("/api/lab/footholds/")
    }
    assert set(paths) == {
        "/api/lab/footholds/{proof_id}/self-rules",
        "/api/lab/footholds/{proof_id}/stage-02/job",
        "/api/lab/footholds/{proof_id}/stage-02/log",
        "/api/lab/footholds/{proof_id}/stage-03/datasources",
        "/api/lab/footholds/{proof_id}/stage-03/query",
        "/api/lab/footholds/{proof_id}/stage-03/exchange/{credential_ref}",
        "/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/info/refs",
        "/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/git-upload-pack",
        "/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/git-receive-pack",
        "/api/lab/footholds/{proof_id}/stage-04/application",
        "/api/lab/footholds/{proof_id}/stage-05/runtime/proof",
        "/api/lab/footholds/{proof_id}/stage-05/build/info",
        "/api/lab/footholds/{proof_id}/stage-05/build",
        "/api/lab/footholds/{proof_id}/stage-05/aws-proof",
    }
    create = paths["/api/lab/footholds/{proof_id}/stage-02/job"]["post"]
    assert "requestBody" not in create
    create_parameters = create.get("parameters", [])
    assert [parameter["name"] for parameter in create_parameters] == ["proof_id"]
