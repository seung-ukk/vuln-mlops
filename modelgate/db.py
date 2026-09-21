from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def init_db(path: str) -> None:
    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_jobs (
                id TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_validation_jobs_status_created "
            "ON validation_jobs(status, created_at)"
        )


def enqueue_job(path: str, model_name: str, model_version: str) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    timestamp = _now()
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO validation_jobs
                (id, model_name, model_version, status, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, model_name, str(model_version), timestamp, timestamp),
        )
    return get_job(path, job_id)


def get_job(path: str, job_id: str) -> dict[str, Any] | None:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM validation_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def claim_next_job(path: str) -> dict[str, Any] | None:
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT * FROM validation_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None
        connection.execute(
            "UPDATE validation_jobs SET status = 'running', updated_at = ? "
            "WHERE id = ? AND status = 'queued'",
            (_now(), row["id"]),
        )
        connection.execute("COMMIT")
        return get_job(path, row["id"])
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def finish_job(
    path: str,
    job_id: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    status = "failed" if error else "succeeded"
    result_json = json.dumps(result, ensure_ascii=False) if result else None
    with _connect(path) as connection:
        connection.execute(
            """
            UPDATE validation_jobs
            SET status = ?, result_json = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, result_json, error, _now(), job_id),
        )
    job = get_job(path, job_id)
    if job is None:
        raise LookupError(f"Unknown validation job: {job_id}")
    return job


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    if value.get("result_json"):
        value["result"] = json.loads(value.pop("result_json"))
    else:
        value.pop("result_json", None)
        value["result"] = None
    return value
