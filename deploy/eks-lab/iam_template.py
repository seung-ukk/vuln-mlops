"""Build and verify the one-time socket-to-IAM Deployment template patch.

Input is JSON emitted by kubectl. No Kubernetes or AWS client is used here.
"""

from __future__ import annotations

import json
import sys


def make_patch(deployment: dict) -> list[dict]:
    if deployment.get("kind") != "Deployment" or deployment.get("metadata", {}).get("name") != "runtime-builder":
        raise ValueError("expected the reviewed runtime-builder Deployment")
    if deployment["metadata"].get("namespace") != "stage-05-runtime":
        raise ValueError("unexpected Deployment namespace")
    return [{"op": "replace", "path": "/spec/template", "value": deployment["spec"]["template"]}]


def verify_preview(deployment: dict, expected_image: str) -> None:
    pod = deployment["spec"]["template"]["spec"]
    if pod.get("serviceAccountName") != "runtime-builder-iam":
        raise ValueError("IRSA ServiceAccount is missing")
    if pod.get("nodeSelector") != {"lab.vuln-mlops/node-role": "general", "kubernetes.io/arch": "amd64"}:
        raise ValueError("unexpected node placement")
    if pod.get("tolerations") or pod.get("initContainers"):
        raise ValueError("old escape-node fields remain")
    containers = pod.get("containers", [])
    if len(containers) != 1 or containers[0].get("name") != "runtime-builder" or containers[0].get("image") != expected_image:
        raise ValueError("unexpected runtime-builder container")
    if [volume.get("name") for volume in pod.get("volumes", [])] != ["tmp"]:
        raise ValueError("old runtime socket or other volumes remain")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: iam_template.py patch|verify [expected-image]")
    document = json.load(sys.stdin)
    if sys.argv[1] == "patch" and len(sys.argv) == 2:
        json.dump(make_patch(document), sys.stdout)
    elif sys.argv[1] == "verify" and len(sys.argv) == 3:
        verify_preview(document, sys.argv[2])
        print("IAM Deployment template preview contains only the reviewed app and tmp volume")
    else:
        raise SystemExit("usage: iam_template.py patch|verify [expected-image]")


if __name__ == "__main__":
    main()
