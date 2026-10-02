from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mlflow")

from modelgate.config import get_settings
from modelgate.main import app


def _bundle(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def _configure(tmp_path, monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("MODELGATE_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MODELGATE_UPLOAD_ROOT", str(tmp_path / "uploads"))
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def test_external_client_can_upload_mlflow_bundle(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    def fake_publish(stored, *_args):
        assert (stored.local_path / "MLmodel").is_file()
        assert (stored.local_path / "model.bin").read_bytes() == b"synthetic-model-data"
        return f"models:/m-{stored.upload_id}"

    monkeypatch.setattr("modelgate.main.publish_logged_model", fake_publish)
    payload = _bundle(
        {
            "model/MLmodel": b"artifact_path: model\nflavors: {}\n",
            "model/model.bin": b"synthetic-model-data",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/artifacts",
            content=payload,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["artifact_uri"] == f"models:/m-{body['upload_id']}"
    assert body["file_count"] == 2
    assert not (tmp_path / "uploads" / body["upload_id"]).exists()


def test_upload_rejects_path_traversal(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    payload = _bundle(
        {
            "model/MLmodel": b"flavors: {}\n",
            "../escaped.txt": b"must-not-be-written",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/artifacts",
            content=payload,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 422
    assert not (tmp_path / "escaped.txt").exists()


def test_upload_requires_exactly_one_mlmodel_manifest(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    payload = _bundle({"README.txt": b"not a model"})

    with TestClient(app) as client:
        response = client.post(
            "/api/artifacts",
            content=payload,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 422
    assert "exactly one" in response.json()["detail"]


def test_upload_enforces_archive_size_limit(tmp_path, monkeypatch):
    _configure(
        tmp_path,
        monkeypatch,
        MODELGATE_UPLOAD_MAX_BYTES="16",
    )
    payload = _bundle({"MLmodel": b"flavors: {}\n"})

    with TestClient(app) as client:
        response = client.post(
            "/api/artifacts",
            content=payload,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 413
