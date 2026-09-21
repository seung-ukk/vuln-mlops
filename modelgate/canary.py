from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="ModelGate internal canary", docs_url=None, redoc_url=None)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/canary")
async def canary() -> dict[str, str]:
    return {
        "canary": "MODELGATE_INTERNAL_SSRF_PROOF",
        "service": "lab-canary",
        "classification": "synthetic-lab-data",
    }
