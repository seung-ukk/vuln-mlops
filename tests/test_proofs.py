from uuid import uuid4

from fastapi.testclient import TestClient

from modelgate.config import get_settings
from modelgate.main import app
from modelgate.proofs import RCE_PROOF_MARKER


def test_rce_proof_returns_only_fixed_evidence(tmp_path, monkeypatch):
    proof_id = uuid4()
    proof_root = tmp_path / "proofs"
    proof_root.mkdir()
    (proof_root / str(proof_id)).write_bytes(RCE_PROOF_MARKER)
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_RCE_PROOF_ROOT", str(proof_root))
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get(f"/api/proofs/rce/{proof_id}")

    assert response.status_code == 200
    assert response.json() == {
        "proof": "rce",
        "success": True,
        "proof_id": str(proof_id),
        "evidence": "validator marker observed",
        "foothold_session": str(proof_id),
        "next": f"/api/lab/footholds/{proof_id}/self-rules",
    }


def test_rce_proof_does_not_return_arbitrary_content(tmp_path, monkeypatch):
    proof_id = uuid4()
    proof_root = tmp_path / "proofs"
    proof_root.mkdir()
    (proof_root / str(proof_id)).write_text("attacker-controlled-secret")
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_RCE_PROOF_ROOT", str(proof_root))
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get(f"/api/proofs/rce/{proof_id}")

    assert response.status_code == 404
    assert "attacker-controlled-secret" not in response.text
