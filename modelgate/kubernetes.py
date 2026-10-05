from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

SERVICE_ACCOUNT_ROOT = Path("/var/run/secrets/kubernetes.io/serviceaccount")
STAGE2_NAMESPACE = "stage-02-rbac"
STAGE2_JOB_NAME = "stage-02-secret-reader"
STAGE2_POD_PREFIX = f"{STAGE2_JOB_NAME}-"
STAGE2_POD_SELECTOR = f"job-name={STAGE2_JOB_NAME}"


def build_kubernetes_client() -> httpx.AsyncClient | None:
    """Create an in-cluster client from the mounted Pod identity, if present."""

    host = os.getenv("KUBERNETES_SERVICE_HOST")
    port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    token_path = SERVICE_ACCOUNT_ROOT / "token"
    ca_path = SERVICE_ACCOUNT_ROOT / "ca.crt"
    if not host or not token_path.is_file() or not ca_path.is_file():
        return None

    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        return None

    return httpx.AsyncClient(
        base_url=f"https://{host}:{port}",
        headers={"Authorization": f"Bearer {token}"},
        verify=str(ca_path),
        timeout=httpx.Timeout(15.0),
    )


def stage2_job_manifest() -> dict[str, Any]:
    """Return the only workload the foothold relay may submit."""

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": STAGE2_JOB_NAME,
            "namespace": STAGE2_NAMESPACE,
            "labels": {"lab.vuln-mlops/stage": "02"},
        },
        "spec": {
            "backoffLimit": 0,
            "template": {
                "metadata": {"labels": {"lab.vuln-mlops/stage": "02"}},
                "spec": {
                    "serviceAccountName": "monitoring-runner",
                    "automountServiceAccountToken": True,
                    "restartPolicy": "Never",
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 65532,
                        "runAsGroup": 65532,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "reader",
                            "image": (
                                "registry.k8s.io/kubectl:v1.37.0@sha256:"
                                "5ed410ebac5dc976cc717098994dcdb29bbbd38f6bd65f582"
                                "311f5be4ba719cf"
                            ),
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["/bin/kubectl"],
                            "args": [
                                "get",
                                "secret",
                                "stage-02-flag",
                                f"--namespace={STAGE2_NAMESPACE}",
                                "--output=jsonpath={.data.flag}",
                            ],
                            "resources": {
                                "requests": {"cpu": "10m", "memory": "16Mi"},
                                "limits": {"cpu": "100m", "memory": "64Mi"},
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "privileged": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                },
            },
        },
    }


def stage2_job_status(job: dict[str, Any], *, created: bool) -> dict[str, Any]:
    status = job.get("status", {})
    return {
        "name": STAGE2_JOB_NAME,
        "namespace": STAGE2_NAMESPACE,
        "created": created,
        "active": int(status.get("active", 0)),
        "succeeded": int(status.get("succeeded", 0)),
        "failed": int(status.get("failed", 0)),
    }
