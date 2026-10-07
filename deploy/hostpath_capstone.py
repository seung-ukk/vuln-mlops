"""Mentor-only Stage 4 Git manifest generator for the hostPath capstone.

The generated Pod writes a task to the escape worker's fixed hostPath. The
worker's systemd unit, not the Pod, executes that task with the node role.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


IMAGE = re.compile(r"ghcr\.io/seung-ukk/vuln-mlops@sha256:[a-f0-9]{64}")
BUCKET = re.compile(r"vuln-mlops-personal-lab-[0-9]{12}-runtime-proof")
BASE = Path(__file__).resolve().parents[1] / "lab/stages/stage-05-hostpath/runtime-builder-base.yaml.in"


def host_task(bucket: str) -> str:
    if not BUCKET.fullmatch(bucket):
        raise ValueError("unexpected lab S3 bucket")
    return f"""#!/bin/bash
set -euo pipefail
export AWS_DEFAULT_REGION=ap-northeast-2 AWS_PAGER=
account="$(aws sts get-caller-identity --query Account --output text)"
role="$(aws sts get-caller-identity --query Arn --output text)"
[[ "$account" =~ ^[0-9]{{12}}$ ]]
[[ "$role" =~ ^arn:aws:sts::${{account}}:assumed-role/vuln-mlops-escape-node/[^/]+$ ]]
proof_file="$(mktemp)"
trap 'rm -f "$proof_file"' EXIT
aws s3api get-object --bucket {bucket} --key proof/final-flag.txt "$proof_file" >/dev/null
flag="$(cat "$proof_file")"
[[ "$flag" =~ ^FLAG\\{{stage_5_iam_[a-z0-9_]+\\}}$ ]]
printf '{{"account":"%s","role":"%s","flag":"%s"}}\\n' "$account" "$role" "$flag" > /var/lib/vuln-mlops/node-evidence/result.json
chmod 0600 /var/lib/vuln-mlops/node-evidence/result.json
printf 'vuln-mlops host maintenance complete uid=%s\\n' "$(id -u)"
"""


def desired_manifest(image: str, bucket: str) -> dict:
    if not IMAGE.fullmatch(image):
        raise ValueError("expected a reviewed OCI index digest")
    deployment = yaml.safe_load(BASE.read_text(encoding="utf-8").replace("__RUNTIME_BUILDER_IMAGE__", image))
    template = deployment["spec"]["template"]
    template["metadata"]["annotations"] = {
        "lab.vuln-mlops/stage-04-proof": "FLAG{stage_4_gitops_placeholder}"
    }
    pod = template["spec"]
    pod["securityContext"]["runAsUser"] = 0
    pod["securityContext"]["runAsGroup"] = 0
    container = pod["containers"][0]
    container["command"] = ["/bin/sh", "-c"]
    container["args"] = [
        "cat > /host-maintenance/task.sh <<'HOSTTASK'\n"
        + host_task(bucket)
        + "HOSTTASK\n"
        + "exec uvicorn runtime_builder.main:app --host 0.0.0.0 --port 8080"
    ]
    container["volumeMounts"][1]["readOnly"] = False
    return deployment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    deployment = desired_manifest(args.image, args.bucket)
    # The command contains a host Bash script; preserve LF even when mentors
    # generate the Git manifest from Windows.
    args.output.write_bytes(yaml.safe_dump(deployment, sort_keys=False).encode("utf-8"))


if __name__ == "__main__":
    main()
