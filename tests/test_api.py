from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mlflow")

from modelgate.config import get_settings
from modelgate.main import app


def test_healthz(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_model_queues_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_ENABLE_AUTO_VALIDATION", "true")
    get_settings.cache_clear()

    # run_in_threadpool expects a sync callable; the lambda is intentionally sync.
    monkeypatch.setattr(
        "modelgate.main.register_model",
        lambda *_args, **_kwargs: SimpleNamespace(version="7"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/models",
            json={
                "name": "fraud-detection",
                "artifact_uri": "models:/m-benign123",
                "description": "test model",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == "7"
    assert body["validation_job"]["status"] == "queued"


def test_invalid_model_name_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/models",
            json={"name": "bad/name", "artifact_uri": "models:/m-benign123"},
        )
    assert response.status_code == 422


def test_read_model_serializes_mlflow_entity(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    get_settings.cache_clear()
    version = SimpleNamespace(
        name="fraud-detection",
        version="1",
        source="models:/m-benign123",
        run_id="run-1",
        status="READY",
        description="benign",
        tags={"modelgate.validation": "succeeded"},
        aliases=["champion"],
        creation_timestamp=1,
        last_updated_timestamp=2,
    )
    model = SimpleNamespace(
        name="fraud-detection",
        description="benign",
        creation_timestamp=1,
        last_updated_timestamp=2,
        tags={},
        aliases={"champion": "1"},
        workspace="default",
        latest_versions=[version],
    )
    monkeypatch.setattr("modelgate.main.get_registered_model", lambda *_: model)

    with TestClient(app) as client:
        response = client.get("/api/models/fraud-detection")

    assert response.status_code == 200
    assert response.json()["aliases"] == {"champion": "1"}
    assert response.json()["latest_versions"][0]["version"] == "1"
