from __future__ import annotations

import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class ArtifactUploadError(ValueError):
    """Raised when an uploaded model bundle is not safe or usable."""


@dataclass(frozen=True)
class UploadLimits:
    max_files: int
    max_extracted_bytes: int


@dataclass(frozen=True)
class StoredArtifact:
    upload_id: str
    artifact_uri: str
    local_path: Path
    file_count: int
    extracted_bytes: int


def _safe_member_path(staging: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    member = PurePosixPath(normalized)
    if (
        member.is_absolute()
        or not member.parts
        or any(part in {"", ".", ".."} for part in member.parts)
        or ":" in member.parts[0]
    ):
        raise ArtifactUploadError(f"Unsafe archive path: {member_name!r}")

    target = staging.joinpath(*member.parts).resolve()
    if not target.is_relative_to(staging.resolve()):
        raise ArtifactUploadError(f"Archive path escapes upload root: {member_name!r}")
    return target


def store_model_bundle(
    archive_path: Path,
    upload_root: Path,
    limits: UploadLimits,
) -> StoredArtifact:
    """Validate and atomically store one zipped MLflow model directory."""

    upload_root = upload_root.resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".extract-", dir=upload_root))
    destination: Path | None = None

    try:
        try:
            archive = zipfile.ZipFile(archive_path)
        except zipfile.BadZipFile as exc:
            raise ArtifactUploadError("The request body is not a valid ZIP archive") from exc

        file_count = 0
        extracted_bytes = 0
        with archive:
            for info in archive.infolist():
                if info.flag_bits & 0x1:
                    raise ArtifactUploadError("Encrypted ZIP entries are not supported")

                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise ArtifactUploadError("Symbolic links are not allowed in model bundles")

                target = _safe_member_path(staging, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                file_count += 1
                if file_count > limits.max_files:
                    raise ArtifactUploadError(
                        f"Model bundle contains more than {limits.max_files} files"
                    )
                if target.exists():
                    raise ArtifactUploadError(
                        f"Model bundle contains a duplicate path: {info.filename!r}"
                    )

                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        extracted_bytes += len(chunk)
                        if extracted_bytes > limits.max_extracted_bytes:
                            raise ArtifactUploadError(
                                "Extracted model bundle exceeds the configured size limit"
                            )
                        output.write(chunk)

        manifests = [path for path in staging.rglob("MLmodel") if path.is_file()]
        if len(manifests) != 1:
            raise ArtifactUploadError(
                "Model bundle must contain exactly one MLflow MLmodel manifest"
            )

        model_root = manifests[0].parent
        upload_id = uuid.uuid4().hex
        destination = upload_root / upload_id
        model_root.replace(destination)

        return StoredArtifact(
            upload_id=upload_id,
            artifact_uri=destination.as_uri(),
            local_path=destination,
            file_count=file_count,
            extracted_bytes=extracted_bytes,
        )
    except Exception:
        if destination is not None:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def publish_logged_model(
    stored: StoredArtifact,
    tracking_uri: str,
    experiment_id: str,
) -> str:
    """Upload a validated directory through MLflow and return a models:/ URI."""

    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri)
    logged_model = client.create_logged_model(
        experiment_id=experiment_id,
        name=f"external-upload-{stored.upload_id}",
        tags={
            "modelgate.source": "external-upload",
            "modelgate.upload_id": stored.upload_id,
        },
    )
    try:
        client.log_model_artifacts(logged_model.model_id, str(stored.local_path))
        client.finalize_logged_model(logged_model.model_id, status="READY")
    except Exception:
        try:
            client.finalize_logged_model(logged_model.model_id, status="FAILED")
        except Exception:
            pass
        raise
    return f"models:/{logged_model.model_id}"


def remove_stored_bundle(stored: StoredArtifact) -> None:
    """Remove the local upload after MLflow has copied it or publishing failed."""

    shutil.rmtree(stored.local_path, ignore_errors=True)
