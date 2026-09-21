from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from mlflow.exceptions import MlflowException

from modelgate import __version__
from modelgate.config import get_settings
from modelgate.db import enqueue_job, get_job, init_db
from modelgate.logging import configure_logging
from modelgate.registry import (
    approve_model,
    get_registered_model,
    register_model,
    registered_model_to_dict,
)
from modelgate.schemas import ModelCreate, WebhookCreate, WebhookTest

configure_logging()
logger = logging.getLogger("modelgate.api")
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.db_path)
    app.state.mlflow_http = httpx.AsyncClient(
        base_url=settings.tracking_uri,
        follow_redirects=False,
        timeout=httpx.Timeout(35.0),
    )
    logger.info("ModelGate API started")
    try:
        yield
    finally:
        await app.state.mlflow_http.aclose()


app = FastAPI(
    title="ModelGate",
    version=__version__,
    description="MLflow-backed model onboarding and validation service",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    try:
        response = await request.app.state.mlflow_http.get("/health")
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="MLflow is unavailable") from exc
    return {"status": "ready"}


@app.get("/api/meta")
async def metadata() -> dict[str, Any]:
    settings = get_settings()
    return {
        "name": "ModelGate",
        "version": __version__,
        "environment": settings.environment,
        "webhooks_enabled": settings.enable_webhooks,
        "auto_validation_enabled": settings.enable_auto_validation,
        "notice": "Authorized isolated security lab only",
    }


@app.post("/api/models", status_code=status.HTTP_201_CREATED)
async def create_model(payload: ModelCreate) -> dict[str, Any]:
    settings = get_settings()
    try:
        version = await run_in_threadpool(
            register_model,
            settings.tracking_uri,
            name=payload.name,
            artifact_uri=payload.artifact_uri,
            description=payload.description,
        )
    except MlflowException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    job = None
    if settings.enable_auto_validation:
        job = enqueue_job(settings.db_path, payload.name, str(version.version))
    logger.info(
        "Model version registered",
        extra={
            "model_name": payload.name,
            "model_version": str(version.version),
            "job_id": job["id"] if job else None,
        },
    )
    return {
        "name": payload.name,
        "version": str(version.version),
        "artifact_uri": payload.artifact_uri,
        "validation_job": job,
    }


@app.get("/api/models/{name}")
async def read_model(name: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        model = await run_in_threadpool(
            get_registered_model, settings.tracking_uri, name
        )
    except MlflowException as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return registered_model_to_dict(model)


@app.post(
    "/api/models/{name}/versions/{version}/validate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def validate_model(name: str, version: str) -> dict[str, Any]:
    settings = get_settings()
    job = enqueue_job(settings.db_path, name, version)
    logger.info(
        "Validation queued",
        extra={"job_id": job["id"], "model_name": name, "model_version": version},
    )
    return job


@app.post("/api/models/{name}/versions/{version}/approve")
async def approve(name: str, version: str) -> dict[str, str]:
    settings = get_settings()
    try:
        await run_in_threadpool(
            approve_model, settings.tracking_uri, name, version
        )
    except MlflowException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"name": name, "version": version, "alias": "champion"}


@app.get("/api/jobs/{job_id}")
async def read_job(job_id: str) -> dict[str, Any]:
    job = get_job(get_settings().db_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Validation job not found")
    return job


def _require_webhooks() -> None:
    if not get_settings().enable_webhooks:
        raise HTTPException(status_code=404, detail="Webhook feature is disabled")


async def _proxy_mlflow_response(response: httpx.Response) -> Response:
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers={
            "content-type": response.headers.get("content-type", "application/json")
        },
    )


@app.post("/api/webhooks")
async def create_webhook(payload: WebhookCreate, request: Request) -> Response:
    _require_webhooks()
    response = await request.app.state.mlflow_http.post(
        "/api/2.0/mlflow/webhooks",
        json=payload.model_dump(exclude_none=True),
    )
    return await _proxy_mlflow_response(response)


@app.post("/api/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: str, payload: WebhookTest, request: Request
) -> Response:
    _require_webhooks()
    body: dict[str, Any] = {"webhook_id": webhook_id}
    if payload.event is not None:
        body["event"] = payload.event.model_dump()
    response = await request.app.state.mlflow_http.post(
        f"/api/2.0/mlflow/webhooks/{webhook_id}/test",
        json=body,
    )
    return await _proxy_mlflow_response(response)
