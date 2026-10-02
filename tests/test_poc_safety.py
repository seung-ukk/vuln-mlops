import builtins
import uuid

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
    proof_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    callable_, args = MarkerPayload(proof_id).__reduce__()

    assert callable_ is builtins.exec
    assert len(args) == 1
    assert "/var/lib/modelgate/rce-proofs" in args[0]
    assert str(proof_id) in args[0]
    assert MARKER_PREFIX in args[0]
    assert "socket" not in args[0]
    assert "subprocess" not in args[0]
    assert "serviceaccount" not in args[0].lower()
    assert "token" not in args[0].lower()
