"""Read only the lab's fixed S3 proof object with the workload IRSA identity."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


PROOF_PATTERN = re.compile(r"FLAG\{stage_5_iam_[a-z0-9_]+\}")
PROOF_PATH = Path("/tmp/runtime-builder-iam-proof.json")
OBJECT_KEY = "proof/final-flag.txt"


def collect_proof() -> dict[str, str]:
    import boto3

    bucket = os.environ["RUNTIME_PROOF_BUCKET"]
    identity = boto3.client("sts").get_caller_identity()
    account = identity["Account"]
    arn = identity["Arn"]
    if not re.fullmatch(r"arn:aws:sts::[0-9]{12}:assumed-role/[^/]*runtime-builder/[^/]+", arn):
        raise RuntimeError("unexpected AWS identity")
    if account not in arn:
        raise RuntimeError("AWS account mismatch")

    response = boto3.client("s3").get_object(Bucket=bucket, Key=OBJECT_KEY)
    raw = response["Body"].read(129)
    if len(raw) > 128:
        raise RuntimeError("synthetic proof is too large")
    proof = raw.decode("ascii").strip()
    if PROOF_PATTERN.fullmatch(proof) is None:
        raise RuntimeError("unexpected synthetic proof")
    result = {"account": account, "role": arn, "flag": proof}
    fd = os.open(PROOF_PATH, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(result, stream)
    return result


if __name__ == "__main__":
    collect_proof()
