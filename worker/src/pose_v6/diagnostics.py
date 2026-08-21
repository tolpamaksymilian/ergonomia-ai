"""Transparent temporal and render coverage diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

import numpy as np

from .motion_analysis import MotionState
from .temporal_reconstruction import PointSource, TemporalFrame


def summarize_temporal_frames(
    frames: Sequence[TemporalFrame],
    motion_states: Sequence[str],
    *,
    joint_names: Sequence[str],
    fps: float = 30.0,
) -> dict[str, object]:
    source_counts: Counter[str] = Counter()
    per_joint: dict[str, Counter[str]] = {name: Counter() for name in joint_names}
    measured = reconstructed = usable = possible = 0
    for frame in frames:
        for index, source in enumerate(frame.sources[: len(joint_names)]):
            possible += 1; source_counts[source.value] += 1; per_joint[joint_names[index]][source.value] += 1
            if source in {PointSource.MEASURED, PointSource.REFINED_MEASUREMENT}:
                measured += 1
            elif source in {PointSource.INTERPOLATED, PointSource.FLOW_TRACKED} and bool(frame.analysis_usable[index]):
                reconstructed += 1
            if bool(frame.analysis_usable[index]):
                usable += 1
    motion_counts = Counter(motion_states)
    episodes: list[dict[str, object]] = []
    index = 0
    while index < len(motion_states):
        state = motion_states[index]
        start = index
        while index + 1 < len(motion_states) and motion_states[index + 1] == state:
            index += 1
        if state in {MotionState.FAST_MOTION.value, MotionState.EXTREME_MOTION.value}:
            episodes.append({
                "state": state,
                "start_frame": start,
                "end_frame": index,
                "duration_seconds": round((index - start + 1) / max(fps, 1e-6), 6),
            })
        index += 1
    return {
        "measurement_coverage_ratio": round(measured / possible, 6) if possible else 0.0,
        "reconstructed_analysis_coverage_ratio": round(reconstructed / possible, 6) if possible else 0.0,
        "analysis_usable_coverage_ratio": round(usable / possible, 6) if possible else 0.0,
        "point_source_counts": dict(source_counts),
        "motion_state_counts": {
            state.value: motion_counts.get(state.value, 0) for state in MotionState
        },
        "per_joint_source_counts": {name: dict(counts) for name, counts in per_joint.items()},
        "motion_episodes": episodes,
    }


def rank_temporal_worst_frames(records: Sequence[Mapping[str, object]], *, limit: int = 20) -> list[dict[str, object]]:
    ranked: list[tuple[float, int, dict[str, object]]] = []
    for index, record in enumerate(records):
        miss = 1.0 if record.get("bbox_source") == "TRACK_PREDICTED" else 0.0
        motion = record.get("motion_v6")
        motion_score = 0.0
        if isinstance(motion, Mapping):
            state = motion.get("state")
            motion_score = 2.0 if state == MotionState.EXTREME_MOTION.value else 1.0 if state == MotionState.FAST_MOTION.value else 0.0
        identity = record.get("tracking_identity_score")
        uncertainty = 1.0 - float(identity) if isinstance(identity, (int, float)) else 1.0
        score = miss * 2.0 + motion_score + uncertainty
        ranked.append((score, index, {"frame_index": index, "score": round(score, 6), "detector_miss": bool(miss), "motion_state": motion.get("state") if isinstance(motion, Mapping) else None, "identity_uncertainty": round(uncertainty, 6)}))
    return [item[2] for item in sorted(ranked, key=lambda value: (-value[0], value[1]))[:limit]]
