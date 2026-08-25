"""Safe, quality-aware and temporally stable overlay for Pose V4."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Protocol, Sequence

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

from .overlay_layout import LabelLayout, LabelRequest, place_overlay_labels


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
    render_sources: dict[str, int] = field(default_factory=dict)
    overlay_label_overlap_count: int = 0
    overlay_label_readability_score: float = 1.0
    overlay_main_metric_visibility_ratio: float = 1.0
    label_count: int = 0


class BoneRenderOverride(Protocol):
    """Narrow bridge used by the V6 renderer without coupling V4 to V6."""

    first: tuple[float, float] | None
    second: tuple[float, float] | None
    alpha: float
    confidence: float
    safety_rejected: bool
    source: object


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
    render_bone_overrides: Mapping[str, BoneRenderOverride] | None = None,
    render_joint_points: np.ndarray | None = None,
    render_joint_scores: np.ndarray | None = None,
    render_joint_sources: Sequence[str] | None = None,
    left_hand_offset: tuple[float, float] | None = None,
    right_hand_offset: tuple[float, float] | None = None,
    left_grip_state: str | None = None,
    right_grip_state: str | None = None,
) -> tuple[np.ndarray, OverlayDiagnostics]:
    output = image.copy()
    height, width = output.shape[:2]
    line_width, joint_radius = overlay_dimensions(height)
    if config.debug and bbox is not None and np.asarray(bbox).size == 4 and np.isfinite(bbox).all():
        x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
        cv2.rectangle(output, (x1, y1), (x2, y2), palette.unknown, max(1, line_width // 2), cv2.LINE_AA)

    severities = _metric_severities(metrics, color_hysteresis, config.metric_quality_threshold)
    rendered: list[RenderedBone] = []
    source_counts: dict[str, int] = {}
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
        override = render_bone_overrides.get(name) if render_bone_overrides is not None else None
        if override is not None:
            source_name = getattr(override.source, "value", str(override.source))
            source_counts[source_name] = source_counts.get(source_name, 0) + 1
            item = RenderedBone(
                name=name,
                phase=BoneRenderPhase.VISIBLE if override.first is not None and override.second is not None and override.alpha > 0.0 else BoneRenderPhase.HIDDEN,
                alpha=override.alpha,
                first=override.first,
                second=override.second,
                confidence=override.confidence,
                safety_rejected=override.safety_rejected,
                severity=VisualSeverity.TEMPORARY if source_name not in {"MEASURED", "REFINED_MEASUREMENT"} else severity,
            )
        else:
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
        override_point = (
            render_joint_points[index]
            if render_joint_points is not None and index < len(render_joint_points)
            else None
        )
        override_quality = (
            float(render_joint_scores[index])
            if render_joint_scores is not None and index < len(render_joint_scores)
            else 0.0
        )
        using_joint_override = bool(
            override_point is not None
            and override_quality > 0.0
            and np.isfinite(override_point).all()
        )
        coordinates = (
            tuple(float(value) for value in override_point)
            if using_joint_override
            else joint.coordinates
        )
        render_quality = override_quality if using_joint_override else joint.quality
        if coordinates is None or render_quality < min(config.render_quality_threshold, 0.35):
            if config.debug and joint.predicted_position is not None:
                cv2.circle(output, _integer_point(joint.predicted_position), joint_radius, palette.debug_expected, 1, cv2.LINE_AA)
            continue
        color = palette.neutral
        limb = "left" if joint.name.startswith("left_") else "right" if joint.name.startswith("right_") else "center"
        halo = (190, 245, 255) if limb == "left" else (255, 220, 185) if limb == "right" else palette.text
        if render_joint_sources is not None and index < len(render_joint_sources) and render_joint_sources[index] not in {"MEASURED", "REFINED_MEASUREMENT"}:
            color = palette.temporary
        cv2.circle(output, _integer_point(coordinates), joint_radius + 1, halo, 1, cv2.LINE_AA)
        cv2.circle(output, _integer_point(coordinates), max(1, joint_radius - 1), color, -1, cv2.LINE_AA)

    _draw_hand(output, left_hand, severities.get("left_wrist_flexion_deg", VisualSeverity.UNKNOWN), palette, max(1, line_width - 1), joint_radius, offset=left_hand_offset)
    _draw_hand(output, right_hand, severities.get("right_wrist_flexion_deg", VisualSeverity.UNKNOWN), palette, max(1, line_width - 1), joint_radius, offset=right_hand_offset)

    if config.draw_objects or config.debug:
        for item in objects:
            x1, y1, x2, y2 = (int(round(value)) for value in item.bbox_xyxy)
            cv2.rectangle(output, (x1, y1), (x2, y2), palette.object, max(1, line_width // 2), cv2.LINE_AA)
            if config.debug:
                _draw_label(output, f"OBJ {item.track_id} {item.class_name or 'unknown'}", (x1, max(14, y1 - 5)), palette.object, palette)

    _draw_holding_marker(output, left_hand, left_holding, "HOLD L", palette)
    _draw_holding_marker(output, right_hand, right_holding, "HOLD R", palette)
    _draw_grip_state(output, left_hand, left_grip_state, "L", palette, offset=left_hand_offset)
    _draw_grip_state(output, right_hand, right_grip_state, "P", palette, offset=right_hand_offset)
    if left_holding.bimanual_candidate and right_holding.bimanual_candidate:
        centers = [value.palm.center for value in (left_hand, right_hand) if value.palm.center]
        if len(centers) == 2:
            center = tuple(np.mean(np.asarray(centers), axis=0))
            _draw_label(output, "BIMANUAL", _integer_point(center), palette.holding, palette)

    label_layout = None
    if config.draw_angles:
        label_layout = _draw_angle_labels(
            output,
            graph,
            metrics,
            severities,
            palette,
            config.metric_quality_threshold,
            render_joint_points=render_joint_points,
            render_joint_scores=render_joint_scores,
        )
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
        render_sources=source_counts,
        overlay_label_overlap_count=label_layout.overlap_count if label_layout else 0,
        overlay_label_readability_score=label_layout.readability_score if label_layout else 1.0,
        overlay_main_metric_visibility_ratio=label_layout.visibility_ratio if label_layout else 1.0,
        label_count=len(label_layout.labels) if label_layout else 0,
    )
    return output, diagnostics


def overlay_dimensions(frame_height: int) -> tuple[int, int]:
    """Return premium standard-mode bone width and joint radius."""

    if frame_height <= 0:
        raise ValueError("frame_height must be positive")
    return (
        int(np.clip(round(frame_height / 190.0), 3, 10)),
        int(np.clip(round(frame_height / 170.0), 3, 11)),
    )


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
    *,
    offset: tuple[float, float] | None = None,
) -> None:
    if not hand.visible:
        return
    source = hand.source_frame
    translation = np.asarray(offset if offset is not None else (0.0, 0.0), dtype=float)
    color = palette.unknown if hand.quality < 0.55 else palette.severity(severity)
    for first, second in HAND_EDGES:
        if source.point_validity.size != 21 or not bool(source.point_validity[first]) or not bool(source.point_validity[second]):
            continue
        if not np.isfinite(source.points_px[[first, second]]).all():
            continue
        cv2.line(image, _integer_point(source.points_px[first] + translation), _integer_point(source.points_px[second] + translation), color, thickness, cv2.LINE_AA)
    for index, point in enumerate(source.points_px):
        if source.point_validity.size == 21 and bool(source.point_validity[index]) and np.isfinite(point).all():
            cv2.circle(image, _integer_point(point + translation), max(1, radius - 1), color, -1, cv2.LINE_AA)


def _draw_grip_state(
    image: np.ndarray,
    hand: HandGraphFrame,
    state: str | None,
    side: str,
    palette: OverlayPalette,
    *,
    offset: tuple[float, float] | None,
) -> None:
    if not hand.visible or state not in {"POWER_GRIP", "PRECISION_PINCH", "CLOSED"} or hand.palm.center is None:
        return
    center = np.asarray(hand.palm.center, dtype=float)
    center += np.asarray(offset if offset is not None else (0.0, 0.0), dtype=float)
    center += np.asarray((12.0, 24.0))
    labels = {"POWER_GRIP": "chwyt", "PRECISION_PINCH": "szczypcowy", "CLOSED": "zamknięta"}
    _draw_label(image, f"{side}: {labels[state]}", _integer_point(center), palette.holding, palette)


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
    *,
    render_joint_points: np.ndarray | None = None,
    render_joint_scores: np.ndarray | None = None,
) -> LabelLayout:
    anchors: dict[str, tuple[float, float] | None] = {
        "trunk_inclination_deg": graph.anchors.torso_center,
        "neck_flexion_deg": graph.anchors.shoulder_center,
        "left_upper_arm_elevation_deg": _overlay_joint(graph, 5, render_joint_points, render_joint_scores),
        "right_upper_arm_elevation_deg": _overlay_joint(graph, 6, render_joint_points, render_joint_scores),
        "left_elbow_flexion_deg": _overlay_joint(graph, 7, render_joint_points, render_joint_scores),
        "right_elbow_flexion_deg": _overlay_joint(graph, 8, render_joint_points, render_joint_scores),
        "left_wrist_flexion_deg": _overlay_joint(graph, 9, render_joint_points, render_joint_scores),
        "right_wrist_flexion_deg": _overlay_joint(graph, 10, render_joint_points, render_joint_scores),
    }
    labels = {
        "trunk_inclination_deg": "Tułów",
        "neck_flexion_deg": "Szyja",
        "left_upper_arm_elevation_deg": "L ramię",
        "right_upper_arm_elevation_deg": "P ramię",
        "left_elbow_flexion_deg": "L łokieć",
        "right_elbow_flexion_deg": "P łokieć",
        "left_wrist_flexion_deg": "L nadgarstek",
        "right_wrist_flexion_deg": "P nadgarstek",
    }
    prepared: list[tuple[str, str, tuple[float, float], tuple[int, int], int]] = []
    font_scale = float(np.clip(image.shape[0] / 820.0, 0.48, 0.82))
    thickness = int(np.clip(round(image.shape[0] / 620.0), 1, 3))
    for name, anchor in anchors.items():
        metric = metrics.get(name, {})
        value, quality = metric.get("value"), metric.get("quality")
        if anchor is None or metric.get("valid") is not True or not isinstance(value, (int, float)) or isinstance(value, bool) or not isinstance(quality, (int, float)) or quality < minimum_quality:
            continue
        text = f"{labels[name]} {float(value):.0f}°"
        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        priority = 3 if name in {"trunk_inclination_deg", "neck_flexion_deg"} else 2 if "elbow" in name else 1
        prepared.append((name, text, anchor, (text_width + 14, text_height + baseline + 12), priority))
    layout = place_overlay_labels(
        [LabelRequest(name, anchor, size, priority) for name, _text, anchor, size, priority in prepared],
        image.shape[1],
        image.shape[0],
    )
    for placed, (name, text, _anchor, _size, _priority) in zip(layout.labels, prepared):
        if not placed.visible:
            continue
        left, top, right, bottom = placed.bounds
        layer = image.copy()
        cv2.rectangle(layer, (left, top), (right, bottom), palette.shadow, -1, cv2.LINE_AA)
        cv2.addWeighted(layer, 0.78, image, 0.22, 0.0, dst=image)
        color = palette.severity(severities.get(name, VisualSeverity.UNKNOWN))
        cv2.rectangle(image, (left, top), (right, bottom), color, 1, cv2.LINE_AA)
        cv2.putText(image, text, placed.origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, palette.shadow, thickness + 3, cv2.LINE_AA)
        cv2.putText(image, text, placed.origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
    return layout


def _overlay_joint(
    graph: PoseGraphFrame,
    index: int,
    render_points: np.ndarray | None,
    render_scores: np.ndarray | None,
) -> tuple[float, float] | None:
    if (
        render_points is not None
        and render_scores is not None
        and index < len(render_points)
        and index < len(render_scores)
        and float(render_scores[index]) > 0.0
        and np.isfinite(render_points[index]).all()
    ):
        return tuple(float(value) for value in render_points[index])
    return graph.joints[index].coordinates


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
    cv2.line(layer, _integer_point(first), _integer_point(second), (10, 18, 24), thickness + 4, cv2.LINE_AA)
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
