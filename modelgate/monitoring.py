from __future__ import annotations

from typing import Any

import httpx

MONITORING_SESSION_URL = "http://monitoring-session.stage-02-rbac.svc:8080"
STAGE3_CREDENTIAL_REF = "stage3-lab-repo-writer"
STAGE3_METRIC_KEYS = {
    "application",
    "branch",
    "broker",
    "credential_ref",
    "destination",
    "path",
    "repository",
}
STAGE3_CREDENTIAL_KEYS = {
    "application",
    "branch",
    "destination",
    "flag",
    "path",
    "repository",
    "token",
    "username",
}


def build_monitoring_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=MONITORING_SESSION_URL,
        follow_redirects=False,
        timeout=httpx.Timeout(15.0),
        trust_env=False,
    )


def normalize_datasources(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        return []
    result = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        uid = item.get("uid")
        name = item.get("name")
        data_type = item.get("type")
        if all(isinstance(value, str) and value for value in (uid, name, data_type)):
            result.append({"uid": uid, "name": name, "type": data_type})
    return result


def normalize_topology(payload: Any) -> dict[str, str] | None:
    try:
        results = payload["data"]["result"]
    except (KeyError, TypeError):
        return None
    if not isinstance(results, list) or not results:
        return None
    metric = results[0].get("metric", {})
    if not isinstance(metric, dict):
        return None
    topology = {
        key: value
        for key, value in metric.items()
        if key in STAGE3_METRIC_KEYS and isinstance(value, str)
    }
    if set(topology) != STAGE3_METRIC_KEYS:
        return None
    if topology.get("credential_ref") != STAGE3_CREDENTIAL_REF:
        return None
    return topology


def normalize_credential(payload: Any) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    credential = {
        key: value
        for key, value in payload.items()
        if key in STAGE3_CREDENTIAL_KEYS and isinstance(value, str)
    }
    if set(credential) != STAGE3_CREDENTIAL_KEYS:
        return None
    return credential
