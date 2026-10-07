from __future__ import annotations

import logging
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from mlflow.exceptions import MlflowException

from modelgate import __version__
from modelgate.artifacts import (
    ArtifactUploadError,
    UploadLimits,
    publish_logged_model,
    remove_stored_bundle,
    store_model_bundle,
)
from modelgate.config import get_settings
from modelgate.db import enqueue_job, get_job, init_db
from modelgate.discovery import build_system_info
from modelgate.logging import configure_logging
from modelgate.git_gateway import (
    GITEA_REPOSITORY_PATH,
    STAGE4_GIT_MAX_BYTES,
    STAGE4_GIT_SERVICES,
    build_git_gateway_client,
)
from modelgate.monitoring import (
    STAGE3_CREDENTIAL_REF,
    build_monitoring_client,
    normalize_credential,
    normalize_datasources,
    normalize_topology,
)
from modelgate.kubernetes import (
    STAGE2_JOB_NAME,
    STAGE2_NAMESPACE,
    STAGE2_POD_PREFIX,
    STAGE2_POD_SELECTOR,
    build_kubernetes_client,
    stage2_job_manifest,
    stage2_job_status,
)
from modelgate.proofs import rce_proof_observed
from modelgate.runtime import build_runtime_builder_client, build_runtime_client
from modelgate.registry import (
    approve_model,
    get_registered_model,
    register_model,
    registered_model_to_dict,
)
from modelgate.schemas import (
    FootholdRuleReview,
    ModelCreate,
    Stage2JobLog,
    Stage2JobStatus,
    Stage3Credential,
    Stage3DatasourceList,
    Stage3Topology,
    Stage4ApplicationStatus,
    Stage5RuntimeProof,
    Stage5BuildRequest,
    Stage5BuildStatus,
    Stage5IamProof,
    SystemInfo,
    WebhookCreate,
    WebhookTest,
)

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
    app.state.kubernetes_http = build_kubernetes_client()
    app.state.monitoring_http = build_monitoring_client()
    app.state.git_gateway_http = build_git_gateway_client()
    app.state.runtime_http = build_runtime_client()
    app.state.runtime_builder_http = build_runtime_builder_client()
    logger.info("ModelGate API started")
    try:
        yield
    finally:
        await app.state.mlflow_http.aclose()
        if app.state.kubernetes_http is not None:
            await app.state.kubernetes_http.aclose()
        await app.state.monitoring_http.aclose()
        await app.state.git_gateway_http.aclose()
        await app.state.runtime_http.aclose()
        await app.state.runtime_builder_http.aclose()


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


@app.get(
    "/api/system/info",
    response_model=SystemInfo,
    summary="Read synthetic lab system information",
    description=(
        "Returns the legacy webhook probe coordinates used by this isolated lab. "
        "The fields are synthetic topology hints, not credentials or cloud metadata."
    ),
    tags=["system"],
)
async def system_info() -> SystemInfo:
    """Expose a bounded discovery clue for the intended Stage 1 SSRF path."""

    settings = get_settings()
    return build_system_info(settings.environment)


@app.get("/api/proofs/rce/{proof_id}")
async def read_rce_proof(proof_id: UUID) -> dict[str, Any]:
    """Return a fixed proof response after the validator creates a marker."""

    settings = get_settings()
    observed = await run_in_threadpool(
        rce_proof_observed, settings.rce_proof_root, proof_id
    )
    if not observed:
        raise HTTPException(status_code=404, detail="RCE proof has not been observed")
    return {
        "proof": "rce",
        "success": True,
        "proof_id": str(proof_id),
        "evidence": "validator marker observed",
        "foothold_session": str(proof_id),
        "next": f"/api/lab/footholds/{proof_id}/self-rules",
    }


async def _require_foothold(request: Request, proof_id: UUID) -> Any:
    settings = get_settings()
    observed = await run_in_threadpool(
        rce_proof_observed, settings.rce_proof_root, proof_id
    )
    if not observed:
        raise HTTPException(status_code=404, detail="RCE foothold has not been observed")

    client = request.app.state.kubernetes_http
    if client is None:
        raise HTTPException(status_code=503, detail="Kubernetes relay is unavailable")
    return client


def _kubernetes_error(response: httpx.Response) -> HTTPException:
    detail = "Kubernetes relay request failed"
    try:
        message = response.json().get("message")
        if isinstance(message, str) and message:
            detail = message[:512]
    except (ValueError, AttributeError):
        pass
    return HTTPException(status_code=502, detail=detail)


