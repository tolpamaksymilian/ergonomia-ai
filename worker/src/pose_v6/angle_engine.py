"""Angle Engine V2 diagnostics and conservative temporal glitch rejection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

import numpy as np

from .temporal_reconstruction import PointSource, TemporalFrame


ANGLE_DEPENDENCIES: dict[str, tuple[int, ...]] = {
    "trunk_inclination_deg": (5, 6, 11, 12),
    "neck_flexion_deg": (0, 5, 6, 11, 12),
    "left_upper_arm_elevation_deg": (5, 7, 6, 11, 12),
    "right_upper_arm_elevation_deg": (6, 8, 5, 11, 12),
    "left_elbow_flexion_deg": (5, 7, 9),
    "right_elbow_flexion_deg": (6, 8, 10),
    "left_forearm_inclination_deg": (7, 9),
    "right_forearm_inclination_deg": (8, 10),
    "left_wrist_flexion_deg": (7, 9),
    "right_wrist_flexion_deg": (8, 10),
}
_MEASURED = {PointSource.MEASURED, PointSource.REFINED_MEASUREMENT}
_RECONSTRUCTED = {
    PointSource.INTERPOLATED,
    PointSource.FLOW_TRACKED,
    PointSource.KINEMATIC_RECONSTRUCTED,
}


class AngleProvenance(StrEnum):
    MEASURED = "MEASURED"
    MIXED_RECONSTRUCTED = "MIXED_RECONSTRUCTED"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class AngleDiagnostic:
    value_degrees: float | None
    confidence: float
    source_quality: float
    analysis_usable: bool
    provenance: AngleProvenance
    temporal_outlier_corrected: bool = False
    temporal_stability: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "value_degrees": round(self.value_degrees, 6) if self.value_degrees is not None else None,
            "confidence": round(self.confidence, 6),
            "source_quality": round(self.source_quality, 6),
            "analysis_usable": self.analysis_usable,
            "provenance": self.provenance.value,
            "temporal_outlier_corrected": self.temporal_outlier_corrected,
            "temporal_stability": round(self.temporal_stability, 6),
        }


@dataclass(frozen=True)
class AngleEngineResult:
    metric_frames: list[dict[str, dict[str, object]]]
    diagnostics: list[dict[str, dict[str, object]]]
    summary: dict[str, object]


def stabilize_angle_sequence(
    metric_frames: Sequence[Mapping[str, Mapping[str, object]]],
    temporal_frames: Sequence[TemporalFrame],
    timestamps: Sequence[float],
    motion_states: Sequence[str],
) -> AngleEngineResult:
    """Reject isolated angle glitches while retaining sustained fast movement."""

    count = len(metric_frames)
    if not (count == len(temporal_frames) == len(timestamps) == len(motion_states)):
        raise ValueError("angle engine inputs must have equal lengths")
    output = [{name: dict(payload) for name, payload in frame.items()} for frame in metric_frames]
    corrected: set[tuple[int, str]] = set()
    for name in ANGLE_DEPENDENCIES:
        for index in range(1, count - 1):
            previous = _valid_value(output[index - 1].get(name))
            current = _valid_value(output[index].get(name))
            following = _valid_value(output[index + 1].get(name))
            if previous is None or current is None or following is None:
                continue
            span = max(1e-3, float(timestamps[index + 1]) - float(timestamps[index - 1]))
            neighbor_rate = abs(following - previous) / span
            fast_motion = str(motion_states[index]).upper() in {"FAST_MOTION", "EXTREME_MOTION"}
            stable_neighbor_limit = 150.0 if fast_motion else 90.0
            excursion = min(abs(current - previous), abs(current - following))
            outside = current < min(previous, following) or current > max(previous, following)
            # A true fast turn normally continues in one direction.  Only an
            # isolated excursion whose neighbours agree is reconstructed.
            if not (outside and excursion >= (42.0 if fast_motion else 30.0) and neighbor_rate <= stable_neighbor_limit):
                continue
            before_time = float(timestamps[index - 1]); after_time = float(timestamps[index + 1])
            ratio = 0.5 if after_time <= before_time else float(np.clip((float(timestamps[index]) - before_time) / (after_time - before_time), 0.0, 1.0))
            replacement = previous + (following - previous) * ratio
            payload = output[index][name]
            payload["value"] = round(float(np.clip(replacement, 0.0, 180.0)), 6)
            payload["quality"] = round(min(_quality(output[index - 1][name]), _quality(payload), _quality(output[index + 1][name])) * 0.72, 6)
            payload["temporal_reconstruction"] = "isolated_angle_outlier"
            corrected.add((index, name))

    diagnostics: list[dict[str, dict[str, object]]] = []
    usable = possible = 0
    stability_values: list[float] = []
    for frame_index, (metrics, temporal) in enumerate(zip(output, temporal_frames)):
        frame_diagnostics: dict[str, dict[str, object]] = {}
        for name, dependencies in ANGLE_DEPENDENCIES.items():
            possible += 1
            payload = metrics.get(name, {})
            value = _valid_value(payload)
            source_quality, provenance, source_usable = _source_contract(temporal, dependencies)
            analysis_usable = value is not None and source_usable
            if analysis_usable:
                usable += 1
            metric_quality = _quality(payload) if value is not None else 0.0
            temporal_stability = _temporal_angle_stability(output, frame_index, name, value, timestamps)
            confidence = min(metric_quality, source_quality) * (0.72 + 0.28 * temporal_stability) if analysis_usable else 0.0
            corrected_here = (frame_index, name) in corrected
            if corrected_here:
                provenance = AngleProvenance.MIXED_RECONSTRUCTED
                confidence *= 0.78
            frame_diagnostics[name] = AngleDiagnostic(
                value, confidence, source_quality, analysis_usable,
                provenance if analysis_usable else AngleProvenance.INSUFFICIENT,
                corrected_here,
                temporal_stability,
            ).to_dict()
            if analysis_usable:
                stability_values.append(temporal_stability)
        diagnostics.append(frame_diagnostics)
    summary = {
        "angle_engine_version": "angle-engine-v2.0",
        "angle_outlier_count": len(corrected),
        "angle_usable_coverage_ratio": round(usable / possible, 6) if possible else 0.0,
        "angles_evaluated_per_frame": len(ANGLE_DEPENDENCIES),
        "projection": "2d_video_plane",
        "full_3d_anatomical_angle_claimed": False,
        "angle_temporal_stability_score": round(float(np.mean(stability_values)), 6) if stability_values else 0.0,
        "confidence_contract": "minimum_metric_and_source_quality_times_temporal_stability",
    }
    return AngleEngineResult(output, diagnostics, summary)


def safe_vector_angle_degrees(first: np.ndarray, second: np.ndarray) -> float | None:
    """NaN-safe vector angle used by regression tests and future angle formulas."""

    a = np.asarray(first, dtype=float).reshape(-1); b = np.asarray(second, dtype=float).reshape(-1)
    if a.size != b.size or a.size == 0 or not np.isfinite(a).all() or not np.isfinite(b).all():
        return None
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 1e-8:
        return None
    cosine = float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))
    value = math.degrees(math.acos(cosine))
    return float(np.clip(value, 0.0, 180.0)) if math.isfinite(value) else None


def _source_contract(frame: TemporalFrame, dependencies: tuple[int, ...]) -> tuple[float, AngleProvenance, bool]:
    sources: list[PointSource] = []
    qualities: list[float] = []
    for index in dependencies:
        if index >= frame.analysis_scores.size or not bool(frame.analysis_usable[index]) or float(frame.analysis_scores[index]) <= 0.0:
            return 0.0, AngleProvenance.INSUFFICIENT, False
        source = frame.sources[index]
        if source not in _MEASURED | _RECONSTRUCTED:
            return 0.0, AngleProvenance.INSUFFICIENT, False
        sources.append(source); qualities.append(float(frame.analysis_scores[index]))
    provenance = AngleProvenance.MEASURED if all(source in _MEASURED for source in sources) else AngleProvenance.MIXED_RECONSTRUCTED
    return min(qualities, default=0.0), provenance, True


def _valid_value(payload: Mapping[str, object] | None) -> float | None:
    if not isinstance(payload, Mapping) or payload.get("valid") is not True:
        return None
    value = payload.get("value")
    return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None


def _quality(payload: Mapping[str, object]) -> float:
    value = payload.get("quality")
    return float(np.clip(value, 0.0, 1.0)) if isinstance(value, (int, float)) and math.isfinite(float(value)) else 0.0


def _temporal_angle_stability(
    frames: Sequence[Mapping[str, Mapping[str, object]]],
    index: int,
    name: str,
    value: float | None,
    timestamps: Sequence[float],
) -> float:
    if value is None:
        return 0.0
    rates: list[float] = []
    for neighbor in (index - 1, index + 1):
        if not 0 <= neighbor < len(frames):
            continue
        neighbor_value = _valid_value(frames[neighbor].get(name))
        delta = abs(float(timestamps[neighbor]) - float(timestamps[index]))
        if neighbor_value is not None and math.isfinite(delta) and delta > 1e-6:
            rates.append(abs(value - neighbor_value) / delta)
    if not rates:
        return 0.7
    return float(np.clip(1.0 - float(np.median(rates)) / 540.0, 0.0, 1.0))
