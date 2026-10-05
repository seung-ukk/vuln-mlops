import io
import json
import sys
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

from runtime_builder import aws_proof
from runtime_builder.main import RELAY_HEADER, app


RELAY_HEADERS = {"x-modelgate-relay": RELAY_HEADER}


ROOT = Path(__file__).resolve().parents[1]


def test_image_build_includes_the_app_and_reviewed_aws_sdk():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements" / "base.txt").read_text(encoding="utf-8")
    assert "COPY --chown=10001:10001 runtime_builder /opt/modelgate/runtime_builder" in dockerfile
    assert "boto3==1.43.105" in requirements


def test_participant_repository_readme_explains_build_input_without_exposing_proof():
    readme = (
        ROOT / "lab" / "stages" / "stage-05-iam-app" / "repository"
        / "runtime-builder" / "README.md"
    ).read_text(encoding="utf-8")
    assert "source_ref" in readme
    assert "shell command" in readme
    assert "runtime-builder-iam" in readme
    assert "FLAG{" not in readme


def test_build_is_unavailable_before_git_mode_change(monkeypatch):
    monkeypatch.setenv("BUILDER_MODE", "baseline")
    called = []
    monkeypatch.setattr("runtime_builder.main.subprocess.run", lambda *a, **kw: called.append(a))
    with TestClient(app) as client:
        response = client.post("/build", json={"source_ref": "main"}, headers=RELAY_HEADERS)
    assert response.status_code == 409
    assert called == []


def test_build_info_exposes_bounded_discovery_clues(monkeypatch):
    monkeypatch.setenv("BUILDER_MODE", "legacy-build")
    with TestClient(app) as client:
        response = client.get("/build/info")
    assert response.status_code == 200
    assert response.json()["input_field"] == "source_ref"
    assert response.json()["resolver"] == "legacy shell-based source lookup"
    assert "command" not in response.json()


def test_legacy_build_uses_the_intentionally_vulnerable_shell_composition(monkeypatch):
    monkeypatch.setenv("BUILDER_MODE", "legacy-build")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("runtime_builder.main.subprocess.run", fake_run)
    with TestClient(app) as client:
        response = client.post(
            "/build",
            json={"source_ref": "main; python -m runtime_builder.aws_proof; #"},
            headers=RELAY_HEADERS,
        )
    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    assert calls[0][1]["shell"] is True
    assert "; python -m runtime_builder.aws_proof; #" in calls[0][0]


def test_fixed_aws_proof_validates_identity_and_object_without_credentials(tmp_path, monkeypatch):
    target = tmp_path / "proof.json"
    monkeypatch.setattr(aws_proof, "PROOF_PATH", target)
    monkeypatch.setenv("RUNTIME_PROOF_BUCKET", "lab-proof-bucket")
    requested = []

    class FakeSTS:
        def get_caller_identity(self):
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/lab-runtime-builder/session",
                "UserId": "ignored",
            }

    class FakeS3:
        def get_object(self, **kwargs):
            requested.append(kwargs)
            return {"Body": io.BytesIO(b"FLAG{stage_5_iam_placeholder}\n")}

    clients = {"sts": FakeSTS(), "s3": FakeS3()}
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=clients.__getitem__))
    result = aws_proof.collect_proof()

    assert requested == [{"Bucket": "lab-proof-bucket", "Key": "proof/final-flag.txt"}]
    assert result == {
        "account": "123456789012",
        "role": "arn:aws:sts::123456789012:assumed-role/lab-runtime-builder/session",
        "flag": "FLAG{stage_5_iam_placeholder}",
    }
    assert json.loads(target.read_text(encoding="utf-8")) == result
    assert "UserId" not in target.read_text(encoding="utf-8")


def test_proof_endpoint_returns_only_validated_synthetic_result(tmp_path, monkeypatch):
    from runtime_builder import main

    monkeypatch.setenv("BUILDER_MODE", "legacy-build")
    monkeypatch.setattr(main, "PROOF_PATH", tmp_path / "proof.json")
    with TestClient(app) as client:
        assert client.get("/proof", headers=RELAY_HEADERS).status_code == 404
        main.PROOF_PATH.write_text('{"account":"123456789012","role":"bad","flag":"FLAG{stage_5_iam_placeholder}"}')
        assert client.get("/proof", headers=RELAY_HEADERS).status_code == 502


def test_build_and_proof_deny_direct_requests_without_modelgate_relay(monkeypatch):
    monkeypatch.setenv("BUILDER_MODE", "legacy-build")
    with TestClient(app) as client:
        assert client.post("/build", json={"source_ref": "main"}).status_code == 403
        assert client.get("/proof").status_code == 403
