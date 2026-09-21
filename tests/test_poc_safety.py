import builtins

from fastapi.testclient import TestClient

from modelgate.canary import app
from poc.rce_marker import MARKER_PREFIX, MarkerPayload


def test_internal_canary_is_synthetic():
    with TestClient(app) as client:
        response = client.get("/canary")

    assert response.status_code == 200
    assert response.json() == {
        "canary": "MODELGATE_INTERNAL_SSRF_PROOF",
        "service": "lab-canary",
        "classification": "synthetic-lab-data",
    }


def test_rce_payload_is_limited_to_marker_statement():
    callable_, args = MarkerPayload().__reduce__()

    assert callable_ is builtins.exec
    assert len(args) == 1
    assert "/tmp/modelgate-rce-proof" in args[0]
    assert MARKER_PREFIX in args[0]
    assert "socket" not in args[0]
    assert "subprocess" not in args[0]
