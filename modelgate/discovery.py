from __future__ import annotations

from modelgate.schemas import SystemInfo


def build_system_info(environment: str) -> SystemInfo:
    """Build the bounded synthetic clue exposed by the Stage 1 API."""

    namespace = "stage-01-canary" if environment == "kubernetes-lab" else None
    return SystemInfo(
        service="modelgate",
        environment=environment,
        legacy_webhook_probe={
            "service": "lab-canary",
            "namespace": namespace,
            "port": 9000,
            "path": "/canary",
        },
    )
