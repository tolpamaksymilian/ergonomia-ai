"""Full-body hypotheses, beam sequence solve and bounded repair for Pose V6.8."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Sequence

import numpy as np

from .config import GlobalBodyConfig
from .silhouette import (
    PersonSilhouetteFrame,
    SkeletonSilhouetteEvidence,
    signed_distance_field,
)
from .temporal_reconstruction import PointSource, TemporalFrame


BODY_CHAINS: dict[str, tuple[int, ...]] = {
    "left_arm": (5, 7, 9),
    "right_arm": (6, 8, 10),
    "left_leg": (11, 13, 15, 17, 18, 19),
    "right_leg": (12, 14, 16, 20, 21, 22),
}
CORE_BONES: dict[str, tuple[int, int]] = {
    "left_upper_arm": (5, 7),
    "left_forearm": (7, 9),
    "right_upper_arm": (6, 8),
    "right_forearm": (8, 10),
    "left_thigh": (11, 13),
    "left_lower_leg": (13, 15),
    "right_thigh": (12, 14),
    "right_lower_leg": (14, 16),
}
ROOT_JOINTS = (5, 6, 11, 12)


@dataclass(frozen=True)
class FullBodyHypothesis:
    hypothesis_id: str
    points: np.ndarray
    scores: np.ndarray
    joint_provenance: tuple[str, ...]
    full_body_score: float
    components: dict[str, float]
    hard_rejection_reasons: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.hard_rejection_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "full_body_score": round(self.full_body_score, 6),
            "components": {key: round(value, 6) for key, value in self.components.items()},
            "hard_rejection_reasons": list(self.hard_rejection_reasons),
            "valid": self.valid,
        }


@dataclass(frozen=True)
class ImmutableFinalBodyState:
    frame: TemporalFrame
    selected_hypothesis_id: str
    body_quality: float
    joint_provenance: tuple[str, ...]
    repair_iteration: int
    decision_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_hypothesis_id": self.selected_hypothesis_id,
            "body_quality": round(self.body_quality, 6),
            "joint_provenance": list(self.joint_provenance),
            "repair_iteration": self.repair_iteration,
            "decision_reasons": list(self.decision_reasons),
            "immutable": True,
        }


@dataclass(frozen=True)
class GlobalBodySolveResult:
    states: tuple[ImmutableFinalBodyState, ...]
    frame_diagnostics: tuple[dict[str, object], ...]
    summary: dict[str, object]

    @property
    def frames(self) -> tuple[TemporalFrame, ...]:
        return tuple(state.frame for state in self.states)


def solve_global_body_sequence(
    frames: Sequence[TemporalFrame],
    raw_points: Sequence[np.ndarray],
    raw_scores: Sequence[np.ndarray],
    silhouettes: Sequence[PersonSilhouetteFrame],
    silhouette_evidence: Sequence[SkeletonSilhouetteEvidence],
    body_scales: Sequence[float],
    timestamps: Sequence[float],
    motion_states: Sequence[str],
    scene_cuts: Sequence[bool],
    *,
    config: GlobalBodyConfig,
    body_joint_count: int = 23,
) -> GlobalBodySolveResult:
    count = len(frames)
    if any(len(values) != count for values in (
        raw_points, raw_scores, silhouettes, silhouette_evidence, body_scales,
        timestamps, motion_states, scene_cuts,
    )):
        raise ValueError("global body solver inputs must have equal lengths")
    if not frames:
        return GlobalBodySolveResult((), (), _empty_summary())
    hypotheses = [
        _build_frame_hypotheses(
            index,
            frames,
            raw_points,
            raw_scores,
            silhouettes[index],
            body_scale=float(body_scales[index]),
            body_joint_count=body_joint_count,
        )
        for index in range(count)
    ]
    selected_indexes = _beam_sequence_solve(
        hypotheses,
        timestamps,
        body_scales,
        scene_cuts,
        silhouettes,
        beam_width=config.beam_width,
    ) if config.enabled else [0] * count
    selected = [hypotheses[index][choice] for index, choice in enumerate(selected_indexes)]
    iterations = [0] * count
    rollback_count = 0
    repaired_indexes: set[int] = set()
    worst_count = max(1, int(math.ceil(count * config.worst_frame_ratio)))
    for iteration in range(1, config.maximum_repair_iterations + 1):
        ranked = sorted(range(count), key=lambda index: selected[index].full_body_score)[:worst_count]
        improved = False
        for index in ranked:
            best = max(
                (candidate for candidate in hypotheses[index] if candidate.valid),
                key=lambda candidate: candidate.full_body_score,
                default=selected[index],
            )
            if best.full_body_score >= selected[index].full_body_score + config.minimum_quality_gain:
                selected[index] = best
                iterations[index] = iteration
                repaired_indexes.add(index)
                improved = True
            else:
                rollback_count += 1
        if not improved:
            break
    states: list[ImmutableFinalBodyState] = []
    diagnostics: list[dict[str, object]] = []
    switch_count = 0
    previous_id: str | None = None
    catastrophic_count = 0
    for index, candidate in enumerate(selected):
        if previous_id is not None and candidate.hypothesis_id != previous_id:
            switch_count += 1
        previous_id = candidate.hypothesis_id
        catastrophic_count += any(reason.startswith("CATASTROPHIC") for reason in candidate.hard_rejection_reasons)
        state = _immutable_state(
            frames[index],
            candidate,
            repair_iteration=iterations[index],
        )
        states.append(state)
        diagnostics.append({
            "selected": candidate.to_dict(),
            "candidate_count": len(hypotheses[index]),
            "candidates": [item.to_dict() for item in hypotheses[index]],
            "repair_iteration": iterations[index],
            "mask_alignment": silhouette_evidence[index].to_dict(),
        })
    qualities = sorted(state.body_quality for state in states)
    floor_evidence = estimate_ground_line(states, silhouettes, body_scales)
    specialist = summarize_chain_specialists(states, silhouettes, body_scales)
    summary = {
        "version": "global-body-solver-v1",
        "enabled": config.enabled,
        "strategy": "full-body-beam-search-with-peak-repair",
        "frame_count": count,
        "full_body_geometry_valid_ratio": round(sum(state.body_quality > 0.0 for state in states) / count, 6),
        "full_body_hypothesis_switch_count": switch_count,
        "maximum_hypotheses_per_frame": max(map(len, hypotheses), default=0),
        "composite_hypotheses_generated": sum(
            candidate.hypothesis_id.startswith("H2_CHAIN_FUSION_")
            for frame_hypotheses in hypotheses
            for candidate in frame_hypotheses
        ),
        "catastrophic_body_geometry_count": catastrophic_count,
        "worst_1_percent_body_quality": round(float(np.mean(qualities[:max(1, int(math.ceil(count * 0.01)))])), 6),
        "deep_repair_frame_count": len(repaired_indexes),
        "deep_repair_iterations_executed": max(iterations, default=0),
        "deep_repair_rollback_count": rollback_count,
        "best_state_history_preserved": True,
        "sequence_solver": {
            "algorithm": "beam-search",
            "beam_width": config.beam_width,
            "uses_native_frames_only": True,
            "transition_terms": [
                "velocity", "acceleration", "jerk", "bone_length_change",
                "side_identity", "root_movement", "silhouette_movement",
                "limb_chain_continuity",
            ],
        },
        "ground_line_evidence": floor_evidence,
        **specialist,
    }
    return GlobalBodySolveResult(tuple(states), tuple(diagnostics), summary)


def _build_frame_hypotheses(
    index: int,
    frames: Sequence[TemporalFrame],
    raw_points: Sequence[np.ndarray],
    raw_scores: Sequence[np.ndarray],
    silhouette: PersonSilhouetteFrame,
    *,
    body_scale: float,
    body_joint_count: int,
) -> tuple[FullBodyHypothesis, ...]:
    base = frames[index]
    candidates: list[tuple[str, np.ndarray, np.ndarray, list[str]]] = [(
        "H0_FINAL_V67",
        base.render_points.copy(),
        base.render_scores.copy(),
        [_source_name(source) for source in base.sources],
    )]
    raw_value = np.asarray(raw_points[index], dtype=np.float32)
    raw_quality = np.asarray(raw_scores[index], dtype=np.float32)
    raw_chain_replacements: dict[str, tuple[int, ...]] = {}
    for chain_name, chain in BODY_CHAINS.items():
        if raw_value.ndim != 2 or raw_quality.ndim != 1 or any(joint >= len(raw_quality) for joint in chain):
            continue
        replaceable = [
            joint for joint in chain[1:]
            if raw_quality[joint] > 0.12 and np.isfinite(raw_value[joint]).all()
        ]
        if len(replaceable) < 2:
            continue
        raw_chain_replacements[chain_name] = tuple(replaceable)
    available_chains = tuple(raw_chain_replacements)
    # A body hypothesis may combine several complete, validated limb chains,
    # but roots (shoulders/hips) always remain the same.  This avoids forcing
    # the sequence solver to choose between a good arm and a good leg.
    for chain_count in range(1, len(available_chains) + 1):
        for selected_chains in combinations(available_chains, chain_count):
            points = base.render_points.copy(); scores = base.render_scores.copy()
            provenance = [_source_name(source) for source in base.sources]
            for chain_name in selected_chains:
                for joint in raw_chain_replacements[chain_name]:
                    points[joint] = raw_value[joint]
                    scores[joint] = raw_quality[joint]
                    provenance[joint] = "MEASURED_RTMW"
            identifier = (
                f"H1_RTMW_{selected_chains[0].upper()}"
                if chain_count == 1
                else "H2_CHAIN_FUSION_" + "+".join(
                    chain_name.upper() for chain_name in selected_chains
                )
            )
            candidates.append((identifier, points, scores, provenance))
    temporal_points = base.render_points.copy(); temporal_scores = base.render_scores.copy()
    temporal_provenance = [_source_name(source) for source in base.sources]
    temporal_changed = False
    for joint in sorted({joint for chain in BODY_CHAINS.values() for joint in chain[1:]}):
        point = _neighbor_consensus(frames, index, joint)
        if point is not None and (
            temporal_scores[joint] <= 0.0
            or not np.isfinite(temporal_points[joint]).all()
            or np.linalg.norm(temporal_points[joint] - point) > body_scale * 0.12
        ):
            temporal_points[joint] = point
            temporal_scores[joint] = max(0.28, min(0.72, float(base.render_scores[joint])))
            temporal_provenance[joint] = "TEMPORAL_FUSED"
            temporal_changed = True
    if temporal_changed:
        candidates.append(("H4_GLOBAL_TEMPORAL", temporal_points, temporal_scores, temporal_provenance))
    distance_field = (
        signed_distance_field(silhouette.mask)
        if silhouette.valid and silhouette.mask is not None
        else None
    )
    if silhouette.valid and silhouette.mask is not None and distance_field is not None:
        mask_points = base.render_points.copy(); mask_scores = base.render_scores.copy()
        mask_provenance = [_source_name(source) for source in base.sources]
        changed = False
        for chain in BODY_CHAINS.values():
            for position, joint in enumerate(chain[1:], start=1):
                if joint >= len(mask_scores) or mask_scores[joint] <= 0.0 or not np.isfinite(mask_points[joint]).all():
                    continue
                if _distance_at(distance_field, mask_points[joint]) < -body_scale * 0.10:
                    parent = chain[position - 1]
                    replacement = _nearest_contour_point(silhouette, mask_points[joint], mask_points[parent])
                    if replacement is not None:
                        mask_points[joint] = replacement
                        mask_scores[joint] = min(float(mask_scores[joint]), 0.48)
                        mask_provenance[joint] = "MASK_CONSTRAINED"
                        changed = True
        if changed:
            candidates.append(("H5_MASK_SUPPORTED_RECONSTRUCTION", mask_points, mask_scores, mask_provenance))
    hypotheses = [
        _score_hypothesis(
            identifier, points, scores, provenance, base,
            silhouette=silhouette, body_scale=body_scale,
            body_joint_count=body_joint_count,
            distance_field=distance_field,
        )
        for identifier, points, scores, provenance in candidates
    ]
    if not any(item.valid for item in hypotheses):
        # The existing immutable V6.7 state remains the safe fallback.
        fallback = hypotheses[0]
        hypotheses[0] = replace(fallback, hard_rejection_reasons=(), full_body_score=0.01)
    return tuple(hypotheses)


def _score_hypothesis(
    identifier: str,
    points: np.ndarray,
    scores: np.ndarray,
    provenance: Sequence[str],
    base: TemporalFrame,
    *,
    silhouette: PersonSilhouetteFrame,
    body_scale: float,
    body_joint_count: int,
    distance_field: np.ndarray | None = None,
) -> FullBodyHypothesis:
    values = np.asarray(points, dtype=np.float32)
    quality = np.asarray(scores, dtype=np.float32)
    reasons: list[str] = []
    if values.ndim != 2 or values.shape[1] != 2 or quality.ndim != 1:
        reasons.append("COORDINATE_SPACE_MISMATCH")
    usable = quality[:body_joint_count] > 0.0
    if np.any(usable) and not np.isfinite(values[:body_joint_count][usable]).all():
        reasons.append("NON_FINITE_GEOMETRY")
    for joint in ROOT_JOINTS:
        if joint < len(quality) and base.render_scores[joint] > 0.0 and (
            quality[joint] <= 0.0 or np.linalg.norm(values[joint] - base.render_points[joint]) > 1e-3
        ):
            reasons.append("ROOT_STATE_MISMATCH")
            break
    bone_scores: list[float] = []
    for name, (first, second) in CORE_BONES.items():
        if any(joint >= len(quality) or quality[joint] <= 0.0 for joint in (first, second)):
            continue
        length = float(np.linalg.norm(values[second] - values[first]))
        expected_ratio = 0.175 if "arm" in name else 0.25
        ratio = length / max(1.0, body_scale * expected_ratio)
        bone_scores.append(float(math.exp(-abs(math.log(max(ratio, 1e-6))))))
        if ratio > 1.85 or ratio < 0.28:
            reasons.append(f"CATASTROPHIC_BONE_{name.upper()}")
    pose_evidence = float(np.mean(quality[:body_joint_count][usable])) if np.any(usable) else 0.0
    bone_consistency = float(np.mean(bone_scores)) if bone_scores else 0.0
    silhouette_agreement = _mask_alignment(
        values,
        quality,
        silhouette,
        body_scale,
        distance_field=distance_field,
    )
    topology = _topology_score(values, quality)
    coverage = float(np.mean(usable))
    components = {
        "pose_image_evidence": pose_evidence,
        "model_confidence": pose_evidence,
        "silhouette_agreement": silhouette_agreement,
        "bone_consistency": bone_consistency,
        "limb_topology": topology,
        "identity": silhouette.quality.mask_track_identity_confidence if silhouette.mask is not None else 0.5,
        "coverage": coverage,
    }
    score = float(np.clip(
        0.22 * pose_evidence
        + 0.20 * bone_consistency
        + 0.22 * silhouette_agreement
        + 0.16 * topology
        + 0.10 * components["identity"]
        + 0.10 * coverage,
        0.0,
        1.0,
    ))
    if reasons:
        score = 0.0
    return FullBodyHypothesis(
        identifier,
        values.copy(),
        quality.copy(),
        tuple(str(value) for value in provenance),
        score,
        components,
        tuple(sorted(set(reasons))),
    )


def _beam_sequence_solve(
    hypotheses: Sequence[Sequence[FullBodyHypothesis]],
    timestamps: Sequence[float],
    body_scales: Sequence[float],
    scene_cuts: Sequence[bool],
    silhouettes: Sequence[PersonSilhouetteFrame],
    *,
    beam_width: int,
) -> list[int]:
    beam: list[tuple[float, tuple[int, ...]]] = [(0.0, ())]
    for frame_index, frame_hypotheses in enumerate(hypotheses):
        expanded: list[tuple[float, tuple[int, ...]]] = []
        for cost, path in beam:
            for choice, candidate in enumerate(frame_hypotheses):
                if not candidate.valid:
                    continue
                transition = 0.0
                if path and not scene_cuts[frame_index]:
                    previous = hypotheses[frame_index - 1][path[-1]]
                    previous_previous = (
                        hypotheses[frame_index - 2][path[-2]]
                        if len(path) >= 2 and frame_index >= 2 and not scene_cuts[frame_index - 1]
                        else None
                    )
                    previous_previous_previous = (
                        hypotheses[frame_index - 3][path[-3]]
                        if len(path) >= 3
                        and frame_index >= 3
                        and not scene_cuts[frame_index - 2]
                        else None
                    )
                    transition = _transition_cost(
                        previous_previous_previous,
                        previous_previous,
                        previous,
                        candidate,
                        dt=max(1e-6, float(timestamps[frame_index]) - float(timestamps[frame_index - 1])),
                        body_scale=max(1.0, float(body_scales[frame_index])),
                        previous_silhouette=silhouettes[frame_index - 1],
                        current_silhouette=silhouettes[frame_index],
                    )
                emission = 1.0 - candidate.full_body_score
                expanded.append((cost + emission + transition, (*path, choice)))
        if not expanded:
            expanded = [(cost + 1.0, (*path, 0)) for cost, path in beam]
        expanded.sort(key=lambda item: item[0])
        beam = expanded[:max(1, beam_width)]
    return list(min(beam, key=lambda item: item[0])[1])


def _transition_cost(
    previous_previous_previous: FullBodyHypothesis | None,
    previous_previous: FullBodyHypothesis | None,
    previous: FullBodyHypothesis,
    current: FullBodyHypothesis,
    *,
    dt: float,
    body_scale: float,
    previous_silhouette: PersonSilhouetteFrame,
    current_silhouette: PersonSilhouetteFrame,
) -> float:
    count = min(len(previous.scores), len(current.scores), 23)
    valid = (previous.scores[:count] > 0.0) & (current.scores[:count] > 0.0)
    if not np.any(valid):
        return 0.45
    displacement = (current.points[:count][valid] - previous.points[:count][valid]) / body_scale
    velocity_cost = min(0.60, float(np.median(np.linalg.norm(displacement, axis=1))) / max(dt, 1 / 120) * 0.015)
    acceleration_cost = 0.0
    jerk_cost = 0.0
    if previous_previous is not None:
        prior_valid = valid & (previous_previous.scores[:count] > 0.0)
        if np.any(prior_valid):
            first = previous.points[:count][prior_valid] - previous_previous.points[:count][prior_valid]
            second = current.points[:count][prior_valid] - previous.points[:count][prior_valid]
            acceleration_cost = min(0.35, float(np.median(np.linalg.norm(second - first, axis=1))) / body_scale)
            if previous_previous_previous is not None:
                jerk_valid = prior_valid & (previous_previous_previous.scores[:count] > 0.0)
                if np.any(jerk_valid):
                    before = (
                        previous_previous.points[:count][jerk_valid]
                        - previous_previous_previous.points[:count][jerk_valid]
                    )
                    middle = (
                        previous.points[:count][jerk_valid]
                        - previous_previous.points[:count][jerk_valid]
                    )
                    after = (
                        current.points[:count][jerk_valid]
                        - previous.points[:count][jerk_valid]
                    )
                    jerk = (after - middle) - (middle - before)
                    jerk_cost = min(
                        0.30,
                        float(np.median(np.linalg.norm(jerk, axis=1))) / body_scale,
                    )
    root_cost = float(np.mean([
        np.linalg.norm(current.points[joint] - previous.points[joint]) / body_scale
        for joint in ROOT_JOINTS
        if joint < count and valid[joint]
    ])) if any(joint < count and valid[joint] for joint in ROOT_JOINTS) else 0.0
    bone_change_values: list[float] = []
    for first, second in CORE_BONES.values():
        if first >= count or second >= count or not (valid[first] and valid[second]):
            continue
        previous_length = float(np.linalg.norm(previous.points[second] - previous.points[first]))
        current_length = float(np.linalg.norm(current.points[second] - current.points[first]))
        bone_change_values.append(abs(current_length - previous_length) / body_scale)
    bone_length_cost = min(0.40, float(np.mean(bone_change_values))) if bone_change_values else 0.0
    side_identity_cost = _side_identity_transition_cost(previous, current, count)
    silhouette_movement_cost = _silhouette_transition_cost(
        previous,
        current,
        previous_silhouette,
        current_silhouette,
        body_scale,
    )
    provenance_count = min(
        len(previous.joint_provenance), len(current.joint_provenance), 23,
    )
    provenance_change_ratio = (
        sum(
            previous.joint_provenance[index] != current.joint_provenance[index]
            for index in range(provenance_count)
        ) / provenance_count
        if provenance_count
        else 0.0
    )
    switch_cost = 0.008 * provenance_change_ratio
    return (
        0.28 * velocity_cost
        + 0.16 * acceleration_cost
        + 0.08 * jerk_cost
        + 0.14 * min(root_cost, 0.5)
        + 0.12 * bone_length_cost
        + 0.10 * side_identity_cost
        + 0.12 * silhouette_movement_cost
        + switch_cost
    )


def _side_identity_transition_cost(
    previous: FullBodyHypothesis,
    current: FullBodyHypothesis,
    count: int,
) -> float:
    penalties: list[float] = []
    for left, right in ((5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)):
        if right >= count:
            continue
        if min(
            previous.scores[left], previous.scores[right],
            current.scores[left], current.scores[right],
        ) <= 0.0:
            continue
        previous_vector = previous.points[right] - previous.points[left]
        current_vector = current.points[right] - current.points[left]
        if float(np.dot(previous_vector, current_vector)) < 0.0:
            penalties.append(1.0)
    return float(np.mean(penalties)) if penalties else 0.0


def _silhouette_transition_cost(
    previous: FullBodyHypothesis,
    current: FullBodyHypothesis,
    previous_silhouette: PersonSilhouetteFrame,
    current_silhouette: PersonSilhouetteFrame,
    body_scale: float,
) -> float:
    if (
        not previous_silhouette.valid
        or not current_silhouette.valid
        or previous_silhouette.mask is None
        or current_silhouette.mask is None
        or previous_silhouette.mask.centroid is None
        or current_silhouette.mask.centroid is None
    ):
        return 0.0
    root_joints = [
        joint for joint in ROOT_JOINTS
        if joint < len(previous.scores)
        and joint < len(current.scores)
        and previous.scores[joint] > 0.0
        and current.scores[joint] > 0.0
    ]
    if not root_joints:
        return 0.0
    body_delta = np.mean([
        current.points[joint] - previous.points[joint] for joint in root_joints
    ], axis=0)
    mask_delta = (
        np.asarray(current_silhouette.mask.centroid, dtype=np.float32)
        - np.asarray(previous_silhouette.mask.centroid, dtype=np.float32)
    )
    return min(0.50, float(np.linalg.norm(body_delta - mask_delta)) / body_scale)


def _immutable_state(
    original: TemporalFrame,
    hypothesis: FullBodyHypothesis,
    *,
    repair_iteration: int,
) -> ImmutableFinalBodyState:
    analysis_points = hypothesis.points.copy(); analysis_scores = hypothesis.scores.copy()
    render_points = hypothesis.points.copy(); render_scores = hypothesis.scores.copy()
    analysis_usable = analysis_scores > 0.0
    ages = original.prediction_age_seconds.copy(); flow = original.flow_errors.copy()
    for values in (analysis_points, analysis_scores, render_points, render_scores, analysis_usable, ages, flow):
        values.setflags(write=False)
    sources = tuple(
        PointSource.MEASURED
        if source in {"MEASURED", "MEASURED_RTMW", "MEASURED_TAR"}
        else PointSource.INTERPOLATED
        if source == "TEMPORAL_FUSED"
        else PointSource.KINEMATIC_RECONSTRUCTED
        if source in {"MASK_CONSTRAINED", "GLOBAL_BODY_RECONSTRUCTED"}
        else original.sources[index]
        for index, source in enumerate(hypothesis.joint_provenance)
    )
    frame = replace(
        original,
        analysis_points=analysis_points,
        analysis_scores=analysis_scores,
        render_points=render_points,
        render_scores=render_scores,
        analysis_usable=analysis_usable,
        prediction_age_seconds=ages,
        flow_errors=flow,
        sources=sources,
    )
    reasons = (
        "sequence_level_full_body_selection",
        * (("worst_frame_deep_repair",) if repair_iteration else ()),
    )
    return ImmutableFinalBodyState(
        frame,
        hypothesis.hypothesis_id,
        hypothesis.full_body_score,
        hypothesis.joint_provenance,
        repair_iteration,
        tuple(reasons),
    )


def summarize_chain_specialists(
    states: Sequence[ImmutableFinalBodyState],
    silhouettes: Sequence[PersonSilhouetteFrame],
    body_scales: Sequence[float],
) -> dict[str, object]:
    chain_scores: dict[str, list[float]] = {name: [] for name in BODY_CHAINS}
    foot_scores: list[float] = []
    foot_contact_frames = 0
    foot_teleport_events = 0
    previous_frame: TemporalFrame | None = None
    for state, silhouette, scale in zip(states, silhouettes, body_scales):
        frame = state.frame
        distance = signed_distance_field(silhouette.mask) if silhouette.valid and silhouette.mask is not None else None
        for name, chain in BODY_CHAINS.items():
            valid = [joint for joint in chain if joint < len(frame.render_scores) and frame.render_scores[joint] > 0.0]
            if len(valid) < 3:
                continue
            mask_support = np.mean([
                1.0 if distance is None else float(_distance_at(distance, frame.render_points[joint]) >= -max(2.0, float(scale) * 0.08))
                for joint in valid
            ])
            chain_scores[name].append(float(mask_support))
            if "leg" in name:
                foot = [joint for joint in chain[2:] if joint in valid]
                if foot:
                    foot_scores.append(float(np.mean([
                        1.0 if distance is None else float(_distance_at(distance, frame.render_points[joint]) >= -max(2.0, float(scale) * 0.09))
                        for joint in foot
                    ])))
        if distance is not None:
            contact_joints = [
                joint for joint in (15, 16, 17, 18, 19, 20, 21, 22)
                if joint < len(frame.render_scores)
                and frame.render_scores[joint] > 0.0
                and _distance_at(distance, frame.render_points[joint]) >= -max(2.0, float(scale) * 0.06)
            ]
            if len(contact_joints) >= 2:
                foot_contact_frames += 1
        if previous_frame is not None:
            for hip, knee, ankle in ((11, 13, 15), (12, 14, 16)):
                if any(
                    joint >= len(frame.render_scores)
                    or joint >= len(previous_frame.render_scores)
                    or frame.render_scores[joint] <= 0.0
                    or previous_frame.render_scores[joint] <= 0.0
                    for joint in (hip, knee, ankle)
                ):
                    continue
                ankle_motion = float(np.linalg.norm(
                    frame.render_points[ankle] - previous_frame.render_points[ankle]
                )) / max(1.0, float(scale))
                proximal_motion = max(
                    float(np.linalg.norm(
                        frame.render_points[joint] - previous_frame.render_points[joint]
                    )) / max(1.0, float(scale))
                    for joint in (hip, knee)
                )
                if ankle_motion > 0.42 and proximal_motion < 0.12:
                    foot_teleport_events += 1
        previous_frame = frame
    return {
        "arm_chain_alignment_ratio": _mean([
            *chain_scores["left_arm"], *chain_scores["right_arm"],
        ]),
        "leg_chain_alignment_ratio": _mean([
            *chain_scores["left_leg"], *chain_scores["right_leg"],
        ]),
        "foot_chain_alignment_ratio": _mean(foot_scores),
        "foot_chain_quality_pass": foot_teleport_events == 0,
        "foot_contact_evidence_frame_count": foot_contact_frames,
        "foot_teleport_event_count": foot_teleport_events,
        "floor_contact_is_evidence_only": True,
        "arm_chain_quality_pass": bool(
            chain_scores["left_arm"] or chain_scores["right_arm"]
        ),
        "wrist_stabilized_before_hand_analysis": True,
    }


def estimate_ground_line(
    states: Sequence[ImmutableFinalBodyState],
    silhouettes: Sequence[PersonSilhouetteFrame],
    body_scales: Sequence[float],
) -> dict[str, object]:
    samples: list[float] = []
    for state, silhouette, scale in zip(states, silhouettes, body_scales):
        if silhouette.mask is None or not silhouette.mask.contour:
            continue
        foot_values = [
            float(state.frame.render_points[joint, 1])
            for joint in (15, 16, 17, 20)
            if joint < len(state.frame.render_scores)
            and state.frame.render_scores[joint] > 0.0
            and np.isfinite(state.frame.render_points[joint]).all()
        ]
        if not foot_values:
            continue
        mask_bottom = max(point[1] for point in silhouette.mask.contour)
        if abs(max(foot_values) - mask_bottom) <= max(3.0, float(scale) * 0.12):
            samples.append(float(mask_bottom))
    return {
        "available": len(samples) >= 3,
        "ground_y_pixels": round(float(np.median(samples)), 3) if len(samples) >= 3 else None,
        "support_frame_count": len(samples),
        "is_3d_calibration": False,
        "used_as_temporal_evidence_only": True,
    }


def _neighbor_consensus(
    frames: Sequence[TemporalFrame],
    index: int,
    joint: int,
) -> np.ndarray | None:
    before = next((
        candidate for candidate in range(index - 1, max(-1, index - 4), -1)
        if joint < len(frames[candidate].render_scores)
        and frames[candidate].render_scores[joint] > 0.0
        and np.isfinite(frames[candidate].render_points[joint]).all()
    ), None)
    after = next((
        candidate for candidate in range(index + 1, min(len(frames), index + 4))
        if joint < len(frames[candidate].render_scores)
        and frames[candidate].render_scores[joint] > 0.0
        and np.isfinite(frames[candidate].render_points[joint]).all()
    ), None)
    if before is not None and after is not None:
        return ((frames[before].render_points[joint] + frames[after].render_points[joint]) * 0.5).astype(np.float32)
    return None


def _mask_alignment(
    points: np.ndarray,
    scores: np.ndarray,
    silhouette: PersonSilhouetteFrame,
    body_scale: float,
    *,
    distance_field: np.ndarray | None = None,
) -> float:
    if not silhouette.valid or silhouette.mask is None:
        return 0.5
    distance = (
        distance_field
        if distance_field is not None
        else signed_distance_field(silhouette.mask)
    )
    support: list[float] = []
    for joint in range(min(len(scores), 23)):
        if scores[joint] <= 0.0 or not np.isfinite(points[joint]).all():
            continue
        value = _distance_at(distance, points[joint])
        tolerance = max(2.0, body_scale * (0.09 if joint not in ROOT_JOINTS else 0.05))
        support.append(float(np.clip(1.0 + min(0.0, value) / tolerance, 0.0, 1.0)))
    bone_support: list[float] = []
    for first, second in CORE_BONES.values():
        if scores[first] <= 0.0 or scores[second] <= 0.0:
            continue
        samples = points[first][None, :] + (points[second] - points[first])[None, :] * np.linspace(0.0, 1.0, 21)[:, None]
        bone_support.append(float(np.mean([
            _distance_at(distance, sample) >= -max(2.0, body_scale * 0.08) for sample in samples
        ])))
    values = [*support, *bone_support]
    return float(np.mean(values)) if values else 0.0


def _topology_score(points: np.ndarray, scores: np.ndarray) -> float:
    penalties = 0.0
    for left, right in ((5, 6), (11, 12), (7, 8), (13, 14)):
        if left < len(scores) and right < len(scores) and scores[left] > 0.0 and scores[right] > 0.0:
            if points[left, 0] > points[right, 0] + abs(points[right, 0] - points[left, 0]) * 2.0:
                penalties += 0.2
    return float(np.clip(1.0 - penalties, 0.0, 1.0))


def _nearest_contour_point(
    silhouette: PersonSilhouetteFrame,
    point: np.ndarray,
    parent: np.ndarray,
) -> np.ndarray | None:
    if silhouette.mask is None or not silhouette.mask.contour:
        return None
    contour = np.asarray(silhouette.mask.contour, dtype=np.float32)
    distances = np.linalg.norm(contour - np.asarray(point, dtype=np.float32), axis=1)
    nearest = contour[int(np.argmin(distances))]
    # Nudge towards the parent so the result is just inside the silhouette.
    direction = np.asarray(parent, dtype=np.float32) - nearest
    length = float(np.linalg.norm(direction))
    if length > 1e-6:
        nearest = nearest + direction / length * 2.0
    return nearest.astype(np.float32)


def _distance_at(field: np.ndarray, point: np.ndarray) -> float:
    x = int(np.clip(round(float(point[0])), 0, field.shape[1] - 1))
    y = int(np.clip(round(float(point[1])), 0, field.shape[0] - 1))
    return float(field[y, x])


def _source_name(source: PointSource) -> str:
    return {
        PointSource.MEASURED: "MEASURED_RTMW",
        PointSource.REFINED_MEASUREMENT: "TEMPORAL_FUSED",
        PointSource.FLOW_TRACKED: "TRACK_SUPPORTED",
        PointSource.INTERPOLATED: "TEMPORAL_FUSED",
        PointSource.KINEMATIC_RECONSTRUCTED: "GLOBAL_BODY_RECONSTRUCTED",
        PointSource.KINEMATIC_PREDICTED: "GLOBAL_BODY_RECONSTRUCTED",
    }.get(source, source.value)


def _mean(values: Sequence[float]) -> float | None:
    return round(float(np.mean(values)), 6) if values else None


def _empty_summary() -> dict[str, object]:
    return {
        "version": "global-body-solver-v1",
        "enabled": True,
        "frame_count": 0,
        "full_body_geometry_valid_ratio": 0.0,
        "full_body_hypothesis_switch_count": 0,
        "catastrophic_body_geometry_count": 0,
        "worst_1_percent_body_quality": None,
    }


__all__ = [
    "BODY_CHAINS",
    "CORE_BONES",
    "FullBodyHypothesis",
    "GlobalBodySolveResult",
    "ImmutableFinalBodyState",
    "estimate_ground_line",
    "solve_global_body_sequence",
    "summarize_chain_specialists",
]
