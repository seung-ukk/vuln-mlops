from __future__ import annotations

import logging
import signal
import time
from threading import Event

import mlflow

from modelgate.config import get_settings
from modelgate.db import claim_next_job, finish_job, init_db
from modelgate.logging import configure_logging
from modelgate.registry import set_validation_status

configure_logging()
logger = logging.getLogger("modelgate.validator")
stop_event = Event()


def _stop(_signum: int, _frame: object) -> None:
    stop_event.set()


def validate_job(job: dict[str, object]) -> dict[str, str]:
    settings = get_settings()
    name = str(job["model_name"])
    version = str(job["model_version"])
    model_uri = f"models:/{name}/{version}"

    mlflow.set_tracking_uri(settings.tracking_uri)
    set_validation_status(settings.tracking_uri, name, version, "running")

    # This is an intentionally realistic compatibility check. In vulnerable MLflow
    # versions, a statsmodels flavor can reach pickle deserialization even when the
    # global safety setting is false. Keep this worker isolated and non-root.
    loaded_model = mlflow.pyfunc.load_model(model_uri)
    implementation = type(loaded_model._model_impl).__name__
    set_validation_status(settings.tracking_uri, name, version, "succeeded")
    return {"model_uri": model_uri, "implementation": implementation}


def run() -> None:
    settings = get_settings()
    init_db(settings.db_path)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("Model validation worker started")

    while not stop_event.is_set():
        job = claim_next_job(settings.db_path)
        if job is None:
            if settings.worker_once:
                return
            stop_event.wait(settings.worker_poll_seconds)
            continue

        context = {
            "job_id": job["id"],
            "model_name": job["model_name"],
            "model_version": job["model_version"],
        }
        logger.info("Validation started", extra=context)
        try:
            result = validate_job(job)
            finish_job(settings.db_path, str(job["id"]), result=result)
            logger.info("Validation succeeded", extra=context)
        except Exception as exc:  # job failures must not stop the worker
            message = f"{type(exc).__name__}: {exc}"[:4096]
            try:
                set_validation_status(
                    settings.tracking_uri,
                    str(job["model_name"]),
                    str(job["model_version"]),
                    "failed",
                )
            except Exception:
                logger.exception("Could not update MLflow validation tag", extra=context)
            finish_job(settings.db_path, str(job["id"]), error=message)
            logger.exception("Validation failed", extra=context)

        if settings.worker_once:
            return
        time.sleep(0.05)


if __name__ == "__main__":
    run()
