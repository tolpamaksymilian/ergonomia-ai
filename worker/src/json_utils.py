"""Strict, path-aware conversion of approved values to standard JSON types."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TypeAlias

import numpy as np


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_SIMPLE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class JsonSerializationError(TypeError):
    """An unsupported JSON value with its exact location in the document."""

    def __init__(self, *, path: str, value: object, reason: str) -> None:
        value_type = type(value)
        self.path = path
        self.python_type = f"{value_type.__module__}.{value_type.__qualname__}"
        self.value_preview = _value_preview(value)
        self.reason = reason
        super().__init__(
            "JSON_SERIALIZATION_ERROR "
            f"path={path} type={value_type.__name__} "
            f"python_type={self.python_type} value={self.value_preview} "
            f"reason={reason}"
        )


def make_json_safe(value: object, *, path: str = "$") -> JsonValue:
    """Normalize approved Python/NumPy values in one recursive pass.

    Non-finite floats represent unavailable measurements in the Pose contract,
    so they become ``None``. Unknown classes and non-string mapping keys remain
    programming errors and are rejected with an exact document path.
    """

    return _make_json_safe(value, path=path, active_containers=set())


def _make_json_safe(
    value: object,
    *,
    path: str,
    active_containers: set[int],
) -> JsonValue:
    if isinstance(value, Enum):
        return _make_json_safe(
            value.value,
            path=path,
            active_containers=active_containers,
        )
    if isinstance(value, np.ndarray):
        return _normalize_sequence(
            value.tolist(),
            path=path,
            active_containers=active_containers,
        )
    if isinstance(value, np.generic):
        return _make_json_safe(
            value.item(),
            path=path,
            active_containers=active_containers,
        )
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_mapping(
            asdict(value),
            path=path,
            active_containers=active_containers,
        )
    if isinstance(value, dict):
        return _normalize_mapping(
            value,
            path=path,
            active_containers=active_containers,
        )
    if isinstance(value, (list, tuple)):
        return _normalize_sequence(
            value,
            path=path,
            active_containers=active_containers,
        )
    raise JsonSerializationError(
        path=path,
        value=value,
        reason="unsupported_type",
    )


def _normalize_mapping(
    value: dict[object, object],
    *,
    path: str,
    active_containers: set[int],
) -> dict[str, JsonValue]:
    identity = id(value)
    _enter_container(identity, value, path, active_containers)
    try:
        output: dict[str, JsonValue] = {}
        for raw_key, item in value.items():
            key = _normalize_key(raw_key, path=path)
            output[key] = _make_json_safe(
                item,
                path=_child_path(path, key),
                active_containers=active_containers,
            )
        return output
    finally:
        active_containers.remove(identity)


def _normalize_sequence(
    value: list[object] | tuple[object, ...],
    *,
    path: str,
    active_containers: set[int],
) -> list[JsonValue]:
    identity = id(value)
    _enter_container(identity, value, path, active_containers)
    try:
        return [
            _make_json_safe(
                item,
                path=f"{path}[{index}]",
                active_containers=active_containers,
            )
            for index, item in enumerate(value)
        ]
    finally:
        active_containers.remove(identity)


def _normalize_key(value: object, *, path: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, str):
        return value
    raise JsonSerializationError(
        path=f"{path}.<key>",
        value=value,
        reason="dictionary_key_must_be_string",
    )


def _enter_container(
    identity: int,
    value: object,
    path: str,
    active_containers: set[int],
) -> None:
    if identity in active_containers:
        raise JsonSerializationError(
            path=path,
            value=value,
            reason="cyclic_reference",
        )
    active_containers.add(identity)


def _child_path(path: str, key: str) -> str:
    if _SIMPLE_KEY.fullmatch(key):
        return f"{path}.{key}"
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'{path}["{escaped}"]'


def _value_preview(value: object, maximum_length: int = 120) -> str:
    try:
        rendered = repr(value)
    except (TypeError, ValueError, RuntimeError):
        rendered = "<unrepresentable>"
    rendered = rendered.replace("\r", "\\r").replace("\n", "\\n")
    if len(rendered) > maximum_length:
        return f"{rendered[: maximum_length - 3]}..."
    return rendered


__all__ = ["JsonSerializationError", "JsonValue", "make_json_safe"]
