from __future__ import annotations

import httpx


RUNTIME_RELAY_URL = "http://runtime-relay.stage-05-runtime.svc:8080"
RUNTIME_RELAY_HEADER = "SYNTHETIC_STAGE5_RUNTIME_RELAY"


def build_runtime_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=RUNTIME_RELAY_URL,
        follow_redirects=False,
        timeout=httpx.Timeout(150.0),
        headers={"x-modelgate-relay": RUNTIME_RELAY_HEADER},
    )
