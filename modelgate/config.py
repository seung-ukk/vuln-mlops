from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    db_path: str
    tracking_uri: str
    artifact_root: str
    enable_webhooks: bool
    enable_auto_validation: bool
    worker_poll_seconds: float
    worker_once: bool


@lru_cache
def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("MODELGATE_ENV", "local"),
        db_path=os.getenv("MODELGATE_DB_PATH", "/var/lib/modelgate/jobs.db"),
        tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"),
        artifact_root=os.getenv("MODELGATE_ARTIFACT_ROOT", "file:///artifacts"),
        enable_webhooks=_as_bool("MODELGATE_ENABLE_WEBHOOKS", True),
        enable_auto_validation=_as_bool(
            "MODELGATE_ENABLE_AUTO_VALIDATION", True
        ),
        worker_poll_seconds=float(
            os.getenv("MODELGATE_WORKER_POLL_SECONDS", "2")
        ),
        worker_once=_as_bool("MODELGATE_WORKER_ONCE", False),
    )
