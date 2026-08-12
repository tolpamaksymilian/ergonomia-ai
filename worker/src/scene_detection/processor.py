from __future__ import annotations

import math
import uuid
from typing import Iterable, Sequence

import cv2
import numpy as np
from numpy.typing import NDArray

from .schemas import DetectionCandidate, NormalizedBox, NormalizedLine, SceneObjectType


DETECTION_VERSION = "scene-detection-v0.2-beta.1"
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
    geometry_analysis: dict[str, object] | None = None,
) -> dict[str, object]:
    if not analysis_id.strip():
        raise ValueError("analysis_id is required")
    document: dict[str, object] = {
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
    if geometry_analysis:
        document.update({
            "geometry_candidates": geometry_analysis.get("geometry_candidates", []),
            "dimension_suggestions": geometry_analysis.get("dimension_suggestions", []),
            "perspective_evidence": geometry_analysis.get("perspective_evidence"),
            "floor_candidates": geometry_analysis.get("floor_candidates", []),
            "surface_candidates": geometry_analysis.get("surface_candidates", []),
        })
    return document


def analyze_scene_geometry(
    image: NDArray[np.uint8],
    candidates: Sequence[DetectionCandidate],
) -> dict[str, object]:
    """Builds editable geometric suggestions; it never claims real-world dimensions."""
    if image.ndim not in (2, 3) or image.size == 0:
        raise ValueError("image must be a non-empty grayscale or color array")
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 55, 145, apertureSize=3)
    raw_lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(25, min(width, height) // 18),
        minLineLength=max(24, min(width, height) // 12),
        maxLineGap=max(8, min(width, height) // 60),
    )
    lines: list[NormalizedLine] = []
    if raw_lines is not None:
        normalized_rows = np.asarray(raw_lines).reshape(-1, 4)
        ranked = sorted((tuple(int(value) for value in row) for row in normalized_rows), key=lambda row: math.hypot(row[2] - row[0], row[3] - row[1]), reverse=True)
        for index, (x1, y1, x2, y2) in enumerate(ranked[:80]):
            length = math.hypot(x2 - x1, y2 - y1)
            if length < max(20, min(width, height) * .04):
                continue
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180
            orientation = _line_orientation(angle)
            quality = "HIGH" if length >= min(width, height) * .32 else "MEDIUM" if length >= min(width, height) * .16 else "LOW"
            lines.append(NormalizedLine(
                id=f"geometry-{index}", start=(x1 / width, y1 / height), end=(x2 / width, y2 / height),
                orientation=orientation, evidence_quality=quality,
            ))
    geometry_candidates = [line.to_dict() for line in lines]
    floor_candidates = [line.to_dict() for line in lines if line.orientation == "HORIZONTAL" and (line.start[1] + line.end[1]) / 2 >= .58][:5]
    surface_candidates = _surface_candidates(lines, candidates)
    suggestions = [suggestion for candidate in candidates for suggestion in _dimension_suggestions(candidate)]
    vertical_angles = [_line_angle(line) for line in lines if line.orientation == "VERTICAL"]
    horizontal_angles = [_line_angle(line) for line in lines if line.orientation == "HORIZONTAL"]
    evidence_count = len(vertical_angles) + len(horizontal_angles)
    evidence_quality = "HIGH" if evidence_count >= 12 else "MEDIUM" if evidence_count >= 5 else "LOW"
    return {
        "geometry_candidates": geometry_candidates,
        "dimension_suggestions": suggestions,
        "perspective_evidence": {
            "dominant_vertical_angle_deg": _median(vertical_angles),
            "dominant_horizontal_angle_deg": _median(horizontal_angles),
            "vanishing_point": None,
            "evidence_quality": evidence_quality,
        },
        "floor_candidates": floor_candidates,
        "surface_candidates": surface_candidates,
    }


def _dimension_suggestions(candidate: DetectionCandidate) -> list[dict[str, object]]:
    box = candidate.bounding_box
    left, right, top, bottom = box.x, box.x + box.width, box.y, box.y + box.height
    center_x = (left + right) / 2
    profiles: dict[SceneObjectType, tuple[tuple[str, str], ...]] = {
        "TABLE": (("workSurfaceHeightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("depthCm", "DEPTH")),
        "WORK_SURFACE": (("workSurfaceHeightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("depthCm", "DEPTH")),
        "SHELF": (("keyShelfHeightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("depthCm", "DEPTH")),
        "RACK": (("heightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("depthCm", "DEPTH"), ("keyShelfHeightCm", "VERTICAL")),
        "CHAIR": (("seatHeightCm", "VERTICAL"), ("seatWidthCm", "HORIZONTAL"), ("seatDepthCm", "DEPTH"), ("backrestHeightCm", "VERTICAL")),
        "STOOL": (("seatHeightCm", "VERTICAL"), ("seatWidthCm", "HORIZONTAL"), ("seatDepthCm", "DEPTH")),
        "MONITOR": (("screenCenterHeightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("screenHeightCm", "VERTICAL")),
        "CONTAINER": (("heightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("depthCm", "DEPTH")),
        "MACHINE": (("heightCm", "VERTICAL"), ("widthCm", "HORIZONTAL"), ("depthCm", "DEPTH"), ("controlHeightCm", "VERTICAL")),
        "CONTROL_PANEL": (("controlHeightCm", "VERTICAL"), ("widthCm", "HORIZONTAL")),
    }
    suggestions: list[dict[str, object]] = []
    for index, (dimension_type, orientation) in enumerate(profiles.get(candidate.suggested_scene_type, ())):
        if orientation == "VERTICAL":
            start, end = {"x": center_x, "y": bottom}, {"x": center_x, "y": top}
        elif orientation == "HORIZONTAL":
            y = top + box.height * .18
            start, end = {"x": left, "y": y}, {"x": right, "y": y}
        else:
            start, end = {"x": left + box.width * .08, "y": top + box.height * .3}, {"x": right - box.width * .08, "y": top + box.height * .08}
        suggestions.append({
            "id": f"suggestion-{candidate.id}-{index}", "object_id": candidate.id,
            "dimension_type": dimension_type, "endpoints": {"start": start, "end": end},
            "source": "WORKER_GEOMETRY_HEURISTIC", "estimated_value_cm": None,
            "estimate_status": "UNKNOWN", "evidence_quality": "MEDIUM" if orientation != "DEPTH" else "LOW",
            "reason": _suggestion_reason(dimension_type, orientation), "status": "PENDING",
        })
    return suggestions


def _surface_candidates(lines: Sequence[NormalizedLine], candidates: Sequence[DetectionCandidate]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for candidate in candidates:
        box = candidate.bounding_box
        for line in lines:
            middle_x, middle_y = (line.start[0] + line.end[0]) / 2, (line.start[1] + line.end[1]) / 2
            if line.orientation == "HORIZONTAL" and box.x <= middle_x <= box.x + box.width and box.y <= middle_y <= box.y + box.height * .55:
                selected.append({**line.to_dict(), "object_id": candidate.id})
                break
    return selected[:20]


def _line_orientation(angle: float) -> str:
    if angle <= 12 or angle >= 168:
        return "HORIZONTAL"
    if 78 <= angle <= 102:
        return "VERTICAL"
    return "DEPTH"


def _line_angle(line: NormalizedLine) -> float:
    return math.degrees(math.atan2(line.end[1] - line.start[1], line.end[0] - line.start[0]))


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _suggestion_reason(dimension_type: str, orientation: str) -> str:
    if orientation == "DEPTH":
        return f"Candidate edge for {dimension_type}; depth remains unknown without reliable perspective evidence."
    return f"Candidate {orientation.lower()} edge derived from the confirmed object region for {dimension_type}."
