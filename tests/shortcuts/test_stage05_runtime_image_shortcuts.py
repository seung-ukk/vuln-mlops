from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "images" / "runtime-client"


def test_runtime_client_supply_chain_is_pinned() -> None:
    dockerfile = (IMAGE / "Dockerfile").read_text(encoding="utf-8")
    pinned_base = "debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251"
    assert dockerfile.count(pinned_base) == 2
    assert "ADD --checksum=sha256:" in dockerfile
    assert "apt-get" not in dockerfile
    assert "curl " not in dockerfile
    assert "wget " not in dockerfile


def test_runtime_client_does_not_bake_credentials_or_host_data() -> None:
    build_context = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(IMAGE.iterdir()) if path.is_file()
    )
    for forbidden in [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "serviceaccount",
        "/var/run/secrets",
        "/var/lib/vuln-mlops",
    ]:
        assert forbidden not in build_context
