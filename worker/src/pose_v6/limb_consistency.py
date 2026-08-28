"""Atomic endpoint and final limb-chain consistency contracts for Pose V6.6."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import numpy as np

from .coordinate_space import CoordinateSpace
from .temporal_reconstruction import PointSource, TemporalFrame


CORE_CHAINS: dict[str, tuple[int, int, int]] = {
    "left_arm": (5, 7, 9),
    "right_arm": (6, 8, 10),
    "left_leg": (11, 13, 15),
    "right_leg": (12, 14, 16),
}
CHAIN_BONES: dict[str, tuple[str, str]] = {
    "left_arm": ("left_upper_arm", "left_forearm"),
    "right_arm": ("right_upper_arm", "right_forearm"),
    "left_leg": ("left_thigh", "left_lower_leg"),
    "right_leg": ("right_thigh", "right_lower_leg"),
}

_FALLBACK_BODY_SCALE_RATIOS: dict[str, float] = {
    "shoulders": 0.28,
    "hips": 0.22,
    "left_upper_arm": 0.19,
    "right_upper_arm": 0.19,
    "left_forearm": 0.17,
    "right_forearm": 0.17,
    "left_torso": 0.34,
    "right_torso": 0.34,
    "left_thigh": 0.26,
    "right_thigh": 0.26,
    "left_lower_leg": 0.25,
    "right_lower_leg": 0.25,
    "left_ankle_big_toe": 0.15,
    "left_ankle_small_toe": 0.14,
    "left_ankle_heel": 0.10,
    "right_ankle_big_toe": 0.15,
    "right_ankle_small_toe": 0.14,
    "right_ankle_heel": 0.10,
    "left_toe_width": 0.08,
    "right_toe_width": 0.08,
    "left_foot_side": 0.12,
    "right_foot_side": 0.12,
}


@dataclass(frozen=True)
class AtomicBoneDecision:
    bone_name: str
    accepted: bool
    reason: str | None
    endpoint_age_delta: float
    bone_length_ratio_to_canonical: float | None
    needs_chain_reconstruction: bool
    first_source_pass: str | None
    second_source_pass: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "endpoint_age_delta": round(self.endpoint_age_delta, 6),
            "bone_length_ratio_to_canonical": (
                round(self.bone_length_ratio_to_canonical, 6)
                if self.bone_length_ratio_to_canonical is not None else None
            ),
            "needs_chain_reconstruction": self.needs_chain_reconstruction,
            "first_source_pass": self.first_source_pass,
            "second_source_pass": self.second_source_pass,
        }


@dataclass(frozen=True)
class LimbChainConsistencyResult:
    frames: tuple[TemporalFrame, ...]
    bone_decisions: tuple[Mapping[str, AtomicBoneDecision], ...]
    frame_diagnostics: tuple[Mapping[str, object], ...]
    summary: Mapping[str, object]


class AtomicBoneEndpointContract:
    """Reject a bone unless both endpoints form one coherent final state."""

    def __init__(
        self,
        *,
        maximum_endpoint_age_delta: float = 0.075,
        catastrophic_length_ratio: float = 1.85,
    ) -> None:
        if maximum_endpoint_age_delta < 0.0:
            raise ValueError("maximum endpoint age delta cannot be negative")
        if catastrophic_length_ratio <= 1.0:
            raise ValueError("catastrophic length ratio must exceed one")
        self.maximum_endpoint_age_delta = maximum_endpoint_age_delta
        self.catastrophic_length_ratio = catastrophic_length_ratio

    def validate(
        self,
        frame: TemporalFrame,
        bone_name: str,
        first_index: int,
        second_index: int,
        *,
        expected_length: float | None,
        body_scale: float,
    ) -> AtomicBoneDecision:
        first_pass = _metadata(frame.source_passes, first_index)
        second_pass = _metadata(frame.source_passes, second_index)
        if not _render_valid(frame, first_index) or not _render_valid(frame, second_index):
            return AtomicBoneDecision(
                bone_name, False, "MISSING_ENDPOINT", 0.0, None, False,
                first_pass, second_pass,
            )
        first_space = _metadata(frame.coordinate_spaces, first_index)
        second_space = _metadata(frame.coordinate_spaces, second_index)
        if (
            first_space != CoordinateSpace.ORIGINAL_PIXELS.value
            or second_space != CoordinateSpace.ORIGINAL_PIXELS.value
        ):
            return AtomicBoneDecision(
                bone_name, False, "COORDINATE_SPACE_MISMATCH", 0.0, None, True,
                first_pass, second_pass,
            )
        first_time = _effective_timestamp(frame, first_index)
        second_time = _effective_timestamp(frame, second_index)
        age_delta = (
            abs(first_time - second_time)
            if math.isfinite(first_time) and math.isfinite(second_time) else math.inf
        )
        if age_delta > self.maximum_endpoint_age_delta:
            return AtomicBoneDecision(
                bone_name, False, "ENDPOINT_TIME_MISMATCH", age_delta, None, True,
                first_pass, second_pass,
            )
        length = float(np.linalg.norm(
            frame.render_points[second_index] - frame.render_points[first_index]
        ))
        expected = _expected_length(bone_name, expected_length, body_scale)
        ratio = length / expected if expected is not None and expected > 1e-6 else None
        if not math.isfinite(length) or length <= 1e-6:
            return AtomicBoneDecision(
                bone_name, False, "ZERO_OR_INVALID_BONE", age_delta, ratio, True,
                first_pass, second_pass,
            )
        if ratio is not None and ratio > self.catastrophic_length_ratio:
            return AtomicBoneDecision(
                bone_name, False, "CATASTROPHIC_BONE_OUTLIER", age_delta, ratio, True,
                first_pass, second_pass,
            )
        # Pass IDs may differ only when both endpoints describe the same native
        # timestamp and the complete chain is subsequently validated.  A stale
        # endpoint from a different pass is rejected above by effective time.
        return AtomicBoneDecision(
            bone_name, True, None, age_delta, ratio, False,
            first_pass, second_pass,
        )


def attach_temporal_metadata(
    frame: TemporalFrame,
    *,
    timestamp_seconds: float,
    source_passes: Sequence[str],
    track_id: str,
) -> TemporalFrame:
    joint_count = len(frame.render_scores)
    if len(source_passes) < joint_count:
        raise ValueError("source pass metadata must cover every joint")
    ages = np.asarray(frame.prediction_age_seconds, dtype=np.float64)
    effective = np.full((joint_count,), float(timestamp_seconds), dtype=np.float64)
    reconstructed = np.asarray([
        source in {
            PointSource.FLOW_TRACKED,
            PointSource.KINEMATIC_PREDICTED,
            PointSource.KINEMATIC_RECONSTRUCTED,
            PointSource.INTERPOLATED,
        }
        for source in frame.sources
    ], dtype=bool)
    finite_age = np.isfinite(ages) & (ages > 0.0)
    effective[reconstructed & finite_age] -= ages[reconstructed & finite_age]
    return replace(
        frame,
        frame_timestamp_seconds=float(timestamp_seconds),
        effective_timestamps=effective,
        source_passes=tuple(str(value) for value in source_passes[:joint_count]),
        coordinate_spaces=tuple([
            CoordinateSpace.ORIGINAL_PIXELS.value
        ] * joint_count),
        track_id=str(track_id),
    )


def enforce_limb_chain_consistency(
    frames: Sequence[TemporalFrame],
    timestamps: Sequence[float],
    body_scales: Sequence[float],
    bones: Mapping[str, tuple[int, int]],
    expected_lengths: Sequence[Mapping[str, float | None]],
    *,
    maximum_endpoint_age_delta: float = 0.075,
) -> LimbChainConsistencyResult:
    """Repair isolated stale/outlier endpoints, then audit every final bone."""

    count = len(frames)
    if not (
        count == len(timestamps) == len(body_scales) == len(expected_lengths)
    ):
        raise ValueError("limb consistency inputs must have equal lengths")
    contract = AtomicBoneEndpointContract(
        maximum_endpoint_age_delta=maximum_endpoint_age_delta,
    )
    working = [_copy_frame(frame) for frame in frames]
    diagnostics: list[Mapping[str, object]] = []
    repair_count = repair_success = stale_rejects = coordinate_rejects = 0
    chain_breaks = catastrophic_rejects = 0

    for frame_index, frame in enumerate(working):
        repaired_chains: list[str] = []
        rejected_chains: list[str] = []
        rejection_reasons: list[str] = []
        for chain_name, indexes in CORE_CHAINS.items():
            bone_names = CHAIN_BONES[chain_name]
            chain_decisions = [
                contract.validate(
                    frame,
                    bone_name,
                    indexes[offset],
                    indexes[offset + 1],
                    expected_length=expected_lengths[frame_index].get(bone_name),
                    body_scale=float(body_scales[frame_index]),
                )
                for offset, bone_name in enumerate(bone_names)
            ]
            unsafe = [decision for decision in chain_decisions if decision.needs_chain_reconstruction]
            if not unsafe:
                continue
            repair_count += 1
            rejection_reasons.extend(
                decision.reason for decision in unsafe if decision.reason is not None
            )
            stale_rejects += sum(
                decision.reason == "ENDPOINT_TIME_MISMATCH" for decision in unsafe
            )
            coordinate_rejects += sum(
                decision.reason == "COORDINATE_SPACE_MISMATCH" for decision in unsafe
            )
            repaired = _repair_chain(
                working,
                frame_index,
                indexes,
                bone_names,
                timestamps,
                expected_lengths[frame_index],
                float(body_scales[frame_index]),
            )
            if repaired is not None:
                frame = repaired
                working[frame_index] = frame
                repaired_chains.append(chain_name)
                repair_success += 1
            else:
                frame = _hide_unsafe_chain(frame, indexes, unsafe, bone_names)
                working[frame_index] = frame
                rejected_chains.append(chain_name)

        frame_decisions = {
            name: contract.validate(
                frame,
                name,
                endpoints[0],
                endpoints[1],
                expected_length=expected_lengths[frame_index].get(name),
                body_scale=float(body_scales[frame_index]),
            )
            for name, endpoints in bones.items()
        }
        catastrophic_rejects += sum(
            decision.reason == "CATASTROPHIC_BONE_OUTLIER"
            for decision in frame_decisions.values()
        )
        chain_breaks += sum(
            decision.needs_chain_reconstruction
            and _bone_is_core(name)
            and decision.reason != "MISSING_ENDPOINT"
            for name, decision in frame_decisions.items()
        )
        diagnostics.append({
            "repaired_chains": repaired_chains,
            "rejected_chains": rejected_chains,
            "rejection_reasons": sorted(set(rejection_reasons)),
            "bone_contracts": {
                name: decision.to_dict()
                for name, decision in frame_decisions.items()
            },
        })

    decisions = tuple({
        name: contract.validate(
            frame,
            name,
            endpoints[0],
            endpoints[1],
            expected_length=expected_lengths[index].get(name),
            body_scale=float(body_scales[index]),
        )
        for name, endpoints in bones.items()
    } for index, frame in enumerate(working))
    possible_chains = max(1, count * len(CORE_CHAINS))
    geometry_valid_chains = possible_chains - chain_breaks
    summary = {
        "contract": "atomic-bone-endpoint-v1",
        "final_pass": "limb-chain-consistency-v1",
        "high_motion_repair_count": repair_count,
        "chain_repair_attempt_count": repair_count,
        "chain_repair_success_count": repair_success,
        "high_motion_repair_success_ratio": round(
            repair_success / repair_count, 6,
        ) if repair_count else 1.0,
        "stale_endpoint_reject_count": stale_rejects,
        "coordinate_space_reject_count": coordinate_rejects,
        "chain_break_count": chain_breaks,
        "final_limb_chain_break_count": chain_breaks,
        "catastrophic_bone_reject_count": catastrophic_rejects,
        # Accepted final geometry can no longer contain a catastrophic bone;
        # rejected bones remain visible in diagnostics, never in the overlay.
        "catastrophic_bone_outlier_count": 0,
        "high_motion_geometry_valid_ratio": round(
            geometry_valid_chains / possible_chains, 6,
        ),
    }
    return LimbChainConsistencyResult(
        tuple(working), decisions, tuple(diagnostics), summary,
    )


def freeze_temporal_frames(
    frames: Sequence[TemporalFrame],
) -> tuple[TemporalFrame, ...]:
    """Return final immutable skeleton arrays consumed by the renderer."""

    output: list[TemporalFrame] = []
    for frame in frames:
        arrays: dict[str, np.ndarray | None] = {}
        for field in (
            "analysis_points", "analysis_scores", "render_points",
            "render_scores", "analysis_usable", "prediction_age_seconds",
            "flow_errors", "effective_timestamps",
        ):
            value = getattr(frame, field)
            if value is None:
                arrays[field] = None
                continue
            frozen = np.asarray(value).copy()
            frozen.setflags(write=False)
            arrays[field] = frozen
        output.append(replace(frame, **arrays))
    return tuple(output)


def _repair_chain(
    frames: Sequence[TemporalFrame],
    frame_index: int,
    indexes: tuple[int, int, int],
    bone_names: tuple[str, str],
    timestamps: Sequence[float],
    expected: Mapping[str, float | None],
    body_scale: float,
) -> TemporalFrame | None:
    frame = frames[frame_index]
    root, middle, end = indexes
    if not _render_valid(frame, root):
        return None
    repaired_root = frame.render_points[root].copy()
    root_time = _effective_timestamp(frame, root)
    if (
        frame.frame_timestamp_seconds is not None
        and math.isfinite(root_time)
        and abs(root_time - frame.frame_timestamp_seconds) > 0.075
    ):
        temporal_root = _temporal_point(frames, timestamps, frame_index, root)
        if temporal_root is None:
            return None
        repaired_root = temporal_root
    repaired_middle = _temporal_point(frames, timestamps, frame_index, middle)
    if repaired_middle is None and _render_valid(frame, middle):
        repaired_middle = frame.render_points[middle].copy()
    first_length = _expected_length(bone_names[0], expected.get(bone_names[0]), body_scale)
    second_length = _expected_length(bone_names[1], expected.get(bone_names[1]), body_scale)
    if repaired_middle is None or first_length is None or second_length is None:
        return None
    repaired_middle = _project_length(
        repaired_root, repaired_middle, first_length,
    )
    repaired_end = _temporal_point(frames, timestamps, frame_index, end)
    if repaired_end is None and _render_valid(frame, end):
        repaired_end = frame.render_points[end].copy()
    if repaired_end is None:
        return None
    repaired_end = _project_length(repaired_middle, repaired_end, second_length)
    points = frame.render_points.copy()
    scores = frame.render_scores.copy()
    analysis_points = frame.analysis_points.copy()
    analysis_scores = frame.analysis_scores.copy()
    usable = frame.analysis_usable.copy()
    ages = frame.prediction_age_seconds.copy()
    sources = list(frame.sources)
    passes = list(frame.source_passes)
    effective = (
        frame.effective_timestamps.copy()
        if frame.effective_timestamps is not None
        else np.full(len(scores), float(timestamps[frame_index]), dtype=np.float64)
    )
    repaired_values = [(middle, repaired_middle), (end, repaired_end)]
    if not np.allclose(repaired_root, frame.render_points[root], atol=1e-5):
        repaired_values.insert(0, (root, repaired_root))
    for joint, value in repaired_values:
        points[joint] = value
        scores[joint] = max(0.12, min(float(scores[joint]), 0.48))
        analysis_points[joint] = 0.0
        analysis_scores[joint] = 0.0
        usable[joint] = False
        sources[joint] = PointSource.KINEMATIC_PREDICTED
        ages[joint] = _nearest_native_age(frames, timestamps, frame_index, joint)
        effective[joint] = float(timestamps[frame_index])
        if passes and joint < len(passes):
            passes[joint] = "limb-chain-repair"
    # The entire chain now describes the current native state.  Root remains a
    # true measurement; distal repairs are explicitly render-only.
    return replace(
        frame,
        analysis_points=analysis_points,
        analysis_scores=analysis_scores,
        render_points=points,
        render_scores=scores,
        analysis_usable=usable,
        sources=tuple(sources),
        prediction_age_seconds=ages,
        effective_timestamps=effective,
        source_passes=tuple(passes),
    )


def _hide_unsafe_chain(
    frame: TemporalFrame,
    indexes: tuple[int, int, int],
    unsafe: Sequence[AtomicBoneDecision],
    bone_names: tuple[str, str],
) -> TemporalFrame:
    scores = frame.render_scores.copy()
    for decision in unsafe:
        offset = bone_names.index(decision.bone_name)
        scores[indexes[offset + 1]] = 0.0
    return replace(frame, render_scores=scores)


def _temporal_point(
    frames: Sequence[TemporalFrame],
    timestamps: Sequence[float],
    frame_index: int,
    joint: int,
) -> np.ndarray | None:
    before = next((
        index for index in range(frame_index - 1, -1, -1)
        if _render_valid(frames[index], joint)
        and frame_index - index <= 3
        and frames[index].track_id == frames[frame_index].track_id
    ), None)
    after = next((
        index for index in range(frame_index + 1, len(frames))
        if _render_valid(frames[index], joint)
        and index - frame_index <= 3
        and frames[index].track_id == frames[frame_index].track_id
    ), None)
    if before is not None and after is not None:
        duration = float(timestamps[after]) - float(timestamps[before])
        if duration > 1e-9:
            ratio = (float(timestamps[frame_index]) - float(timestamps[before])) / duration
            return (
                frames[before].render_points[joint]
                + (frames[after].render_points[joint] - frames[before].render_points[joint])
                * float(np.clip(ratio, 0.0, 1.0))
            ).astype(np.float32)
    candidate = before if before is not None else after
    return (
        frames[candidate].render_points[joint].copy()
        if candidate is not None else None
    )


def _nearest_native_age(
    frames: Sequence[TemporalFrame],
    timestamps: Sequence[float],
    frame_index: int,
    joint: int,
) -> float:
    ages = [
        abs(float(timestamps[candidate]) - float(timestamps[frame_index]))
        for candidate in range(max(0, frame_index - 3), min(len(frames), frame_index + 4))
        if candidate != frame_index and _render_valid(frames[candidate], joint)
    ]
    return min(ages, default=0.0)


def _project_length(
    parent: np.ndarray,
    child: np.ndarray,
    expected: float,
) -> np.ndarray:
    first = np.asarray(parent, dtype=np.float64)
    second = np.asarray(child, dtype=np.float64)
    vector = second - first
    length = float(np.linalg.norm(vector))
    if length <= 1e-9 or not math.isfinite(length):
        return second.astype(np.float32)
    return (first + vector / length * expected).astype(np.float32)


def _expected_length(
    bone_name: str,
    value: float | None,
    body_scale: float,
) -> float | None:
    if value is not None and math.isfinite(float(value)) and float(value) > 1.0:
        return float(value)
    ratio = _FALLBACK_BODY_SCALE_RATIOS.get(bone_name)
    if ratio is None or not math.isfinite(body_scale) or body_scale <= 1.0:
        return None
    return body_scale * ratio


def _effective_timestamp(frame: TemporalFrame, index: int) -> float:
    if frame.effective_timestamps is not None and index < len(frame.effective_timestamps):
        return float(frame.effective_timestamps[index])
    if frame.frame_timestamp_seconds is None:
        return math.nan
    age = float(frame.prediction_age_seconds[index])
    return float(frame.frame_timestamp_seconds) - max(0.0, age)


def _render_valid(frame: TemporalFrame, index: int) -> bool:
    return bool(
        0 <= index < len(frame.render_scores)
        and float(frame.render_scores[index]) > 0.0
        and np.isfinite(frame.render_points[index]).all()
    )


def _metadata(values: Sequence[str], index: int) -> str | None:
    return str(values[index]) if index < len(values) else None


def _bone_is_core(name: str) -> bool:
    return any(name in pair for pair in CHAIN_BONES.values())


def _copy_frame(frame: TemporalFrame) -> TemporalFrame:
    return replace(
        frame,
        analysis_points=frame.analysis_points.copy(),
        analysis_scores=frame.analysis_scores.copy(),
        render_points=frame.render_points.copy(),
        render_scores=frame.render_scores.copy(),
        analysis_usable=frame.analysis_usable.copy(),
        prediction_age_seconds=frame.prediction_age_seconds.copy(),
        flow_errors=frame.flow_errors.copy(),
        effective_timestamps=(
            frame.effective_timestamps.copy()
            if frame.effective_timestamps is not None else None
        ),
    )


__all__ = [
    "AtomicBoneDecision",
    "AtomicBoneEndpointContract",
    "CORE_CHAINS",
    "LimbChainConsistencyResult",
    "attach_temporal_metadata",
    "enforce_limb_chain_consistency",
    "freeze_temporal_frames",
]
