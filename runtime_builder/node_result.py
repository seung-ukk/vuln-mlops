"""Bounded display of a host-produced synthetic result.

This file is only a participant display channel. Operator verification must
also establish host systemd execution and the escape node's S3 data event.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


RESULT_PATH = Path("/node-evidence/result.json")
FLAG = re.compile(r"FLAG\{stage_5_iam_[a-z0-9_]+\}")
ACCOUNT = re.compile(r"[0-9]{12}")


def read_node_result(path: Path = RESULT_PATH) -> dict[str, str]:
    raw = path.read_bytes()
    if len(raw) > 512:
        raise ValueError("node result is too large")
    result = json.loads(raw)
    if not isinstance(result, dict) or set(result) != {"account", "role", "flag"}:
        raise ValueError("unexpected node result fields")
    account, role, flag = result["account"], result["role"], result["flag"]
    if not all(isinstance(value, str) for value in (account, role, flag)):
        raise ValueError("unexpected node result types")
    if not ACCOUNT.fullmatch(account) or not FLAG.fullmatch(flag):
        raise ValueError("unexpected synthetic identity or flag")
    if not re.fullmatch(
        rf"arn:aws:sts::{account}:assumed-role/vuln-mlops-escape-node/[^/]+",
        role,
    ):
        raise ValueError("unexpected node role")
    return result
