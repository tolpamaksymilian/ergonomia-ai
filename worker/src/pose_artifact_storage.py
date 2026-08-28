"""Storage helpers for large Pose JSON artifacts."""

from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


GZIP_CONTENT_TYPE = "application/gzip"
GZIP_MAGIC = b"\x1f\x8b"


class StorageBucket(Protocol):
    """Minimal Storage bucket contract used by the upload helper."""

    def upload(
        self,
        *,
        path: str,
        file: BinaryIO,
        file_options: dict[str, str],
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class CompressedJsonArtifact:
    source_path: Path
    compressed_path: Path
    storage_path: str
    source_size_bytes: int
    compressed_size_bytes: int
    content_type: str = GZIP_CONTENT_TYPE


def gzip_storage_path(json_storage_path: str) -> str:
    """Return the explicit gzip object path for a JSON Storage path."""

    normalized = json_storage_path.strip()
    if not normalized:
        raise ValueError("Storage path cannot be empty.")
    return normalized if normalized.endswith(".gz") else f"{normalized}.gz"


def compress_json_artifact(
    source_path: Path,
    json_storage_path: str,
    *,
    compresslevel: int = 6,
) -> CompressedJsonArtifact:
    """Create a deterministic gzip copy without removing the source JSON."""

    if not source_path.is_file():
        raise FileNotFoundError(f"JSON artifact does not exist: {source_path}")
    source_size = source_path.stat().st_size
    if source_size <= 0:
        raise ValueError(f"JSON artifact is empty: {source_path}")

    compressed_path = source_path.with_name(f"{source_path.name}.gz")
    with source_path.open("rb") as source, compressed_path.open("wb") as target:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=compresslevel,
            fileobj=target,
            mtime=0,
        ) as compressed:
            shutil.copyfileobj(source, compressed)

    compressed_size = compressed_path.stat().st_size
    if compressed_size <= 0:
        raise ValueError(f"Compressed JSON artifact is empty: {compressed_path}")

    return CompressedJsonArtifact(
        source_path=source_path,
        compressed_path=compressed_path,
        storage_path=gzip_storage_path(json_storage_path),
        source_size_bytes=source_size,
        compressed_size_bytes=compressed_size,
    )


def upload_compressed_json(
    bucket: StorageBucket,
    artifact: CompressedJsonArtifact,
) -> object:
    """Upload gzip bytes with an explicit gzip content contract and upsert."""

    with artifact.compressed_path.open("rb") as file_handle:
        return bucket.upload(
            path=artifact.storage_path,
            file=file_handle,
            file_options={
                "content-type": artifact.content_type,
                "cache-control": "3600",
                "upsert": "true",
            },
        )


def decompress_json_payload(payload: bytes | bytearray) -> bytes:
    """Transparently decode gzip JSON while retaining legacy plain JSON support."""

    raw_payload = bytes(payload)
    if raw_payload.startswith(GZIP_MAGIC):
        return gzip.decompress(raw_payload)
    return raw_payload


__all__ = [
    "CompressedJsonArtifact",
    "GZIP_CONTENT_TYPE",
    "compress_json_artifact",
    "decompress_json_payload",
    "gzip_storage_path",
    "upload_compressed_json",
]
