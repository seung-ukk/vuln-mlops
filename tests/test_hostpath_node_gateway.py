from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from modelgate.main import app
from tests.test_runtime_relay_api import RuntimeKubernetes, _proof


class NodeResultRelay:
    def __init__(self, payload=None):
        self.payload = payload or {
            "account": "707605822656",
            "role": "arn:aws:sts::707605822656:assumed-role/vuln-mlops-escape-node/i-lab123",
            "flag": "FLAG{stage_5_iam_placeholder}",
        }
        self.calls = []

    async def aclose(self):
        return None

    async def get(self, path):
        self.calls.append(path)
        return httpx.Response(200, json=self.payload)


def test_hostpath_result_requires_reconciled_stage4_and_bounded_node_identity(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    relay = NodeResultRelay()
    with TestClient(app) as client:
        app.state.kubernetes_http = RuntimeKubernetes(stage5_mode="hostpath", stage4_proof=None)
        app.state.runtime_builder_http = relay
        status = client.get(f"/api/lab/footholds/{proof_id}/stage-04/application")
        result = client.get(f"/api/lab/footholds/{proof_id}/stage-05/node-result")
    assert status.status_code == 200
    assert status.json()["node_result_endpoint"].endswith("/stage-05/node-result")
    assert status.json()["runtime_relay"] is None
    assert status.json()["builder_endpoint"] is None
    assert result.status_code == 200
    assert result.json() == relay.payload
    assert relay.calls == ["/node/result"]


def test_hostpath_result_denies_early_and_pod_iam_shortcuts(tmp_path, monkeypatch):
    proof_id = _proof(tmp_path, monkeypatch)
    relay = NodeResultRelay()
    with TestClient(app) as client:
        app.state.kubernetes_http = RuntimeKubernetes(stage5_mode="hostpath", health="Progressing")
        app.state.runtime_builder_http = relay
        early = client.get(f"/api/lab/footholds/{proof_id}/stage-05/node-result")
        app.state.kubernetes_http = RuntimeKubernetes(stage5_mode="hostpath")
        relay.payload["role"] = "arn:aws:sts::707605822656:assumed-role/vuln-mlops-personal-lab-runtime-builder/pod"
        wrong_role = client.get(f"/api/lab/footholds/{proof_id}/stage-05/node-result")
    assert early.status_code == 409
    assert wrong_role.status_code == 502
    assert relay.calls == ["/node/result"]
