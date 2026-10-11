"""Submit an ordinary statsmodels MLflow bundle to the public lab API."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import mlflow.statsmodels
import numpy as np
import statsmodels.api as sm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelgate-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    root_url = args.modelgate_url.rstrip("/")

    with tempfile.TemporaryDirectory(prefix="modelgate-benign-") as temp_dir:
        root = Path(temp_dir)
        model = root / "model"
        x = sm.add_constant(np.arange(4.0))
        y = 1.0 + np.arange(4.0)
        mlflow.statsmodels.save_model(sm.OLS(y, x).fit(), model)
        bundle = root / "model.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in model.rglob("*"):
                if path.is_file():
                    archive.write(path, Path("model") / path.relative_to(model))

        with httpx.Client(timeout=60.0) as client:
            upload = client.post(
                f"{root_url}/api/artifacts",
                content=bundle.read_bytes(),
                headers={"content-type": "application/zip"},
            )
            upload.raise_for_status()
            create = client.post(
                f"{root_url}/api/models",
                json={
                    "name": f"benign-validation-{int(time.time())}",
                    "artifact_uri": upload.json()["artifact_uri"],
                },
            )
            create.raise_for_status()
            job = create.json()["validation_job"]
            deadline = time.monotonic() + args.timeout
            while job["status"] not in {"succeeded", "failed"}:
                if time.monotonic() >= deadline:
                    raise TimeoutError("validation did not finish")
                time.sleep(0.5)
                response = client.get(f"{root_url}/api/jobs/{job['id']}")
                response.raise_for_status()
                job = response.json()

    print(
        json.dumps(
            {
                "upload_status": upload.status_code,
                "create_status": create.status_code,
                "validation_status": job["status"],
                "validation_error": job.get("error"),
            }
        )
    )


if __name__ == "__main__":
    main()
