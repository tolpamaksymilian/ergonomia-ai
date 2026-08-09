"""Safe, quality-aware and temporally stable overlay for Pose V4."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

import cv2
import numpy as np

try:
    from ..pose_v3.body_validation import BODY_BONES
    from ..pose_v3.hand_pipeline import HAND_EDGES
except ImportError:  # pragma: no cover - standalone worker import mode
    from pose_v3.body_validation import BODY_BONES
    from pose_v3.hand_pipeline import HAND_EDGES

from .graph import MeasurementSource, PoseGraphFrame
from .hand_graph import HandGraphFrame
from .holding import HoldingFrameV2, HoldingStateV2
from .object_tracking import TrackedObject


class VisualSeverity(StrEnum):
    NEUTRAL = "neutral"
    MILD = "mild"
    ELEVATED = "elevated"
    STRONG = "strong"
    UNKNOWN = "unknown"
    TEMPORARY = "temporary"


class BoneRenderPhase(StrEnum):
    VISIBLE = "VISIBLE"
    FADING_OUT = "FADING_OUT"
    HIDDEN = "HIDDEN"
    FADING_IN = "FADING_IN"


@dataclass(frozen=True)
class OverlayPalette:
    neutral: tuple[int, int, int] = (153, 211, 54)
    mild: tuple[int, int, int] = (21, 204, 250)
    elevated: tuple[int, int, int] = (60, 146, 251)
    strong: tuple[int, int, int] = (68, 68, 239)
    unknown: tuple[int, int, int] = (184, 163, 148)
    temporary: tuple[int, int, int] = (250, 165, 96)
    holding: tuple[int, int, int] = (250, 139, 167)
    object: tuple[int, int, int] = (238, 211, 34)
    debug_rejected: tuple[int, int, int] = (80, 80, 255)
    debug_expected: tuple[int, int, int] = (255, 170, 70)
    text: tuple[int, int, int] = (245, 245, 245)
    shadow: tuple[int, int, int] = (12, 18, 28)

    def severity(self, value: VisualSeverity) -> tuple[int, int, int]:
        return {
            VisualSeverity.NEUTRAL: self.neutral,
            VisualSeverity.MILD: self.mild,
            VisualSeverity.ELEVATED: self.elevated,
            VisualSeverity.STRONG: self.strong,
            VisualSeverity.UNKNOWN: self.unknown,
            VisualSeverity.TEMPORARY: self.temporary,
        }[value]


@dataclass(frozen=True)
class VisualMetricRule:
    boundaries: tuple[float, float, float]
    center: float = 0.0
    absolute: bool = True

    def magnitude(self, value: float) -> float:
        return abs(value - self.center) if self.absolute else value


# These are non-normative geometric visualization bands. They are not RULA,
# REBA or a safety decision and never enter Risk Engine calculations.
VISUAL_METRIC_RULES: dict[str, VisualMetricRule] = {
    "trunk_inclination_deg": VisualMetricRule((10.0, 25.0, 45.0)),
    "neck_flexion_deg": VisualMetricRule((10.0, 20.0, 35.0)),
    "left_upper_arm_elevation_deg": VisualMetricRule((20.0, 45.0, 90.0)),
    "right_upper_arm_elevation_deg": VisualMetricRule((20.0, 45.0, 90.0)),
    "left_elbow_flexion_deg": VisualMetricRule((30.0, 50.0, 75.0), center=90.0),
    "right_elbow_flexion_deg": VisualMetricRule((30.0, 50.0, 75.0), center=90.0),
    "left_forearm_inclination_deg": VisualMetricRule((20.0, 45.0, 75.0)),
    "right_forearm_inclination_deg": VisualMetricRule((20.0, 45.0, 75.0)),
    "left_wrist_flexion_deg": VisualMetricRule((10.0, 25.0, 45.0)),
    "right_wrist_flexion_deg": VisualMetricRule((10.0, 25.0, 45.0)),
}

BONE_METRICS: dict[str, str] = {
    "shoulders": "trunk_inclination_deg",
    "left_torso": "trunk_inclination_deg",
    "right_torso": "trunk_inclination_deg",
    "hips": "trunk_inclination_deg",
    "left_upper_arm": "left_upper_arm_elevation_deg",
    "right_upper_arm": "right_upper_arm_elevation_deg",
    "left_forearm": "left_forearm_inclination_deg",
    "right_forearm": "right_forearm_inclination_deg",
}

BONE_MAXIMUM_BODY_SCALE_RATIO: dict[str, float] = {
    "shoulders": 0.52,
    "hips": 0.44,
    "left_torso": 0.52,
    "right_torso": 0.52,
    "left_upper_arm": 0.44,
    "right_upper_arm": 0.44,
    "left_forearm": 0.44,
    "right_forearm": 0.44,
    "left_thigh": 0.58,
    "right_thigh": 0.58,
    "left_lower_leg": 0.58,
    "right_lower_leg": 0.58,
}


@dataclass(frozen=True)
class OverlayConfig:
    render_quality_threshold: float = 0.58
    metric_quality_threshold: float = 0.55
    fade_frames: int = 3
    maximum_expected_length_ratio: float = 1.80
    maximum_diagonal_ratio: float = 0.45
    draw_angles: bool = True
    draw_objects: bool = False
    debug: bool = False

    def validate(self) -> None:
        if not 0.0 <= self.render_quality_threshold <= 1.0:
            raise ValueError("render_quality_threshold must be in range 0..1")
        if not 0.0 <= self.metric_quality_threshold <= 1.0:
            raise ValueError("metric_quality_threshold must be in range 0..1")
        if not 0 <= self.fade_frames <= 8:
            raise ValueError("fade_frames must be in range 0..8")
        if self.maximum_expected_length_ratio <= 1.0:
            raise ValueError("maximum_expected_length_ratio must be greater than 1")
        if not 0.0 < self.maximum_diagonal_ratio < 1.0:
            raise ValueError("maximum_diagonal_ratio must be in range (0, 1)")


@dataclass(frozen=True)
class RenderedBone:
    name: str
    phase: BoneRenderPhase
    alpha: float
    first: tuple[float, float] | None
    second: tuple[float, float] | None
    confidence: float
    safety_rejected: bool
    severity: VisualSeverity


@dataclass(frozen=True)
class OverlayDiagnostics:
    rendered_bones: int
    hidden_bones: int
    safety_rejections: int
    maximum_rendered_length: float
    severities: dict[str, str]


@dataclass
class _BoneRenderMemory:
    phase: BoneRenderPhase = BoneRenderPhase.HIDDEN
    alpha: float = 0.0
    last_first: np.ndarray | None = None
    last_second: np.ndarray | None = None


class MetricColorHysteresis:
    def __init__(self, confirmation_frames: int = 2) -> None:
        if confirmation_frames < 1:
            raise ValueError("confirmation_frames must be positive")
        self.confirmation_frames = confirmation_frames
        self._current: dict[str, VisualSeverity] = {}
        self._pending: dict[str, tuple[VisualSeverity, int]] = {}

    def update(
        self,
        metric_name: str,
        value: float | None,
        valid: bool,
        quality: float,
        *,
        minimum_quality: float,
    ) -> VisualSeverity:
        candidate = classify_metric_severity(
            metric_name,
            value,
            valid,
            quality,
            minimum_quality=minimum_quality,
        )
        current = self._current.get(metric_name)
        if candidate in {VisualSeverity.UNKNOWN, VisualSeverity.TEMPORARY}:
            self._current[metric_name] = candidate
            self._pending.pop(metric_name, None)
            return candidate
        if current is None or current in {VisualSeverity.UNKNOWN, VisualSeverity.TEMPORARY}:
            self._current[metric_name] = candidate
            return candidate
        if current == candidate:
            self._pending.pop(metric_name, None)
            return current
        pending, count = self._pending.get(metric_name, (candidate, 0))
        count = count + 1 if pending == candidate else 1
        if count >= self.confirmation_frames:
            self._current[metric_name] = candidate
            self._pending.pop(metric_name, None)
            return candidate
        self._pending[metric_name] = (candidate, count)
        return current


class BoneRenderController:
    def __init__(self, config: OverlayConfig) -> None:
        config.validate()
        self.config = config
        self._bones = {name: _BoneRenderMemory() for name in BODY_BONES}

    def update(
        self,
        name: str,
        first: np.ndarray | None,
        second: np.ndarray | None,
        *,
        valid: bool,
        render_confidence: float,
        body_scale: float,
        expected_length: float | None,
        frame_width: int,
        frame_height: int,
        severity: VisualSeverity,
    ) -> RenderedBone:
        memory = self._bones.setdefault(name, _BoneRenderMemory())
        safe = safe_bone_segment(
            name,
            first,
            second,
            body_scale=body_scale,
            expected_length=expected_length,
            frame_width=frame_width,
            frame_height=frame_height,
            maximum_expected_ratio=self.config.maximum_expected_length_ratio,
            maximum_diagonal_ratio=self.config.maximum_diagonal_ratio,
        )
        accepted = valid and render_confidence >= self.config.render_quality_threshold and safe
        step = 1.0 / max(1, self.config.fade_frames)
        if accepted and first is not None and second is not None:
            memory.last_first = np.asarray(first, dtype=np.float32).copy()
            memory.last_second = np.asarray(second, dtype=np.float32).copy()
            if self.config.fade_frames == 0:
                memory.alpha = 1.0
                memory.phase = BoneRenderPhase.VISIBLE
            else:
                memory.alpha = min(1.0, memory.alpha + step)
                memory.phase = BoneRenderPhase.VISIBLE if memory.alpha >= 1.0 else BoneRenderPhase.FADING_IN
        elif memory.last_first is not None and memory.last_second is not None and memory.alpha > 0.0:
            memory.alpha = max(0.0, memory.alpha - step)
            memory.phase = BoneRenderPhase.FADING_OUT if memory.alpha > 0.0 else BoneRenderPhase.HIDDEN
        else:
            memory.alpha = 0.0
            memory.phase = BoneRenderPhase.HIDDEN
        return RenderedBone(
            name=name,
            phase=memory.phase,
            alpha=memory.alpha,
            first=_point(memory.last_first) if memory.alpha > 0.0 else None,
            second=_point(memory.last_second) if memory.alpha > 0.0 else None,
            confidence=float(np.clip(render_confidence, 0.0, 1.0)),
            safety_rejected=valid and not safe,
            severity=severity,
        )


def classify_metric_severity(
    metric_name: str,
    value: float | None,
    valid: bool,
    quality: float,
    *,
    minimum_quality: float = 0.55,
) -> VisualSeverity:
    if not valid or value is None or not math.isfinite(value) or quality < minimum_quality:
        return VisualSeverity.UNKNOWN
    rule = VISUAL_METRIC_RULES.get(metric_name)
    if rule is None:
        return VisualSeverity.UNKNOWN
    magnitude = rule.magnitude(value)
    if magnitude <= rule.boundaries[0]:
        return VisualSeverity.NEUTRAL
    if magnitude <= rule.boundaries[1]:
        return VisualSeverity.MILD
    if magnitude <= rule.boundaries[2]:
        return VisualSeverity.ELEVATED
    return VisualSeverity.STRONG


def safe_bone_segment(
    name: str,
    first: np.ndarray | None,
    second: np.ndarray | None,
    *,
    body_scale: float,
    expected_length: float | None,
    frame_width: int,
    frame_height: int,
    maximum_expected_ratio: float = 1.80,
    maximum_diagonal_ratio: float = 0.45,
) -> bool:
    if first is None or second is None:
        return False
    first_array = np.asarray(first, dtype=float).reshape(-1)
    second_array = np.asarray(second, dtype=float).reshape(-1)
    if first_array.size != 2 or second_array.size != 2 or not np.isfinite(first_array).all() or not np.isfinite(second_array).all():
        return False
    if not (_inside_frame(first_array, frame_width, frame_height) and _inside_frame(second_array, frame_width, frame_height)):
        return False
    length = float(np.linalg.norm(second_array - first_array))
    if not math.isfinite(length) or length <= 1e-6:
        return False
    limits = [math.hypot(frame_width, frame_height) * maximum_diagonal_ratio]
    body_ratio = BONE_MAXIMUM_BODY_SCALE_RATIO.get(name, 0.30 if "foot" in name or "toe" in name else 0.62)
    if body_scale > 0.0 and math.isfinite(body_scale):
        limits.append(body_scale * body_ratio)
    if expected_length is not None and expected_length > 0.0 and math.isfinite(expected_length):
        limits.append(expected_length * maximum_expected_ratio)
    return length <= min(limits)


def draw_pose_overlay_v4(
    image: np.ndarray,
    graph: PoseGraphFrame,
    metrics: Mapping[str, Mapping[str, object]],
    left_hand: HandGraphFrame,
    right_hand: HandGraphFrame,
    left_holding: HoldingFrameV2,
    right_holding: HoldingFrameV2,
    objects: list[TrackedObject],
    *,
    render_controller: BoneRenderController,
    color_hysteresis: MetricColorHysteresis,
    config: OverlayConfig,
    palette: OverlayPalette,
    bbox: np.ndarray | None = None,
) -> tuple[np.ndarray, OverlayDiagnostics]:
    output = image.copy()
    height, width = output.shape[:2]
    line_width = int(np.clip(round(height / 260.0), 2, 8))
    joint_radius = int(np.clip(round(height / 210.0), 2, 9))
    if config.debug and bbox is not None and np.asarray(bbox).size == 4 and np.isfinite(bbox).all():
        x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
        cv2.rectangle(output, (x1, y1), (x2, y2), palette.unknown, max(1, line_width // 2), cv2.LINE_AA)

    severities = _metric_severities(metrics, color_hysteresis, config.metric_quality_threshold)
    rendered: list[RenderedBone] = []
    for name, (first_index, second_index) in BODY_BONES.items():
        bone = graph.bones[name]
        first = graph.analysis_points[first_index] if graph.analysis_scores[first_index] > 0.0 else None
        second = graph.analysis_points[second_index] if graph.analysis_scores[second_index] > 0.0 else None
        metric_name = BONE_METRICS.get(name)
        severity = severities.get(metric_name, VisualSeverity.NEUTRAL) if metric_name else VisualSeverity.NEUTRAL
        if (
            graph.joints[first_index].source == MeasurementSource.INTERPOLATED
            or graph.joints[second_index].source == MeasurementSource.INTERPOLATED
        ):
            severity = VisualSeverity.TEMPORARY
        render_confidence = min(
            graph.joints[first_index].quality,
            graph.joints[second_index].quality,
            bone.quality,
        )
        expected_pixels = bone.reference_length * graph.body_scale if bone.reference_length is not None else None
        item = render_controller.update(
            name,
            first,
            second,
            valid=bone.valid,
            render_confidence=render_confidence,
            body_scale=graph.body_scale,
            expected_length=expected_pixels,
            frame_width=width,
            frame_height=height,
            severity=severity,
        )
        rendered.append(item)
        if item.first is not None and item.second is not None and item.alpha > 0.0:
            _draw_alpha_line(
                output,
                item.first,
                item.second,
                palette.severity(item.severity),
                line_width,
                item.alpha,
            )

    for index, joint in enumerate(graph.joints):
        if not joint.valid or joint.coordinates is None or joint.quality < config.render_quality_threshold:
            if config.debug and joint.predicted_position is not None:
                cv2.circle(output, _integer_point(joint.predicted_position), joint_radius, palette.debug_expected, 1, cv2.LINE_AA)
            continue
        color = palette.neutral
        limb = "left" if joint.name.startswith("left_") else "right" if joint.name.startswith("right_") else "center"
        halo = (190, 245, 255) if limb == "left" else (255, 220, 185) if limb == "right" else palette.text
        cv2.circle(output, _integer_point(joint.coordinates), joint_radius + 1, halo, 1, cv2.LINE_AA)
        cv2.circle(output, _integer_point(joint.coordinates), max(1, joint_radius - 1), color, -1, cv2.LINE_AA)

    _draw_hand(output, left_hand, severities.get("left_wrist_flexion_deg", VisualSeverity.UNKNOWN), palette, max(1, line_width - 1), joint_radius)
    _draw_hand(output, right_hand, severities.get("right_wrist_flexion_deg", VisualSeverity.UNKNOWN), palette, max(1, line_width - 1), joint_radius)

    if config.draw_objects or config.debug:
        for item in objects:
            x1, y1, x2, y2 = (int(round(value)) for value in item.bbox_xyxy)
            cv2.rectangle(output, (x1, y1), (x2, y2), palette.object, max(1, line_width // 2), cv2.LINE_AA)
            if config.debug:
                _draw_label(output, f"OBJ {item.track_id} {item.class_name or 'unknown'}", (x1, max(14, y1 - 5)), palette.object, palette)

    _draw_holding_marker(output, left_hand, left_holding, "HOLD L", palette)
    _draw_holding_marker(output, right_hand, right_holding, "HOLD R", palette)
    if left_holding.bimanual_candidate and right_holding.bimanual_candidate:
        centers = [value.palm.center for value in (left_hand, right_hand) if value.palm.center]
        if len(centers) == 2:
            center = tuple(np.mean(np.asarray(centers), axis=0))
            _draw_label(output, "BIMANUAL", _integer_point(center), palette.holding, palette)

    if config.draw_angles:
        _draw_angle_labels(output, graph, metrics, severities, palette, config.metric_quality_threshold)
    if config.debug:
        _draw_debug_status(output, graph, palette)

    lengths = [
        math.dist(item.first, item.second)
        for item in rendered
        if item.first is not None and item.second is not None and item.alpha > 0.0
    ]
    diagnostics = OverlayDiagnostics(
        rendered_bones=len(lengths),
        hidden_bones=sum(item.phase == BoneRenderPhase.HIDDEN for item in rendered),
        safety_rejections=sum(item.safety_rejected for item in rendered),
        maximum_rendered_length=max(lengths, default=0.0),
        severities={name: value.value for name, value in severities.items()},
    )
    return output, diagnostics


def _metric_severities(
    metrics: Mapping[str, Mapping[str, object]],
    hysteresis: MetricColorHysteresis,
    minimum_quality: float,
) -> dict[str, VisualSeverity]:
    output: dict[str, VisualSeverity] = {}
    for name in VISUAL_METRIC_RULES:
        metric = metrics.get(name, {})
        value = metric.get("value")
        quality = metric.get("quality")
        output[name] = hysteresis.update(
            name,
            float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
            metric.get("valid") is True,
            float(quality) if isinstance(quality, (int, float)) and not isinstance(quality, bool) else 0.0,
            minimum_quality=minimum_quality,
        )
    return output


def _draw_hand(
    image: np.ndarray,
    hand: HandGraphFrame,
    severity: VisualSeverity,
    palette: OverlayPalette,
    thickness: int,
    radius: int,
) -> None:
    if not hand.visible:
        return
    source = hand.source_frame
    color = palette.unknown if hand.quality < 0.55 else palette.severity(severity)
    for first, second in HAND_EDGES:
        if source.point_validity.size != 21 or not bool(source.point_validity[first]) or not bool(source.point_validity[second]):
            continue
        if not np.isfinite(source.points_px[[first, second]]).all():
            continue
        cv2.line(image, _integer_point(source.points_px[first]), _integer_point(source.points_px[second]), color, thickness, cv2.LINE_AA)
    for index, point in enumerate(source.points_px):
        if source.point_validity.size == 21 and bool(source.point_validity[index]) and np.isfinite(point).all():
            cv2.circle(image, _integer_point(point), max(1, radius - 1), color, -1, cv2.LINE_AA)


def _draw_holding_marker(
    image: np.ndarray,
    hand: HandGraphFrame,
    holding: HoldingFrameV2,
    text: str,
    palette: OverlayPalette,
) -> None:
    if holding.state not in {HoldingStateV2.LIKELY_HOLDING, HoldingStateV2.LIKELY_HOLDING_UNKNOWN_OBJECT} or hand.palm.center is None:
        return
    center = np.asarray(hand.palm.center, dtype=float) + np.asarray((14.0, -18.0))
    _draw_label(image, text, _integer_point(center), palette.holding, palette)


def _draw_angle_labels(
    image: np.ndarray,
    graph: PoseGraphFrame,
    metrics: Mapping[str, Mapping[str, object]],
    severities: dict[str, VisualSeverity],
    palette: OverlayPalette,
    minimum_quality: float,
) -> None:
    anchors: dict[str, tuple[float, float] | None] = {
        "trunk_inclination_deg": graph.anchors.torso_center,
        "neck_flexion_deg": graph.anchors.shoulder_center,
        "left_upper_arm_elevation_deg": graph.joints[5].coordinates,
        "right_upper_arm_elevation_deg": graph.joints[6].coordinates,
        "left_elbow_flexion_deg": graph.joints[7].coordinates,
        "right_elbow_flexion_deg": graph.joints[8].coordinates,
        "left_wrist_flexion_deg": graph.joints[9].coordinates,
        "right_wrist_flexion_deg": graph.joints[10].coordinates,
    }
    occupied: list[np.ndarray] = []
    for index, (name, anchor) in enumerate(anchors.items()):
        metric = metrics.get(name, {})
        value, quality = metric.get("value"), metric.get("quality")
        if anchor is None or metric.get("valid") is not True or not isinstance(value, (int, float)) or isinstance(value, bool) or not isinstance(quality, (int, float)) or quality < minimum_quality:
            continue
        base = np.asarray(anchor, dtype=float) + np.asarray((12.0, -10.0 if index % 2 == 0 else 18.0))
        for existing in occupied:
            if np.linalg.norm(base - existing) < 34.0:
                base[1] += 22.0
        base[0] = np.clip(base[0], 8.0, image.shape[1] - 52.0)
        base[1] = np.clip(base[1], 16.0, image.shape[0] - 8.0)
        occupied.append(base.copy())
        _draw_label(image, f"{float(value):.0f}°", _integer_point(base), palette.severity(severities.get(name, VisualSeverity.UNKNOWN)), palette)


def _draw_debug_status(image: np.ndarray, graph: PoseGraphFrame, palette: OverlayPalette) -> None:
    lines = [f"BODY {graph.tracking_state} Q={graph.quality:.2f} COVER={graph.body_coverage_ratio:.2f}"]
    lines.extend(f"{name.upper()} {limb.state.value} Q={limb.quality:.2f}" for name, limb in graph.limbs.items())
    y = 22
    for line in lines:
        _draw_label(image, line, (12, y), palette.text, palette)
        y += 18


def _draw_alpha_line(
    image: np.ndarray,
    first: tuple[float, float],
    second: tuple[float, float],
    color: tuple[int, int, int],
    thickness: int,
    alpha: float,
) -> None:
    layer = image.copy()
    cv2.line(layer, _integer_point(first), _integer_point(second), color, thickness, cv2.LINE_AA)
    cv2.addWeighted(layer, float(np.clip(alpha, 0.0, 1.0)), image, 1.0 - float(np.clip(alpha, 0.0, 1.0)), 0.0, dst=image)


def _draw_label(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
    palette: OverlayPalette,
) -> None:
    font_scale = float(np.clip(image.shape[0] / 900.0, 0.38, 0.72))
    thickness = int(np.clip(round(image.shape[0] / 720.0), 1, 2))
    cv2.putText(image, text, (origin[0] + 1, origin[1] + 1), cv2.FONT_HERSHEY_SIMPLEX, font_scale, palette.shadow, thickness + 2, cv2.LINE_AA)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)


def _inside_frame(point: np.ndarray, width: int, height: int) -> bool:
    return 0.0 <= point[0] < width and 0.0 <= point[1] < height


def _point(value: np.ndarray | None) -> tuple[float, float] | None:
    if value is None or value.size != 2 or not np.isfinite(value).all():
        return None
    return float(value[0]), float(value[1])


def _integer_point(value: np.ndarray | tuple[float, float]) -> tuple[int, int]:
    array = np.asarray(value, dtype=float)
    return int(round(float(array[0]))), int(round(float(array[1])))
