from __future__ import annotations

from mlflow import set_tracking_uri
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient


def client_for(tracking_uri: str) -> MlflowClient:
    set_tracking_uri(tracking_uri)
    return MlflowClient(tracking_uri=tracking_uri)


def register_model(
    tracking_uri: str,
    *,
    name: str,
    artifact_uri: str,
    description: str | None,
):
    client = client_for(tracking_uri)
    try:
        client.create_registered_model(name=name, description=description)
    except MlflowException as exc:
        if exc.error_code != "RESOURCE_ALREADY_EXISTS":
            raise
    return client.create_model_version(
        name=name,
        source=artifact_uri,
        description=description,
        tags={"modelgate.validation": "queued"},
    )


def get_registered_model(tracking_uri: str, name: str):
    return client_for(tracking_uri).get_registered_model(name)


def registered_model_to_dict(model) -> dict:
    return {
        "name": model.name,
        "description": model.description,
        "creation_timestamp": model.creation_timestamp,
        "last_updated_timestamp": model.last_updated_timestamp,
        "tags": dict(model.tags or {}),
        "aliases": dict(model.aliases or {}),
        "workspace": getattr(model, "workspace", None),
        "latest_versions": [
            {
                "name": version.name,
                "version": str(version.version),
                "source": version.source,
                "run_id": version.run_id,
                "status": version.status,
                "description": version.description,
                "tags": dict(version.tags or {}),
                "aliases": list(version.aliases or []),
                "creation_timestamp": version.creation_timestamp,
                "last_updated_timestamp": version.last_updated_timestamp,
            }
            for version in (model.latest_versions or [])
        ],
    }


def approve_model(tracking_uri: str, name: str, version: str) -> None:
    client = client_for(tracking_uri)
    client.set_registered_model_alias(name, "champion", version)
    client.set_model_version_tag(name, version, "modelgate.approval", "approved")


def set_validation_status(
    tracking_uri: str, name: str, version: str, status: str
) -> None:
    client_for(tracking_uri).set_model_version_tag(
        name, version, "modelgate.validation", status
    )
