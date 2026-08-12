from __future__ import annotations

import math
import uuid
from typing import Iterable, Sequence

from .schemas import DetectionCandidate, NormalizedBox, SceneObjectType


DETECTION_VERSION = "scene-detection-v0.1-beta.1"
COCO_CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)
CLASS_MAPPING: dict[int, SceneObjectType] = {
    56: "CHAIR", 57: "CHAIR", 60: "TABLE", 62: "MONITOR", 63: "MONITOR",
    66: "CONTROL_PANEL", 67: "CONTROL_PANEL", 68: "MACHINE", 69: "MACHINE",
    70: "MACHINE", 71: "WORK_SURFACE", 72: "MACHINE", 39: "CONTAINER",
    41: "CONTAINER", 45: "CONTAINER",
}


def _iou(a: NormalizedBox, b: NormalizedBox) -> float:
    left, top = max(a.x, b.x), max(a.y, b.y)
    right, bottom = min(a.x + a.width, b.x + b.width), min(a.y + a.height, b.y + b.height)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = a.width * a.height + b.width * b.height - intersection
    return intersection / union if union > 0 else 0.0


def normalize_detections(
    boxes: Iterable[Sequence[float]],
    class_ids: Iterable[int],
    *,
    image_width: int,
    image_height: int,
) -> list[DetectionCandidate]:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    candidates: list[DetectionCandidate] = []
    for index, (raw_box, raw_class_id) in enumerate(zip(boxes, class_ids)):
        if len(raw_box) < 4:
            continue
        values = [float(value) for value in raw_box[:4]]
        if not all(math.isfinite(value) for value in values):
            continue
        class_id = int(raw_class_id)
        scene_type = CLASS_MAPPING.get(class_id)
        if scene_type is None:
            continue
        x1, y1, x2, y2 = values
        x1 = min(max(x1, 0.0), float(image_width))
        y1 = min(max(y1, 0.0), float(image_height))
        x2 = min(max(x2, 0.0), float(image_width))
        y2 = min(max(y2, 0.0), float(image_height))
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        box = NormalizedBox(x1 / image_width, y1 / image_height, (x2 - x1) / image_width, (y2 - y1) / image_height)
        if any(item.suggested_scene_type == scene_type and _iou(item.bounding_box, box) >= 0.85 for item in candidates):
            continue
        source_class = COCO_CLASSES[class_id] if 0 <= class_id < len(COCO_CLASSES) else f"class_{class_id}"
        candidates.append(DetectionCandidate(
            id=f"detected-{index}-{uuid.uuid4().hex[:10]}",
            source_class=source_class,
            suggested_scene_type=scene_type,
            bounding_box=box,
            confidence=None,
        ))
    return candidates


def build_detection_document(
    analysis_id: str,
    image_width: int,
    image_height: int,
    candidates: Sequence[DetectionCandidate],
) -> dict[str, object]:
    if not analysis_id.strip():
        raise ValueError("analysis_id is required")
    return {
        "schema_version": "1.0",
        "detection_version": DETECTION_VERSION,
        "analysis_id": analysis_id,
        "source_image": {"width": image_width, "height": image_height},
        "candidates": [candidate.to_dict() for candidate in candidates],
        "limitations": [
            "detection_requires_user_confirmation",
            "industrial_objects_may_be_missing",
            "detector_confidence_unavailable_in_current_rtmlib_adapter",
            "no_depth_reconstruction",
            "no_ergonomic_assessment",
        ],
    }
