"""Provider contracts keep baseline and optional refinement backends isolated."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class BodyPoseProvider(Protocol):
    provider_id: str
    provider_version: str

    def infer(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...


class HandPoseProvider(Protocol):
    provider_id: str
    provider_version: str

    def infer(self, frame: np.ndarray, timestamp_ms: int, roi: tuple[int, int, int, int] | None) -> object: ...


class ObjectDetectorProvider(Protocol):
    provider_id: str
    provider_version: str

    def detections(self) -> list[object]: ...