@app.get(
    "/api/lab/footholds/{proof_id}/self-rules",
    response_model=FootholdRuleReview,
    summary="Review the bounded Stage 2 foothold permissions",
    tags=["lab foothold"],
)
async def foothold_self_rules(request: Request, proof_id: UUID) -> dict[str, Any]:
    client = await _require_foothold(request, proof_id)
    response = await client.post(
        "/apis/authorization.k8s.io/v1/selfsubjectrulesreviews",
        json={
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SelfSubjectRulesReview",
            "spec": {"namespace": STAGE2_NAMESPACE},
        },
    )
    if response.is_error:
        raise _kubernetes_error(response)
    review = response.json().get("status", {})
    return {
        "namespace": STAGE2_NAMESPACE,
        "resource_rules": review.get("resourceRules", []),
        "non_resource_rules": review.get("nonResourceRules", []),
        "incomplete": bool(review.get("incomplete", False)),
    }


@app.post(
    "/api/lab/footholds/{proof_id}/stage-02/job",
    response_model=Stage2JobStatus,
    summary="Submit the fixed Stage 2 reader Job",
    tags=["lab foothold"],
)
async def foothold_create_stage2_job(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    client = await _require_foothold(request, proof_id)
    collection = f"/apis/batch/v1/namespaces/{STAGE2_NAMESPACE}/jobs"
    response = await client.post(collection, json=stage2_job_manifest())
    created = response.status_code == status.HTTP_201_CREATED
    if response.status_code == status.HTTP_409_CONFLICT:
        response = await client.get(f"{collection}/{STAGE2_JOB_NAME}")
    if response.is_error:
        raise _kubernetes_error(response)
    return stage2_job_status(response.json(), created=created)


@app.get(
    "/api/lab/footholds/{proof_id}/stage-02/job",
    response_model=Stage2JobStatus,
    summary="Read the fixed Stage 2 reader Job status",
    tags=["lab foothold"],
)
async def foothold_read_stage2_job(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    client = await _require_foothold(request, proof_id)
    path = (
        f"/apis/batch/v1/namespaces/{STAGE2_NAMESPACE}/jobs/{STAGE2_JOB_NAME}"
    )
    response = await client.get(path)
    if response.is_error:
        raise _kubernetes_error(response)
    return stage2_job_status(response.json(), created=False)


@app.get(
    "/api/lab/footholds/{proof_id}/stage-02/log",
    response_model=Stage2JobLog,
    summary="Read the fixed Stage 2 synthetic proof log",
    tags=["lab foothold"],
)
async def foothold_read_stage2_log(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    client = await _require_foothold(request, proof_id)
    job_path = (
        f"/apis/batch/v1/namespaces/{STAGE2_NAMESPACE}/jobs/{STAGE2_JOB_NAME}"
    )
    job_response = await client.get(job_path)
    if job_response.is_error:
        raise _kubernetes_error(job_response)
    job_uid = job_response.json().get("metadata", {}).get("uid")
    if not isinstance(job_uid, str) or not job_uid:
        raise HTTPException(status_code=502, detail="Stage 2 Job identity is unavailable")

    pods_path = f"/api/v1/namespaces/{STAGE2_NAMESPACE}/pods"
    response = await client.get(
        pods_path, params={"labelSelector": STAGE2_POD_SELECTOR}
    )
    if response.is_error:
        raise _kubernetes_error(response)

    pods = response.json().get("items", [])
    names = []
    for pod in pods:
        metadata = pod.get("metadata", {})
        name = metadata.get("name", "")
        owners = metadata.get("ownerReferences", [])
        owned_by_job = any(
            owner.get("kind") == "Job"
            and owner.get("name") == STAGE2_JOB_NAME
            and owner.get("uid") == job_uid
            and owner.get("controller") is True
            for owner in owners
        )
        if name.startswith(STAGE2_POD_PREFIX) and owned_by_job:
            names.append(name)
    names.sort()
    if not names:
        raise HTTPException(status_code=409, detail="Stage 2 proof Pod is not ready")

    pod_name = names[0]
    response = await client.get(f"{pods_path}/{pod_name}/log")
    if response.is_error:
        raise _kubernetes_error(response)
    return {
        "name": STAGE2_JOB_NAME,
        "namespace": STAGE2_NAMESPACE,
        "pod": pod_name,
        "encoded_proof": response.text.strip(),
        "next": f"/api/lab/footholds/{proof_id}/stage-03/datasources",
    }


async def _require_completed_stage2(request: Request, proof_id: UUID) -> Any:
    kubernetes = await _require_foothold(request, proof_id)
    job_path = (
        f"/apis/batch/v1/namespaces/{STAGE2_NAMESPACE}/jobs/{STAGE2_JOB_NAME}"
    )
    response = await kubernetes.get(job_path)
    if response.is_error:
        raise _kubernetes_error(response)
    if int(response.json().get("status", {}).get("succeeded", 0)) < 1:
        raise HTTPException(status_code=409, detail="Stage 2 Job is not complete")
    return kubernetes


async def _require_stage3_session(request: Request, proof_id: UUID) -> Any:
    await _require_completed_stage2(request, proof_id)
    return request.app.state.monitoring_http


@app.get(
    "/api/lab/footholds/{proof_id}/stage-03/datasources",
    response_model=Stage3DatasourceList,
    summary="Discover the bounded Stage 3 Grafana datasource",
    tags=["lab foothold"],
)
async def foothold_stage3_datasources(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    monitoring = await _require_stage3_session(request, proof_id)
    response = await monitoring.get("/datasources")
    if response.is_error:
        raise HTTPException(status_code=502, detail="Monitoring relay request failed")
    datasources = normalize_datasources(response.json())
    if not datasources:
        raise HTTPException(status_code=502, detail="Grafana datasource is unavailable")
    return {
        "datasources": datasources,
        "next": f"/api/lab/footholds/{proof_id}/stage-03/query",
    }


@app.get(
    "/api/lab/footholds/{proof_id}/stage-03/query",
    response_model=Stage3Topology,
    summary="Query the fixed Stage 3 topology metric",
    tags=["lab foothold"],
)
async def foothold_stage3_query(request: Request, proof_id: UUID) -> dict[str, Any]:
    monitoring = await _require_stage3_session(request, proof_id)
    response = await monitoring.get("/query")
    if response.is_error:
        raise HTTPException(status_code=502, detail="Monitoring relay request failed")
    topology = normalize_topology(response.json())
    if topology is None:
        raise HTTPException(status_code=502, detail="Stage 3 topology is unavailable")
    return {
        **topology,
        "next": (
            f"/api/lab/footholds/{proof_id}/stage-03/exchange/"
            f"{STAGE3_CREDENTIAL_REF}"
        ),
    }


@app.get(
    "/api/lab/footholds/{proof_id}/stage-03/exchange/{credential_ref}",
    response_model=Stage3Credential,
    summary="Exchange the exact Stage 3 synthetic credential reference",
    tags=["lab foothold"],
)
async def foothold_stage3_exchange(
    request: Request, proof_id: UUID, credential_ref: str
) -> dict[str, str]:
    if credential_ref != STAGE3_CREDENTIAL_REF:
        raise HTTPException(status_code=404, detail="Credential reference not found")
    monitoring = await _require_stage3_session(request, proof_id)
    response = await monitoring.get(f"/exchange/{STAGE3_CREDENTIAL_REF}")
    if response.is_error:
        raise HTTPException(status_code=502, detail="Monitoring relay request failed")
    credential = normalize_credential(response.json())
    if credential is None:
        raise HTTPException(status_code=502, detail="Stage 3 credential is unavailable")
    return {
        **credential,
        "git_gateway": (
            f"/api/lab/footholds/{proof_id}/stage-04/git/"
            "vuln-mlops-gitops.git"
        ),
        "application_status": (
            f"/api/lab/footholds/{proof_id}/stage-04/application"
        ),
    }


def _require_git_basic_auth(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Basic ") or len(authorization) > 2048:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Stage 3 Git credential is required",
            headers={"WWW-Authenticate": "Basic"},
        )
    return authorization


async def _bounded_git_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if declared_size > STAGE4_GIT_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Git request is too large")
    body = await request.body()
    if len(body) > STAGE4_GIT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Git request is too large")
    return body


async def _proxy_stage4_git(
    request: Request,
    proof_id: UUID,
    *,
    suffix: str,
    service: str,
) -> Response:
    await _require_completed_stage2(request, proof_id)
    authorization = _require_git_basic_auth(request)
    body = await _bounded_git_body(request)
    headers = {"authorization": authorization}
    for name in ("content-type", "git-protocol"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    params = {"service": service} if suffix == "/info/refs" else None
    try:
        upstream = await request.app.state.git_gateway_http.request(
            request.method,
            f"{GITEA_REPOSITORY_PATH}{suffix}",
            params=params,
            content=body,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Git gateway is unavailable") from exc
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in {"content-type", "cache-control", "www-authenticate"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@app.get(
    "/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/info/refs",
    summary="Discover the fixed Stage 4 Git smart-HTTP service",
    tags=["lab foothold"],
)
async def foothold_stage4_git_info_refs(
    request: Request, proof_id: UUID, service: str
) -> Response:
    if service not in STAGE4_GIT_SERVICES:
        raise HTTPException(status_code=404, detail="Git service not found")
    return await _proxy_stage4_git(
        request,
        proof_id,
        suffix="/info/refs",
        service=service,
    )


@app.post(
    "/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/git-upload-pack",
    summary="Read the fixed Stage 4 Git repository",
    tags=["lab foothold"],
)
async def foothold_stage4_git_upload_pack(
    request: Request, proof_id: UUID
) -> Response:
    return await _proxy_stage4_git(
        request,
        proof_id,
        suffix="/git-upload-pack",
        service="git-upload-pack",
    )


@app.post(
    "/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/git-receive-pack",
    summary="Write the fixed Stage 4 Git repository",
    tags=["lab foothold"],
)
async def foothold_stage4_git_receive_pack(
    request: Request, proof_id: UUID
) -> Response:
    return await _proxy_stage4_git(
        request,
        proof_id,
        suffix="/git-receive-pack",
        service="git-receive-pack",
    )


async def _read_stage4_application(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    kubernetes = await _require_completed_stage2(request, proof_id)
    application_path = (
        "/apis/argoproj.io/v1alpha1/namespaces/stage-04-gitops/"
        "applications/runtime-builder"
    )
    application_response = await kubernetes.get(application_path)
    if application_response.is_error:
        raise _kubernetes_error(application_response)
    application = application_response.json()

    deployment_namespace = (
        application.get("spec", {}).get("destination", {}).get("namespace")
    )
    if deployment_namespace not in {"stage-04-gitops", "stage-05-runtime"}:
        raise HTTPException(status_code=502, detail="Argo destination is unavailable")
    deployment_response = await kubernetes.get(
        f"/apis/apps/v1/namespaces/{deployment_namespace}/"
        "deployments/runtime-builder"
    )
    if deployment_response.is_error:
        raise _kubernetes_error(deployment_response)
    deployment = deployment_response.json()

    pod_template = deployment.get("spec", {}).get("template", {})
    annotations = pod_template.get("metadata", {}).get("annotations", {})
    containers = pod_template.get("spec", {}).get("containers", [])
    environment = containers[0].get("env", []) if containers else []
    stage5_mode = next(
        (item.get("value") for item in environment if item.get("name") == "STAGE5_MODE"),
        None,
    )
    application_status = application.get("status", {})
    stage4_proof = annotations.get("lab.vuln-mlops/stage-04-proof")
    runtime_relay = None
    builder_endpoint = None
    node_result_endpoint = None
    if (
        stage4_proof == "FLAG{stage_4_gitops_placeholder}"
        and stage5_mode in {"runtime-socket", "iam-build"}
    ):
        runtime_relay = (
            f"/api/lab/footholds/{proof_id}/stage-05/runtime/proof"
        )
    if (
        stage4_proof == "FLAG{stage_4_gitops_placeholder}"
        and stage5_mode == "iam-build"
    ):
        builder_endpoint = f"/api/lab/footholds/{proof_id}/stage-05/build/info"
    if stage5_mode == "hostpath" and deployment_namespace == "stage-05-runtime":
        node_result_endpoint = f"/api/lab/footholds/{proof_id}/stage-05/node-result"
    return {
        "name": "runtime-builder",
        "namespace": deployment_namespace,
        "sync": application_status.get("sync", {}).get("status", "Unknown"),
        "health": application_status.get("health", {}).get("status", "Unknown"),
        "revision": application_status.get("sync", {}).get("revision", ""),
        "stage4_proof": stage4_proof,
        "stage5_mode": stage5_mode,
        "runtime_relay": runtime_relay,
        "builder_endpoint": builder_endpoint,
        "node_result_endpoint": node_result_endpoint,
    }


@app.get(
    "/api/lab/footholds/{proof_id}/stage-05/node-result",
    response_model=Stage5IamProof,
    summary="Read the bounded host maintenance result",
    tags=["lab foothold"],
)
async def foothold_stage5_node_result(request: Request, proof_id: UUID) -> dict[str, str]:
    application = await _read_stage4_application(request, proof_id)
    if (
        application["sync"] != "Synced"
        or application["health"] != "Healthy"
        or application["stage5_mode"] != "hostpath"
        or application["namespace"] != "stage-05-runtime"
    ):
        raise HTTPException(status_code=409, detail="Host maintenance path is not ready")
    try:
        response = await request.app.state.runtime_builder_http.get("/node/result")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Runtime builder is unavailable") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="No host result has been observed")
    if response.is_error:
        raise HTTPException(status_code=502, detail="Host result is unavailable")
    payload = response.json()
    account = payload.get("account") if isinstance(payload, dict) else None
    role = payload.get("role") if isinstance(payload, dict) else None
    flag = payload.get("flag") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"account", "role", "flag"}
        or not isinstance(account, str)
        or not isinstance(role, str)
        or not isinstance(flag, str)
        or re.fullmatch(r"[0-9]{12}", account) is None
        or re.fullmatch(
            rf"arn:aws:sts::{account}:assumed-role/vuln-mlops-escape-node/[^/]+",
            role,
        ) is None
        or re.fullmatch(r"FLAG\{stage_5_iam_[a-z0-9_]+\}", flag) is None
    ):
        raise HTTPException(status_code=502, detail="Host result is invalid")
    return payload


@app.get(
    "/api/lab/footholds/{proof_id}/stage-04/application",
    response_model=Stage4ApplicationStatus,
    summary="Read the fixed runtime-builder reconciliation status",
    tags=["lab foothold"],
)
async def foothold_stage4_application(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    return await _read_stage4_application(request, proof_id)


@app.post(
    "/api/lab/footholds/{proof_id}/stage-05/runtime/proof",
    response_model=Stage5RuntimeProof,
    summary="Run the fixed synthetic Stage 5 runtime proof",
    tags=["lab foothold"],
)
async def foothold_stage5_runtime_proof(
    request: Request, proof_id: UUID
) -> dict[str, Any]:
    if request.headers.get("content-length") not in {None, "0"}:
        raise HTTPException(status_code=400, detail="Request body is forbidden")
    body = await request.body()
    if body:
        raise HTTPException(status_code=400, detail="Request body is forbidden")

    application = await _read_stage4_application(request, proof_id)
    if (
        application["sync"] != "Synced"
        or application["health"] != "Healthy"
        or application["stage4_proof"] != "FLAG{stage_4_gitops_placeholder}"
        or application["stage5_mode"] not in {"runtime-socket", "iam-build"}
        or application["namespace"] != "stage-05-runtime"
    ):
        raise HTTPException(status_code=409, detail="Stage 5 runtime path is not ready")
    try:
        if application["stage5_mode"] == "iam-build":
            response = await request.app.state.runtime_builder_http.post(
                "/runtime/proof", content=b""
            )
        else:
            response = await request.app.state.runtime_http.post("/proof", content=b"")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Runtime relay is unavailable") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail="Runtime proof operation failed")
    payload = response.json()
    expected = {
        "proof": "runtime",
        "success": True,
        "evidence": "synthetic escape-node proof observed",
        "flag": "FLAG{stage_5_node_placeholder}",
    }
    if payload != expected:
        raise HTTPException(status_code=502, detail="Runtime proof response is invalid")
    return expected


async def _require_iam_build_mode(request: Request, proof_id: UUID) -> None:
    application = await _read_stage4_application(request, proof_id)
    if (
        application["sync"] != "Synced"
        or application["health"] != "Healthy"
        or application["stage4_proof"] != "FLAG{stage_4_gitops_placeholder}"
        or application["stage5_mode"] != "iam-build"
        or application["namespace"] != "stage-05-runtime"
    ):
        raise HTTPException(status_code=409, detail="IAM build path is not ready")


@app.get(
    "/api/lab/footholds/{proof_id}/stage-05/build/info",
    summary="Discover the fixed runtime-builder build profile",
    tags=["lab foothold"],
)
async def foothold_stage5_build_info(request: Request, proof_id: UUID) -> dict[str, str]:
    await _require_iam_build_mode(request, proof_id)
    try:
        response = await request.app.state.runtime_builder_http.get("/build/info")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Runtime builder is unavailable") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail="Runtime builder info failed")
    payload = response.json()
    if (
        not isinstance(payload, dict)
        or payload.get("service") != "runtime-builder"
        or payload.get("mode") != "legacy-build"
    ):
        raise HTTPException(status_code=502, detail="Runtime builder profile is invalid")
    return {
        "service": "runtime-builder",
        "mode": "legacy-build",
        "input_field": "source_ref",
        "resolver": "legacy shell-based source lookup",
        "next": f"/api/lab/footholds/{proof_id}/stage-05/build",
    }


@app.post(
    "/api/lab/footholds/{proof_id}/stage-05/build",
    response_model=Stage5BuildStatus,
    summary="Submit a source reference to the Git-controlled runtime builder",
    tags=["lab foothold"],
)
async def foothold_stage5_build(
    request: Request, proof_id: UUID, body: Stage5BuildRequest
) -> dict[str, str]:
    await _require_iam_build_mode(request, proof_id)
    try:
        response = await request.app.state.runtime_builder_http.post(
            "/build", json={"source_ref": body.source_ref}
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Runtime builder is unavailable") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail="Runtime builder request failed")
    payload = response.json()
    if payload not in ({"status": "completed"}, {"status": "failed"}):
        raise HTTPException(status_code=502, detail="Runtime builder response is invalid")
    return payload


@app.get(
    "/api/lab/footholds/{proof_id}/stage-05/aws-proof",
    response_model=Stage5IamProof,
    summary="Read only the validated synthetic AWS proof",
    tags=["lab foothold"],
)
async def foothold_stage5_aws_proof(request: Request, proof_id: UUID) -> dict[str, str]:
    await _require_iam_build_mode(request, proof_id)
    try:
        response = await request.app.state.runtime_builder_http.get("/proof")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Runtime builder is unavailable") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="IAM proof has not been observed")
    if response.is_error:
        raise HTTPException(status_code=502, detail="Runtime builder proof failed")
    payload = response.json()
    if (
        not isinstance(payload, dict)
        or set(payload) != {"account", "role", "flag"}
        or not isinstance(payload["account"], str)
        or not isinstance(payload["role"], str)
        or not isinstance(payload["flag"], str)
        or re.fullmatch(r"[0-9]{12}", payload["account"]) is None
        or re.fullmatch(
            rf"arn:aws:sts::{payload['account']}:assumed-role/[^/]*runtime-builder/[^/]+",
            payload["role"],
        ) is None
        or re.fullmatch(r"FLAG\{stage_5_iam_[a-z0-9_]+\}", payload["flag"]) is None
    ):
        raise HTTPException(status_code=502, detail="IAM proof response is invalid")
    return payload


@app.post("/api/artifacts", status_code=status.HTTP_201_CREATED)
async def upload_artifact(request: Request) -> dict[str, Any]:
    """Accept a bounded ZIP containing exactly one MLflow model bundle."""

    settings = get_settings()
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type not in {"application/zip", "application/x-zip-compressed"}:
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/zip",
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if declared_size > settings.upload_max_bytes:
            raise HTTPException(status_code=413, detail="Model bundle is too large")

    upload_root = Path(settings.upload_root)
    upload_root.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    received = 0
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".upload-", suffix=".zip", dir=upload_root, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            async for chunk in request.stream():
                received += len(chunk)
                if received > settings.upload_max_bytes:
                    raise HTTPException(status_code=413, detail="Model bundle is too large")
                temporary.write(chunk)

        if received == 0:
            raise HTTPException(status_code=400, detail="Model bundle is empty")

        try:
            stored = await run_in_threadpool(
                store_model_bundle,
                temporary_path,
                upload_root,
                UploadLimits(
                    max_files=settings.upload_max_files,
                    max_extracted_bytes=settings.upload_max_extracted_bytes,
                ),
            )
        except ArtifactUploadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            try:
                artifact_uri = await run_in_threadpool(
                    publish_logged_model,
                    stored,
                    settings.tracking_uri,
                    settings.upload_experiment_id,
                )
            except MlflowException as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not publish uploaded model to MLflow: {exc}",
                ) from exc
        finally:
            await run_in_threadpool(remove_stored_bundle, stored)

        logger.info(
            "Model artifact uploaded",
            extra={
                "upload_id": stored.upload_id,
                "file_count": stored.file_count,
                "extracted_bytes": stored.extracted_bytes,
            },
        )
        return {
            "upload_id": stored.upload_id,
            "artifact_uri": artifact_uri,
            "archive_bytes": received,
            "file_count": stored.file_count,
            "extracted_bytes": stored.extracted_bytes,
        }
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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
