"""Strict JSON serialization boundary for final Pose V6 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from worker.src.json_utils import JsonSerializationError, make_json_safe
except ModuleNotFoundError:  # pragma: no cover - worker/src direct execution
    from json_utils import JsonSerializationError, make_json_safe


class PoseOutputSerializationError(TypeError):
    """A final Pose artifact violated the approved JSON output contract."""

    error_code = "POSE_OUTPUT_SERIALIZATION_ERROR"

    def __init__(
        self,
        *,
        document_name: str,
        cause: JsonSerializationError,
    ) -> None:
        self.document_name = document_name
        self.path = cause.path
        self.python_type = cause.python_type
        self.value_preview = cause.value_preview
        super().__init__(
            f"{self.error_code} document={document_name} "
            f"path={cause.path} type={cause.python_type} "
            f"value={cause.value_preview} reason={cause.reason}"
        )


def serialize_pose_document(
    document: dict[str, Any],
    *,
    document_name: str,
    pretty: bool = False,
) -> str:
    """Normalize and serialize one final Pose artifact as strict JSON."""

    try:
        safe_document = make_json_safe(document)
    except JsonSerializationError as error:
        raise PoseOutputSerializationError(
            document_name=document_name,
            cause=error,
        ) from error
    return json.dumps(
        safe_document,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        allow_nan=False,
    )


def write_pose_document(
    path: Path,
    document: dict[str, Any],
    *,
    document_name: str,
    pretty: bool = False,
) -> None:
    """Write a complete, validated Pose artifact in UTF-8."""

    path.write_text(
        serialize_pose_document(
            document,
            document_name=document_name,
            pretty=pretty,
        ),
        encoding="utf-8",
    )


__all__ = [
    "PoseOutputSerializationError",
    "serialize_pose_document",
    "write_pose_document",
]
