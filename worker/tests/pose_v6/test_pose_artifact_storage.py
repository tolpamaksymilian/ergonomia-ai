from __future__ import annotations

import json
from pathlib import Path
from typing import BinaryIO

import pytest

from worker.src.pose_artifact_storage import (
    GZIP_CONTENT_TYPE,
    compress_json_artifact,
    decompress_json_payload,
    upload_compressed_json,
)


class RecordingBucket:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.path: str | None = None
        self.payload: bytes | None = None
        self.file_options: dict[str, str] | None = None

    def upload(
        self,
        *,
        path: str,
        file: BinaryIO,
        file_options: dict[str, str],
    ) -> object:
        self.path = path
        self.payload = file.read()
        self.file_options = file_options
        if self.fail:
            raise RuntimeError("simulated upload failure")
        return {"path": path}


def _write_large_pose_document(path: Path) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "6.6",
        "analysis_id": "analysis-large-json",
        "frames": [
            {
                "source_frame_index": frame_index,
                "timestamp": frame_index / 30,
                "keypoints": [[point, point + 0.25, 0.95] for point in range(133)],
                "diagnostic_padding": "repeated-pose-data-" * 20,
            }
            for frame_index in range(2_000)
        ],
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return document


def test_large_pose_json_is_uploaded_as_gzip_and_round_trips(tmp_path: Path) -> None:
    source_path = tmp_path / "pose-keypoints.json"
    expected_document = _write_large_pose_document(source_path)
    assert source_path.stat().st_size > 5 * 1024 * 1024

    artifact = compress_json_artifact(
        source_path,
        "user/analysis/results/pose-keypoints.json",
    )
    bucket = RecordingBucket()
    upload_compressed_json(bucket, artifact)

    assert source_path.is_file()
    assert artifact.compressed_path.is_file()
    assert artifact.compressed_size_bytes < artifact.source_size_bytes
    assert bucket.path == "user/analysis/results/pose-keypoints.json.gz"
    assert bucket.file_options == {
        "content-type": GZIP_CONTENT_TYPE,
        "cache-control": "3600",
        "upsert": "true",
    }
    assert bucket.payload is not None
    restored = json.loads(decompress_json_payload(bucket.payload).decode("utf-8"))
    assert restored == expected_document


def test_failed_gzip_upload_preserves_local_artifacts(tmp_path: Path) -> None:
    source_path = tmp_path / "pose-keypoints.json"
    _write_large_pose_document(source_path)
    artifact = compress_json_artifact(
        source_path,
        "user/analysis/results/pose-keypoints.json",
    )

    with pytest.raises(RuntimeError, match="simulated upload failure"):
        upload_compressed_json(RecordingBucket(fail=True), artifact)

    assert source_path.is_file()
    assert artifact.compressed_path.is_file()


def test_plain_legacy_json_payload_remains_supported() -> None:
    payload = b'{"schema_version":"6.5","frames":[]}'
    assert decompress_json_payload(payload) == payload
