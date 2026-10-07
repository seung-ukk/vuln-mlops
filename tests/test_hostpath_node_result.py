from __future__ import annotations

import json

import pytest

from runtime_builder.node_result import RESULT_PATH, read_node_result


VALID = {
    "account": "707605822656",
    "role": "arn:aws:sts::707605822656:assumed-role/vuln-mlops-escape-node/i-lab123",
    "flag": "FLAG{stage_5_iam_placeholder}",
}


def test_display_reads_the_separate_read_only_evidence_mount():
    assert RESULT_PATH.as_posix() == "/node-evidence/result.json"


def test_bounded_host_result_accepts_only_the_escape_node_role(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps(VALID), encoding="utf-8")
    assert read_node_result(result) == VALID


@pytest.mark.parametrize(
    "change",
    [
        {"role": "arn:aws:sts::707605822656:assumed-role/vuln-mlops-personal-lab-runtime-builder/pod"},
        {"role": "arn:aws:sts::707605822656:assumed-role/vuln-mlops-general-node/i-lab123"},
        {"flag": "AKIAEXAMPLE"},
        {"account": "000000000000"},
        {"extra": "arbitrary-data"},
    ],
)
def test_host_result_rejects_wrong_identity_or_unbounded_fields(tmp_path, change):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({**VALID, **change}), encoding="utf-8")
    with pytest.raises(ValueError):
        read_node_result(result)


def test_host_result_rejects_oversized_file(tmp_path):
    result = tmp_path / "result.json"
    result.write_bytes(b"x" * 513)
    with pytest.raises(ValueError):
        read_node_result(result)
