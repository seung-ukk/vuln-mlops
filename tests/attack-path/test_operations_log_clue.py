from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml
import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_metric_points_to_log_while_credential_stays_out_of_metric(tmp_path: Path) -> None:
    documents = list(
        yaml.safe_load_all(
            (ROOT / "lab/participant-chain/observability/config.yaml").read_text()
        )
    )
    program = next(item for item in documents if item["metadata"]["name"] == "operations-log-program")
    script = tmp_path / "server.py"
    script.write_text(program["data"]["server.py"])

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    env = os.environ | {
        "GIT_USERNAME": "lab-git-writer",
        "GIT_TOKEN": "synthetic-test-token",
        "LAB_OPERATIONS_LOG_LISTEN_PORT": str(port),
    }
    process = subprocess.Popen(
        [sys.executable, str(script)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=1) as response:
                    metrics = response.read().decode()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("operations-log did not start")

        assert 'log_namespace="observability-lab"' in metrics
        assert 'log_selector="app=operations-log"' in metrics
        assert "synthetic-test-token" not in metrics
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/exchange", timeout=1)
        assert exc.value.code == 404
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=5)
    assert "synthetic-test-token" in output
