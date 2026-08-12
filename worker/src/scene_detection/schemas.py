from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


SceneObjectType = Literal[
    "WORK_SURFACE", "TABLE", "SHELF", "RACK", "CHAIR", "STOOL", "CONVEYOR",
    "MACHINE", "CONTROL_PANEL", "MONITOR", "CONTAINER", "PALLET", "OTHER",
]


@dataclass(frozen=True)
class NormalizedBox:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class DetectionCandidate:
    id: str
    source_class: str
    suggested_scene_type: SceneObjectType
    bounding_box: NormalizedBox
    confidence: float | None
    source: Literal["YOLOX_X_COCO"] = "YOLOX_X_COCO"
    status: Literal["DETECTED"] = "DETECTED"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
