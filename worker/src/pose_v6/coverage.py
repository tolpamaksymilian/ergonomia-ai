"""Layer-level analysis/timeline contract and coverage diagnostics for Pose V6."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

import numpy as np

from .temporal_reconstruction import PointSource, TemporalFrame


class TimelineState(StrEnum):
    MEASURED = "MEASURED"
    REFINED_MODEL = "REFINED_MODEL"
    TEMPORALLY_RECONSTRUCTED = "TEMPORALLY_RECONSTRUCTED"
    FLOW_TRACKED = "FLOW_TRACKED"
    KINEMATICALLY_INFERRED = "KINEMATICALLY_INFERRED"
    LOW_CONFIDENCE_BUT_USABLE = "LOW_CONFIDENCE_BUT_USABLE"
    NOT_VISIBLE = "NOT_VISIBLE"
    NO_DATA = "NO_DATA"


class UsabilityLevel(StrEnum):
    FULLY_USABLE = "fully_usable"
    USABLE_WITH_RECONSTRUCTION = "usable_with_reconstruction"
    TIMELINE_ONLY = "usable_for_timeline_only"
    INSUFFICIENT = "insufficient"


LAYER_JOINTS: dict[str, tuple[int, ...]] = {
    "torso": (5, 6, 11, 12),
    "neck": (0, 5, 6, 11, 12),
    "left_arm": (5, 7, 9),
    "right_arm": (6, 8, 10),
    "left_wrist": (7, 9),
    "right_wrist": (8, 10),
}

LAYER_BONES: dict[str, tuple[str, ...]] = {
    "torso": ("shoulders", "left_torso", "right_torso", "hips"),
    "neck": (),
    "left_arm": ("left_upper_arm", "left_forearm"),
    "right_arm": ("right_upper_arm", "right_forearm"),
    "left_wrist": ("left_forearm",),
    "right_wrist": ("right_forearm",),
}


def build_frame_layer_contract(
    frame: TemporalFrame,
    *,
    raw_scores: np.ndarray | None = None,
    rendered_bones: Mapping[str, Any] | None = None,
    left_hand_visible: bool = False,
    left_hand_quality: float = 0.0,
    right_hand_visible: bool = False,
    right_hand_quality: float = 0.0,
    tracking_state: str = "",
) -> dict[str, dict[str, object]]:
    """Describe each layer without converting visual continuity into measurement."""

    output = {
        name: _body_layer(
            frame,
            joints,
            LAYER_BONES[name],
            raw_scores=raw_scores,
            rendered_bones=rendered_bones,
            tracking_state=tracking_state,
        )
        for name, joints in LAYER_JOINTS.items()
    }
    output["left_hand"] = _hand_layer(left_hand_visible, left_hand_quality)
    output["right_hand"] = _hand_layer(right_hand_visible, right_hand_quality)
    return output


def summarize_layer_coverage(
    frames: Sequence[Mapping[str, Mapping[str, object]]],
    *,
    fps: float,
    long_gap_seconds: float = 0.5,
) -> dict[str, object]:
    names = tuple((*LAYER_JOINTS.keys(), "left_hand", "right_hand"))
    total = len(frames)
    layers: dict[str, dict[str, object]] = {}
    for name in names:
        states = [str(frame.get(name, {}).get("state", TimelineState.NO_DATA.value)) for frame in frames]
        usability = [str(frame.get(name, {}).get("usability", UsabilityLevel.INSUFFICIENT.value)) for frame in frames]
        analysis_flags = [value in {UsabilityLevel.FULLY_USABLE.value, UsabilityLevel.USABLE_WITH_RECONSTRUCTION.value} for value in usability]
        timeline_flags = [value != UsabilityLevel.INSUFFICIENT.value for value in usability]
        measured_flags = [value in {TimelineState.MEASURED.value, TimelineState.REFINED_MODEL.value} for value in states]
        refined_flags = [value == TimelineState.REFINED_MODEL.value for value in states]
        reconstructed_flags = [value in {TimelineState.TEMPORALLY_RECONSTRUCTED.value, TimelineState.FLOW_TRACKED.value} for value in states]
        inferred_flags = [value in {TimelineState.KINEMATICALLY_INFERRED.value, TimelineState.LOW_CONFIDENCE_BUT_USABLE.value} for value in states]
        gaps = _gap_lengths(timeline_flags)
        layers[name] = {
            "analysis_coverage_ratio": _ratio(sum(analysis_flags), total),
            "timeline_coverage_ratio": _ratio(sum(timeline_flags), total),
            "measured_ratio": _ratio(sum(measured_flags), total),
            "analysis_coverage_gain_vs_measured": round(
                _ratio(sum(analysis_flags), total) - _ratio(sum(measured_flags), total), 6
            ),
            "timeline_coverage_gain_vs_measured": round(
                _ratio(sum(timeline_flags), total) - _ratio(sum(measured_flags), total), 6
            ),
            "refined_model_ratio": _ratio(sum(refined_flags), total),
            "reconstructed_ratio": _ratio(sum(reconstructed_flags), total),
            "inferred_ratio": _ratio(sum(inferred_flags), total),
            "gray_timeline_ratio": _ratio(total - sum(timeline_flags), total),
            "state_counts": dict(Counter(states)),
            "single_frame_dropout_count": sum(length == 1 for length in gaps),
            "long_gap_count": sum(length / max(fps, 1e-6) >= long_gap_seconds for length in gaps),
            "maximum_gap_frames": max(gaps, default=0),
            "maximum_gap_seconds": round(max(gaps, default=0) / max(fps, 1e-6), 6),
        }

    assessment_flags = []
    for frame in frames:
        usable = lambda layer: str(frame.get(layer, {}).get("usability", "")) in {
            UsabilityLevel.FULLY_USABLE.value,
            UsabilityLevel.USABLE_WITH_RECONSTRUCTION.value,
        }
        assessment_flags.append(
            usable("torso")
            and usable("neck")
            and (
                usable("left_arm") and usable("left_wrist") and usable("left_hand")
                or usable("right_arm") and usable("right_wrist") and usable("right_hand")
            )
        )
    assessment_gaps = _gap_lengths(assessment_flags)
    flat_coverage = {
        key: value
        for name in names
        for key, value in (
            (f"{name}_analysis_coverage_ratio", layers[name]["analysis_coverage_ratio"]),
            (f"{name}_timeline_coverage_ratio", layers[name]["timeline_coverage_ratio"]),
        )
    }
    return {
        "contract_version": "pose-timeline-coverage-v1",
        "frame_count": total,
        "layers": layers,
        **flat_coverage,
        "analysis_coverage_ratios": {
            name: layers[name]["analysis_coverage_ratio"] for name in names
        },
        "timeline_coverage_ratios": {
            name: layers[name]["timeline_coverage_ratio"] for name in names
        },
        "measured_ratio_per_layer": {
            name: layers[name]["measured_ratio"] for name in names
        },
        "reconstructed_ratio_per_layer": {
            name: layers[name]["reconstructed_ratio"] for name in names
        },
        "inferred_ratio_per_layer": {
            name: layers[name]["inferred_ratio"] for name in names
        },
        "single_frame_dropout_count_per_layer": {
            name: layers[name]["single_frame_dropout_count"] for name in names
        },
        "long_gap_count_per_layer": {
            name: layers[name]["long_gap_count"] for name in names
        },
        "maximum_gap_seconds_per_layer": {
            name: layers[name]["maximum_gap_seconds"] for name in names
        },
        "gray_ratio_per_layer": {
            name: layers[name]["gray_timeline_ratio"] for name in names
        },
        "rula_reba_timeline_coverage_ratio": _ratio(sum(assessment_flags), total),
        "rula_reba_longest_gap_frames": max(assessment_gaps, default=0),
        "rula_reba_longest_gap_seconds": round(max(assessment_gaps, default=0) / max(fps, 1e-6), 6),
        "assessment_coverage_definition": "technical_geometry_eligibility_not_completed_normative_score",
    }


def coalesce_short_timeline_gaps(
    frames: Sequence[Mapping[str, Mapping[str, object]]],
    *,
    maximum_gap_frames: int = 1,
) -> list[dict[str, dict[str, object]]]:
    """Bridge short body-layer display gaps while retaining explicit provenance.

    This changes timeline usability only. It never marks the bridged sample as
    analytically usable and never bridges an explicitly NOT_VISIBLE interval.
    """

    if maximum_gap_frames < 0:
        raise ValueError("maximum_gap_frames cannot be negative")
    output = [
        {layer: dict(contract) for layer, contract in frame.items()}
        for frame in frames
    ]
    for layer in LAYER_JOINTS:
        index = 1
        while index < len(output) - 1:
            contract = output[index].get(layer, {})
            if contract.get("usability") != UsabilityLevel.INSUFFICIENT.value:
                index += 1
                continue
            start = index
            while index < len(output) and output[index].get(layer, {}).get("usability") == UsabilityLevel.INSUFFICIENT.value:
                index += 1
            end = index
            if (
                end - start <= maximum_gap_frames
                and start > 0
                and end < len(output)
                and all(output[item].get(layer, {}).get("state") != TimelineState.NOT_VISIBLE.value for item in range(start, end))
                and output[start - 1].get(layer, {}).get("timeline_usable") is True
                and output[end].get(layer, {}).get("timeline_usable") is True
            ):
                for item in range(start, end):
                    previous_state = output[item][layer].get("state", TimelineState.NO_DATA.value)
                    output[item][layer].update({
                        "state": TimelineState.TEMPORALLY_RECONSTRUCTED.value,
                        "usability": UsabilityLevel.TIMELINE_ONLY.value,
                        "analysis_usable": False,
                        "timeline_usable": True,
                        "coalesced_from_state": previous_state,
                    })
    return output


def _body_layer(
    frame: TemporalFrame,
    joints: tuple[int, ...],
    bones: tuple[str, ...],
    *,
    raw_scores: np.ndarray | None,
    rendered_bones: Mapping[str, Any] | None,
    tracking_state: str,
) -> dict[str, object]:
    sources = [frame.sources[index] for index in joints]
    analysis_usable = all(bool(frame.analysis_usable[index]) for index in joints)
    quality = min((float(frame.render_scores[index]) for index in joints), default=0.0)
    if analysis_usable:
        state = _dominant_state(sources)
        reconstructed = any(source in {PointSource.INTERPOLATED, PointSource.FLOW_TRACKED} for source in sources)
        usability = UsabilityLevel.USABLE_WITH_RECONSTRUCTION if reconstructed else UsabilityLevel.FULLY_USABLE
    elif _bones_visible(rendered_bones, bones):
        state = (
            TimelineState.KINEMATICALLY_INFERRED
            if any(source == PointSource.KINEMATIC_PREDICTED for source in sources)
            else TimelineState.LOW_CONFIDENCE_BUT_USABLE
        )
        usability = UsabilityLevel.TIMELINE_ONLY
        quality = _bone_quality(rendered_bones, bones)
    elif tracking_state.upper() in {"LOST", "OUT_OF_FRAME", "OCCLUDED"}:
        state = TimelineState.NOT_VISIBLE
        usability = UsabilityLevel.INSUFFICIENT
    else:
        state = TimelineState.NO_DATA
        usability = UsabilityLevel.INSUFFICIENT
    return {
        "state": state.value,
        "usability": usability.value,
        "analysis_usable": usability in {UsabilityLevel.FULLY_USABLE, UsabilityLevel.USABLE_WITH_RECONSTRUCTION},
        "timeline_usable": usability != UsabilityLevel.INSUFFICIENT,
        "quality": round(max(0.0, min(1.0, quality)), 6),
    }


def _hand_layer(visible: bool, quality: float) -> dict[str, object]:
    safe_quality = max(0.0, min(1.0, float(quality)))
    return {
        "state": (TimelineState.MEASURED if visible else TimelineState.NOT_VISIBLE).value,
        "usability": (UsabilityLevel.FULLY_USABLE if visible else UsabilityLevel.INSUFFICIENT).value,
        "analysis_usable": visible,
        "timeline_usable": visible,
        "quality": round(safe_quality if visible else 0.0, 6),
    }


def _dominant_state(sources: Sequence[PointSource]) -> TimelineState:
    if PointSource.FLOW_TRACKED in sources:
        return TimelineState.FLOW_TRACKED
    if PointSource.INTERPOLATED in sources:
        return TimelineState.TEMPORALLY_RECONSTRUCTED
    if PointSource.REFINED_MEASUREMENT in sources:
        return TimelineState.REFINED_MODEL
    return TimelineState.MEASURED


def _bones_visible(rendered: Mapping[str, Any] | None, names: tuple[str, ...]) -> bool:
    if not rendered or not names:
        return False
    def visible(value: Any) -> bool:
        if isinstance(value, Mapping):
            return value.get("visible") is True
        return getattr(value, "visible", False) is True

    return all(name in rendered and visible(rendered[name]) for name in names)


def _bone_quality(rendered: Mapping[str, Any] | None, names: tuple[str, ...]) -> float:
    if not rendered or not names:
        return 0.0
    values: list[float] = []
    for name in names:
        value = rendered.get(name)
        raw = value.get("confidence") if isinstance(value, Mapping) else getattr(value, "confidence", 0.0)
        if isinstance(raw, (int, float)) and np.isfinite(float(raw)):
            values.append(float(raw))
    return min(values) if values else 0.0


def _gap_lengths(flags: Sequence[bool]) -> list[int]:
    gaps: list[int] = []
    length = 0
    for flag in (*flags, True):
        if not flag:
            length += 1
        elif length:
            gaps.append(length)
            length = 0
    return gaps


def _ratio(value: int, total: int) -> float:
    return round(value / total, 6) if total else 0.0
