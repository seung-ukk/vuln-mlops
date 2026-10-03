from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "lab" / "stages" / "stage-02-rbac"


def documents(filename: str) -> list[dict]:
    with (STAGE / filename).open(encoding="utf-8") as stream:
        return [document for document in yaml.safe_load_all(stream) if document]


def document(filename: str, kind: str, name: str) -> dict:
    for item in documents(filename):
        if item["kind"] == kind and item.get("metadata", {}).get("name", "") == name:
            return item
    raise AssertionError(f"missing {kind}/{name} in {filename}")


def rule_for(role: dict, resource: str) -> dict:
    for rule in role["rules"]:
        if resource in rule["resources"]:
            return rule
    raise AssertionError(f"missing rule for {resource}")
