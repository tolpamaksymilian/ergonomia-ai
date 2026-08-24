"""Pose V6.2 anatomical projection and skeleton-geometry diagnostics.

The pass is intentionally model-agnostic.  It consumes the V6 analysis/render
split, learns person-specific *normalized* proportions from strong samples and
applies the smallest correction that satisfies a two-bone limb chain.  Every
synthetic analytical point remains explicitly reconstructed in provenance.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import numpy as np

from .temporal_reconstruction import PointSource, TemporalFrame


CANONICAL_BONES: dict[str, tuple[int, int]] = {
    "shoulder_width": (5, 6),
    "hip_width": (11, 12),
    "left_upper_arm": (5, 7),
    "left_forearm": (7, 9),
    "right_upper_arm": (6, 8),
    "right_forearm": (8, 10),
    "left_thigh": (11, 13),
    "left_shin": (13, 15),
    "right_thigh": (12, 14),
    "right_shin": (14, 16),
}
LIMB_CHAINS: dict[str, tuple[int, int, int, str, str]] = {
    "left_arm": (5, 7, 9, "left_upper_arm", "left_forearm"),
    "right_arm": (6, 8, 10, "right_upper_arm", "right_forearm"),
    "left_leg": (11, 13, 15, "left_thigh", "left_shin"),
    "right_leg": (12, 14, 16, "right_thigh", "right_shin"),
}
SIDE_PAIRS: tuple[tuple[int, int], ...] = ((7, 8), (9, 10), (13, 14), (15, 16))
MAIN_BONE_NAMES = (
    "shoulders", "left_upper_arm", "left_forearm", "right_upper_arm",
    "right_forearm", "hips", "left_thigh", "left_lower_leg",
    "right_thigh", "right_lower_leg",
)
_STRONG_SOURCES = {PointSource.MEASURED, PointSource.REFINED_MEASUREMENT}


@dataclass(frozen=True)
class CanonicalBone:
    normalized_length: float
    mad: float
    sample_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "normalized_length": round(self.normalized_length, 6),
            "mad": round(self.mad, 6),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class CanonicalBodyProfile:
    bones: Mapping[str, CanonicalBone]
    minimum_quality: float = 0.72

    def expected_pixels(self, name: str, body_scale: float) -> float | None:
        value = self.bones.get(name)
        if value is None or not math.isfinite(body_scale) or body_scale <= 0.0:
            return None
        return value.normalized_length * body_scale

    def to_dict(self) -> dict[str, object]:
        return {
            "normalization": "bone_length_divided_by_current_body_scale",
            "estimator": "median_and_mad_high_quality_only",
            "minimum_quality": self.minimum_quality,
            "bones": {name: value.to_dict() for name, value in self.bones.items()},
        }


@dataclass(frozen=True)
class BodyReferenceFrame:
    shoulder_midpoint: tuple[float, float] | None
    hip_midpoint: tuple[float, float] | None
    torso_axis: tuple[float, float] | None
    shoulder_axis: tuple[float, float] | None
    body_scale: float
    global_motion: tuple[float, float]
    quality: float

    def to_dict(self) -> dict[str, object]:
        return {
            "shoulder_midpoint": _rounded_point(self.shoulder_midpoint),
            "hip_midpoint": _rounded_point(self.hip_midpoint),
            "torso_axis": _rounded_point(self.torso_axis),
            "shoulder_axis": _rounded_point(self.shoulder_axis),
            "body_scale": round(self.body_scale, 6),
            "global_motion": _rounded_point(self.global_motion),
            "quality": round(self.quality, 6),
        }


@dataclass(frozen=True)
class JointEstimate:
    position: tuple[float, float] | None
    velocity: tuple[float, float]
    acceleration: tuple[float, float]
    uncertainty: float
    confidence: float
    source: str
    age_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "position": _rounded_point(self.position),
            "velocity": _rounded_point(self.velocity),
            "acceleration": _rounded_point(self.acceleration),
            "uncertainty": round(self.uncertainty, 6),
            "confidence": round(self.confidence, 6),
            "source": self.source,
            "age_seconds": round(self.age_seconds, 6),
        }


@dataclass(frozen=True)
class AnatomicalProjectionResult:
    frames: list[TemporalFrame]
    frame_diagnostics: list[dict[str, object]]
    profile: CanonicalBodyProfile
    summary: dict[str, object]


class SkeletonGeometryValidator:
    """Detect implausible geometry without assuming screen-left means body-left."""

    def validate(
        self,
        frame: TemporalFrame,
        profile: CanonicalBodyProfile,
        body_scale: float,
        *,
        previous: TemporalFrame | None,
        previous_scale: float | None,
        side_swap_corrected: bool,
    ) -> dict[str, object]:
        scale = max(float(body_scale), 1.0)
        errors = _bone_errors(frame, profile, scale)
        abnormal = [name for name, value in errors.items() if value > 0.18]
        jumps: list[int] = []
        if previous is not None:
            for index in range(min(17, frame.analysis_scores.size)):
                if _analysis_valid(frame, index) and _analysis_valid(previous, index):
                    if float(np.linalg.norm(frame.analysis_points[index] - previous.analysis_points[index]) / scale) > 0.35:
                        jumps.append(index)
        center = _midpoint(frame, 11, 12)
        outside = []
        if center is not None:
            outside = [
                index for index in (7, 8, 9, 10, 13, 14, 15, 16)
                if _analysis_valid(frame, index)
                and float(np.linalg.norm(frame.analysis_points[index] - center) / scale) > 1.65
            ]
        torso_scale_anomaly = bool(
            previous_scale is not None
            and previous_scale > 1e-6
            and abs(scale / previous_scale - 1.0) > 0.32
        )
        crossing = _segments_cross(frame, (5, 7), (6, 8)) and _segments_cross(frame, (7, 9), (8, 10))
        reasons = []
        if abnormal: reasons.append("ABNORMAL_BONE_LENGTH")
        if jumps: reasons.append("IMPOSSIBLE_JOINT_JUMP")
        if side_swap_corrected: reasons.append("LEFT_RIGHT_SWAP_CORRECTED")
        if crossing: reasons.append("LIMB_CROSSING_ANOMALY")
        if outside: reasons.append("JOINT_OUTSIDE_BODY_REGION")
        if torso_scale_anomaly: reasons.append("TORSO_SCALE_ANOMALY")
        return {
            "valid": not bool(abnormal or jumps or outside or torso_scale_anomaly),
            "reasons": reasons,
            "abnormal_bones": abnormal,
            "jump_joints": jumps,
            "outside_body_region_joints": outside,
            "left_right_swap_corrected": side_swap_corrected,
            "limb_crossing_anomaly": crossing,
            "torso_scale_anomaly": torso_scale_anomaly,
        }


@dataclass
class _State:
    position: np.ndarray | None = None
    velocity: np.ndarray | None = None
    acceleration: np.ndarray | None = None
    timestamp: float | None = None
    uncertainty: float = 1.0
    age_seconds: float = 0.0


def build_canonical_body_profile(
    frames: Sequence[TemporalFrame],
    body_scales: Sequence[float],
    *,
    minimum_quality: float = 0.72,
    minimum_samples: int = 3,
    maximum_samples: int = 120,
) -> CanonicalBodyProfile:
    """Learn robust normalized lengths without admitting weak/reconstructed data."""

    if len(frames) != len(body_scales):
        raise ValueError("frames and body_scales must have equal lengths")
    samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=maximum_samples))
    for frame, scale in zip(frames, body_scales):
        if not math.isfinite(scale) or scale <= 1e-6:
            continue
        for name, (first, second) in CANONICAL_BONES.items():
            if not _strong_joint(frame, first, minimum_quality) or not _strong_joint(frame, second, minimum_quality):
                continue
            normalized = float(np.linalg.norm(frame.analysis_points[second] - frame.analysis_points[first]) / scale)
            if math.isfinite(normalized) and 0.01 <= normalized <= 0.9:
                samples[name].append(normalized)
        if all(_strong_joint(frame, index, minimum_quality) for index in (5, 6, 11, 12)):
            shoulder_midpoint = (frame.analysis_points[5] + frame.analysis_points[6]) * 0.5
            hip_midpoint = (frame.analysis_points[11] + frame.analysis_points[12]) * 0.5
            normalized_torso = float(np.linalg.norm(shoulder_midpoint - hip_midpoint) / scale)
            if math.isfinite(normalized_torso) and 0.01 <= normalized_torso <= 0.9:
                samples["torso_length"].append(normalized_torso)
    bones: dict[str, CanonicalBone] = {}
    for name, values in samples.items():
        if len(values) < minimum_samples:
            continue
        array = np.asarray(values, dtype=np.float64)
        median = float(np.median(array))
        mad = float(np.median(np.abs(array - median)))
        bones[name] = CanonicalBone(median, mad, len(values))
    # A stable side can seed its counterpart, but provenance remains a profile
    # prior rather than a fabricated frame measurement.
    for left, right in (
        ("left_upper_arm", "right_upper_arm"), ("left_forearm", "right_forearm"),
        ("left_thigh", "right_thigh"), ("left_shin", "right_shin"),
    ):
        if left in bones and right not in bones:
            bones[right] = bones[left]
        elif right in bones and left not in bones:
            bones[left] = bones[right]
    return CanonicalBodyProfile(bones=bones, minimum_quality=minimum_quality)


def build_body_reference_frames(
    frames: Sequence[TemporalFrame], body_scales: Sequence[float]
) -> list[BodyReferenceFrame]:
    output: list[BodyReferenceFrame] = []
    previous_center: np.ndarray | None = None
    for frame, scale in zip(frames, body_scales):
        shoulder = _midpoint(frame, 5, 6)
        hip = _midpoint(frame, 11, 12)
        center = (shoulder + hip) * 0.5 if shoulder is not None and hip is not None else shoulder if shoulder is not None else hip
        motion = center - previous_center if center is not None and previous_center is not None else np.zeros(2, dtype=np.float32)
        if center is not None:
            previous_center = center
        torso = shoulder - hip if shoulder is not None and hip is not None else None
        shoulder_axis = frame.render_points[6] - frame.render_points[5] if _render_valid(frame, 5) and _render_valid(frame, 6) else None
        quality_indices = [index for index in (5, 6, 11, 12) if _analysis_valid(frame, index)]
        quality = min((float(frame.analysis_scores[index]) for index in quality_indices), default=0.0)
        output.append(BodyReferenceFrame(
            _tuple(shoulder), _tuple(hip), _tuple(torso), _tuple(shoulder_axis),
            float(scale) if math.isfinite(scale) and scale > 0.0 else 1.0,
            _tuple(motion) or (0.0, 0.0), quality,
        ))
    return output


def project_anatomical_sequence(
    frames: Sequence[TemporalFrame],
    body_scales: Sequence[float],
    timestamps: Sequence[float],
    tracking_states: Sequence[str],
    scene_cuts: Sequence[bool],
    *,
    maximum_prediction_seconds: float = 0.55,
) -> AnatomicalProjectionResult:
    """Run root-first state estimation, side hysteresis and limb-chain projection."""

    count = len(frames)
    if not (count == len(body_scales) == len(timestamps) == len(tracking_states) == len(scene_cuts)):
        raise ValueError("anatomical projection inputs must have equal lengths")
    if not frames:
        profile = CanonicalBodyProfile({})
        return AnatomicalProjectionResult([], [], profile, _empty_summary())
    profile = build_canonical_body_profile(frames, body_scales)
    input_errors = [
        value
        for frame, scale in zip(frames, body_scales)
        for value in _bone_errors(frame, profile, scale).values()
    ]
    working = [_copy_frame(frame) for frame in frames]
    swap_flags = detect_and_correct_side_swaps(working, body_scales)
    references = build_body_reference_frames(working, body_scales)
    states = [_State() for _ in range(min(23, working[0].analysis_scores.size))]
    diagnostics: list[dict[str, object]] = []
    detected_jump_events = residual_jump_events = correction_count = ik_count = 0
    previous_timestamp: float | None = None
    geometry_validator = SkeletonGeometryValidator()
    previous_projected: TemporalFrame | None = None
    previous_scale: float | None = None

    for frame_index, frame in enumerate(working):
        timestamp = float(timestamps[frame_index])
        dt = max(1e-3, timestamp - previous_timestamp) if previous_timestamp is not None and timestamp > previous_timestamp else 1.0 / 30.0
        previous_timestamp = timestamp
        if scene_cuts[frame_index] or str(tracking_states[frame_index]).upper() == "LOST":
            states = [_State() for _ in states]
        points = frame.analysis_points.copy(); scores = frame.analysis_scores.copy()
        render_points = frame.render_points.copy(); render_scores = frame.render_scores.copy()
        usable = frame.analysis_usable.copy(); sources = list(frame.sources)
        ages = frame.prediction_age_seconds.copy()
        joint_estimates: dict[str, object] = {}
        frame_jumps = 0

        # Root-first ordering prevents distal noise from moving the torso.
        order = (5, 6, 11, 12, 7, 8, 13, 14, 9, 10, 15, 16)
        root_motion = np.asarray(references[frame_index].global_motion, dtype=np.float32)
        for joint in order:
            if joint >= len(states):
                continue
            measurement = points[joint] if _analysis_valid_arrays(points, scores, usable, joint) else None
            quality = float(scores[joint]) if measurement is not None else 0.0
            estimate, was_jump = _update_state(
                states[joint], measurement, quality, timestamp, dt,
                max(float(body_scales[frame_index]), 1.0), root_motion,
                maximum_prediction_seconds,
            )
            frame_jumps += int(was_jump)
            if estimate is not None and measurement is not None:
                displacement = float(np.linalg.norm(estimate - measurement))
                if was_jump:
                    points[joint] = estimate; render_points[joint] = estimate
                    scores[joint] = max(0.35, quality * 0.62); render_scores[joint] = scores[joint]
                    sources[joint] = PointSource.KINEMATIC_RECONSTRUCTED; usable[joint] = True
                    ages[joint] = dt
                    correction_count += 1
                elif displacement > max(0.75, body_scales[frame_index] * 0.006):
                    points[joint] = estimate; render_points[joint] = estimate
            elif estimate is not None and states[joint].age_seconds <= maximum_prediction_seconds:
                render_points[joint] = estimate; render_scores[joint] = max(0.12, (1.0 - states[joint].uncertainty) * 0.45)
                sources[joint] = PointSource.KINEMATIC_PREDICTED; ages[joint] = states[joint].age_seconds
            joint_estimates[str(joint)] = _serialize_state(states[joint], sources[joint])

        # Solve each proximal/middle/distal chain as one constrained geometry.
        for chain_name, (root, middle, end, first_name, second_name) in LIMB_CHAINS.items():
            length_a = profile.expected_pixels(first_name, body_scales[frame_index])
            length_b = profile.expected_pixels(second_name, body_scales[frame_index])
            if length_a is None or length_b is None:
                continue
            root_point = points[root] if _analysis_valid_arrays(points, scores, usable, root) else None
            end_point = points[end] if _analysis_valid_arrays(points, scores, usable, end) else None
            measured_middle = points[middle] if _analysis_valid_arrays(points, scores, usable, middle) else None
            if root_point is None or end_point is None:
                continue
            preferred = _preferred_middle(working, frame_index, middle, measured_middle)
            solved = solve_two_bone_chain(root_point, end_point, length_a, length_b, preferred)
            if solved is None:
                continue
            correction = float(np.linalg.norm(solved - measured_middle)) if measured_middle is not None else math.inf
            tolerance = max(1.5, body_scales[frame_index] * 0.018)
            if measured_middle is None or correction > tolerance:
                quality = min(float(scores[root]), float(scores[end])) * (0.62 if measured_middle is None else 0.72)
                points[middle] = solved; render_points[middle] = solved
                scores[middle] = max(0.35, min(0.78, quality)); render_scores[middle] = scores[middle]
                usable[middle] = True; sources[middle] = PointSource.KINEMATIC_RECONSTRUCTED
                ages[middle] = 0.0 if measured_middle is not None else dt
                correction_count += 1; ik_count += int(measured_middle is None)

        projected = replace(
            frame,
            analysis_points=points, analysis_scores=scores,
            render_points=render_points, render_scores=render_scores,
            sources=tuple(sources), analysis_usable=usable,
            prediction_age_seconds=ages,
        )
        working[frame_index] = projected
        errors = _bone_errors(projected, profile, body_scales[frame_index])
        geometry = geometry_validator.validate(
            projected,
            profile,
            body_scales[frame_index],
            previous=previous_projected,
            previous_scale=previous_scale,
            side_swap_corrected=swap_flags[frame_index],
        )
        previous_projected = projected
        previous_scale = float(body_scales[frame_index])
        detected_jump_events += frame_jumps
        residual_jump_events += len(geometry["jump_joints"])
        diagnostics.append({
            "body_reference_frame": references[frame_index].to_dict(),
            "joint_states": joint_estimates,
            "side_swap_corrected": swap_flags[frame_index],
            "joint_jump_events": frame_jumps,
            "bone_length_errors": errors,
            "geometry_validation": geometry,
            "kinematic_reconstruction_count": sum(source == PointSource.KINEMATIC_RECONSTRUCTED for source in sources),
        })

    all_errors = [value for item in diagnostics for value in item["bone_length_errors"].values() if isinstance(value, float)]
    summary = {
        "canonical_body_profile": profile.to_dict(),
        "anatomical_projection_correction_count": correction_count,
        "kinematic_reconstruction_count": ik_count,
        "side_swap_correction_count": sum(swap_flags),
        "detected_joint_jump_count": detected_jump_events,
        "joint_jump_event_count": residual_jump_events,
        "input_bone_length_stability_error": round(float(np.mean(input_errors)), 6) if input_errors else 0.0,
        "bone_length_stability_error": round(float(np.mean(all_errors)), 6) if all_errors else 0.0,
        "maximum_bone_length_error": round(max(all_errors), 6) if all_errors else 0.0,
        "state_estimator": "dt-aware-alpha-beta-gamma-velocity-adaptive",
        "projection": "root-first-constrained-two-bone-chain",
    }
    return AnatomicalProjectionResult(working, diagnostics, profile, summary)


def solve_two_bone_chain(
    root: np.ndarray, end: np.ndarray, length_a: float, length_b: float,
    preferred_middle: np.ndarray | None,
) -> np.ndarray | None:
    """Return the preferred intersection of two circles, or a safe collinear limit."""

    first = np.asarray(root, dtype=np.float64).reshape(-1); second = np.asarray(end, dtype=np.float64).reshape(-1)
    if first.size != 2 or second.size != 2 or not np.isfinite(first).all() or not np.isfinite(second).all():
        return None
    if not all(math.isfinite(value) and value > 1e-6 for value in (length_a, length_b)):
        return None
    delta = second - first; distance = float(np.linalg.norm(delta))
    if distance <= 1e-8:
        return None
    direction = delta / distance
    feasible_distance = float(np.clip(distance, abs(length_a - length_b) + 1e-6, length_a + length_b - 1e-6))
    x = (length_a * length_a - length_b * length_b + feasible_distance * feasible_distance) / (2.0 * feasible_distance)
    height_sq = max(0.0, length_a * length_a - x * x)
    height = math.sqrt(height_sq)
    base = first + direction * x
    normal = np.asarray((-direction[1], direction[0]))
    candidates = (base + normal * height, base - normal * height)
    if preferred_middle is None or not np.isfinite(preferred_middle).all():
        return candidates[0].astype(np.float32)
    preferred = np.asarray(preferred_middle, dtype=np.float64)
    selected = min(candidates, key=lambda value: float(np.linalg.norm(value - preferred)))
    return selected.astype(np.float32)


def detect_and_correct_side_swaps(
    frames: list[TemporalFrame], body_scales: Sequence[float], *, margin_ratio: float = 0.10
) -> list[bool]:
    """Correct isolated label swaps using parent topology and temporal trajectories."""

    corrected = [False] * len(frames)
    for index in range(1, len(frames) - 1):
        frame = frames[index]
        scale = max(float(body_scales[index]), 1.0)
        pairs_to_swap: list[tuple[int, int]] = []
        for left, right in SIDE_PAIRS:
            if not all(_analysis_valid(item, joint) for item in (frames[index - 1], frame, frames[index + 1]) for joint in (left, right)):
                continue
            current_left = frame.analysis_points[left]; current_right = frame.analysis_points[right]
            expected_left = (frames[index - 1].analysis_points[left] + frames[index + 1].analysis_points[left]) * 0.5
            expected_right = (frames[index - 1].analysis_points[right] + frames[index + 1].analysis_points[right]) * 0.5
            direct = float(np.linalg.norm(current_left - expected_left) + np.linalg.norm(current_right - expected_right))
            swapped = float(np.linalg.norm(current_right - expected_left) + np.linalg.norm(current_left - expected_right))
            if swapped + scale * margin_ratio < direct:
                pairs_to_swap.append((left, right))
        if not pairs_to_swap:
            continue
        points = frame.analysis_points.copy(); scores = frame.analysis_scores.copy()
        render_points = frame.render_points.copy(); render_scores = frame.render_scores.copy()
        sources = list(frame.sources); usable = frame.analysis_usable.copy(); ages = frame.prediction_age_seconds.copy(); flow = frame.flow_errors.copy()
        for left, right in pairs_to_swap:
            for values in (points, render_points):
                values[[left, right]] = values[[right, left]]
            for values in (scores, render_scores, usable, ages, flow):
                values[[left, right]] = values[[right, left]]
            sources[left], sources[right] = sources[right], sources[left]
        frames[index] = replace(frame, analysis_points=points, analysis_scores=scores, render_points=render_points, render_scores=render_scores, sources=tuple(sources), analysis_usable=usable, prediction_age_seconds=ages, flow_errors=flow)
        corrected[index] = True
    return corrected


def _update_state(
    state: _State, measurement: np.ndarray | None, quality: float, timestamp: float,
    dt: float, body_scale: float, root_motion: np.ndarray, maximum_age: float,
) -> tuple[np.ndarray | None, bool]:
    previous_position = state.position.copy() if state.position is not None else None
    previous_velocity = state.velocity.copy() if state.velocity is not None else np.zeros(2, dtype=np.float32)
    previous_acceleration = state.acceleration.copy() if state.acceleration is not None else np.zeros(2, dtype=np.float32)
    prediction = None
    if previous_position is not None:
        prediction = previous_position + previous_velocity * dt + 0.5 * previous_acceleration * dt * dt + root_motion * 0.15
    was_jump = False
    if measurement is not None and np.isfinite(measurement).all():
        if prediction is None:
            position = measurement.astype(np.float32)
        else:
            residual = measurement - prediction
            normalized_jump = float(np.linalg.norm(residual) / max(body_scale, 1e-6))
            speed = float(np.linalg.norm(previous_velocity) / max(body_scale, 1e-6))
            jump_gate = 0.16 + min(0.18, speed * 0.10)
            was_jump = normalized_jump > jump_gate and quality < 0.94
            if was_jump:
                position = prediction.astype(np.float32)
            else:
                responsiveness = float(np.clip(0.58 + 0.30 * quality + 0.08 * min(speed, 1.0), 0.58, 0.96))
                position = (prediction + responsiveness * residual).astype(np.float32)
        velocity = (position - previous_position) / dt if previous_position is not None else np.zeros(2, dtype=np.float32)
        acceleration = (velocity - previous_velocity) / dt
        state.position = position; state.velocity = velocity.astype(np.float32); state.acceleration = acceleration.astype(np.float32)
        state.timestamp = timestamp; state.age_seconds = 0.0
        state.uncertainty = float(np.clip((1.0 - quality) * 0.55 + (0.30 if was_jump else 0.0), 0.0, 1.0))
        return position, was_jump
    if prediction is None:
        return None, False
    state.age_seconds += dt
    state.uncertainty = float(np.clip(state.uncertainty + dt / max(maximum_age, 1e-6) * 0.42, 0.0, 1.0))
    if state.age_seconds > maximum_age:
        return None, False
    state.position = prediction.astype(np.float32); state.velocity = (previous_velocity * 0.92).astype(np.float32)
    state.acceleration = (previous_acceleration * 0.75).astype(np.float32); state.timestamp = timestamp
    return state.position, False


def _preferred_middle(frames: Sequence[TemporalFrame], index: int, joint: int, current: np.ndarray | None) -> np.ndarray | None:
    values = []
    if current is not None:
        values.append(np.asarray(current, dtype=np.float32))
    for candidate_index in (index - 1, index + 1):
        if 0 <= candidate_index < len(frames) and _render_valid(frames[candidate_index], joint):
            values.append(frames[candidate_index].render_points[joint])
    return np.mean(values, axis=0).astype(np.float32) if values else None


def _bone_errors(frame: TemporalFrame, profile: CanonicalBodyProfile, scale: float) -> dict[str, float]:
    output: dict[str, float] = {}
    for name, (first, second) in CANONICAL_BONES.items():
        expected = profile.expected_pixels(name, scale)
        if expected is None or expected <= 1e-6 or not _analysis_valid(frame, first) or not _analysis_valid(frame, second):
            continue
        actual = float(np.linalg.norm(frame.analysis_points[second] - frame.analysis_points[first]))
        output[name] = round(abs(actual - expected) / expected, 6)
    torso_expected = profile.expected_pixels("torso_length", scale)
    if torso_expected is not None and torso_expected > 1e-6 and all(_analysis_valid(frame, index) for index in (5, 6, 11, 12)):
        shoulder_midpoint = (frame.analysis_points[5] + frame.analysis_points[6]) * 0.5
        hip_midpoint = (frame.analysis_points[11] + frame.analysis_points[12]) * 0.5
        actual = float(np.linalg.norm(shoulder_midpoint - hip_midpoint))
        output["torso_length"] = round(abs(actual - torso_expected) / torso_expected, 6)
    return output


def _serialize_state(state: _State, source: PointSource) -> dict[str, object]:
    confidence = float(np.clip(1.0 - state.uncertainty, 0.0, 1.0))
    return JointEstimate(_tuple(state.position), _tuple(state.velocity) or (0.0, 0.0), _tuple(state.acceleration) or (0.0, 0.0), state.uncertainty, confidence, source.value, state.age_seconds).to_dict()


def _copy_frame(frame: TemporalFrame) -> TemporalFrame:
    return replace(frame, analysis_points=frame.analysis_points.copy(), analysis_scores=frame.analysis_scores.copy(), render_points=frame.render_points.copy(), render_scores=frame.render_scores.copy(), analysis_usable=frame.analysis_usable.copy(), prediction_age_seconds=frame.prediction_age_seconds.copy(), flow_errors=frame.flow_errors.copy())


def _strong_joint(frame: TemporalFrame, index: int, minimum: float) -> bool:
    return _analysis_valid(frame, index) and frame.sources[index] in _STRONG_SOURCES and float(frame.analysis_scores[index]) >= minimum


def _analysis_valid(frame: TemporalFrame, index: int) -> bool:
    return index < frame.analysis_scores.size and bool(frame.analysis_usable[index]) and float(frame.analysis_scores[index]) > 0.0 and np.isfinite(frame.analysis_points[index]).all()


def _analysis_valid_arrays(points: np.ndarray, scores: np.ndarray, usable: np.ndarray, index: int) -> bool:
    return index < scores.size and bool(usable[index]) and float(scores[index]) > 0.0 and np.isfinite(points[index]).all()


def _render_valid(frame: TemporalFrame, index: int) -> bool:
    return index < frame.render_scores.size and float(frame.render_scores[index]) > 0.0 and np.isfinite(frame.render_points[index]).all()


def _midpoint(frame: TemporalFrame, first: int, second: int) -> np.ndarray | None:
    return (frame.render_points[first] + frame.render_points[second]) * 0.5 if _render_valid(frame, first) and _render_valid(frame, second) else None


def _segments_cross(frame: TemporalFrame, first: tuple[int, int], second: tuple[int, int]) -> bool:
    if not all(_analysis_valid(frame, index) for index in (*first, *second)):
        return False
    a, b = frame.analysis_points[first[0]], frame.analysis_points[first[1]]
    c, d = frame.analysis_points[second[0]], frame.analysis_points[second[1]]
    def orientation(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> float:
        first_vector = q - p; second_vector = r - p
        return float(first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0])
    return orientation(a, b, c) * orientation(a, b, d) < 0.0 and orientation(c, d, a) * orientation(c, d, b) < 0.0


def _tuple(value: np.ndarray | None) -> tuple[float, float] | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float).reshape(-1)
    return (float(array[0]), float(array[1])) if array.size == 2 and np.isfinite(array).all() else None


def _rounded_point(value: tuple[float, float] | None) -> list[float] | None:
    return [round(value[0], 3), round(value[1], 3)] if value is not None else None


def _empty_summary() -> dict[str, object]:
    return {"canonical_body_profile": CanonicalBodyProfile({}).to_dict(), "anatomical_projection_correction_count": 0, "kinematic_reconstruction_count": 0, "side_swap_correction_count": 0, "detected_joint_jump_count": 0, "joint_jump_event_count": 0, "input_bone_length_stability_error": 0.0, "bone_length_stability_error": 0.0, "maximum_bone_length_error": 0.0}
