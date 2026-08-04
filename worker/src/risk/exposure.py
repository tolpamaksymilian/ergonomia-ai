"""Frame timing and exposure calculations for Risk Engine V1."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Sequence

from .schemas import BandLevel, RISK_LEVELS, RISK_SEVERITY


@dataclass(frozen=True)
class TimingInfo:
    durations_seconds: tuple[float, ...]
    timeline_seconds: tuple[float | None, ...]
    method: str
    fallback_used: bool
    fallback_reason: str | None


def resolve_frame_timing(
    frames: Sequence[dict[str, Any]],
    fps: float | None = None,
) -> TimingInfo:
    """Prefer strictly increasing timestamps and otherwise fall back to FPS."""

    timestamps = tuple(_timestamp(frame) for frame in frames)
    if _timestamps_are_usable(timestamps):
        values = tuple(float(value) for value in timestamps if value is not None)
        differences = tuple(
            current - previous for previous, current in zip(values, values[1:])
        )
        representative = statistics.median(differences)
        durations = differences + (representative,)
        return TimingInfo(
            durations_seconds=durations,
            timeline_seconds=tuple(values),
            method="timestamps",
            fallback_used=False,
            fallback_reason=None,
        )

    if fps is not None and math.isfinite(fps) and fps > 0:
        frame_duration = 1.0 / fps
        timeline = tuple(index * frame_duration for index in range(len(frames)))
        return TimingInfo(
            durations_seconds=tuple(frame_duration for _ in frames),
            timeline_seconds=timeline,
            method="fps_fallback",
            fallback_used=True,
            fallback_reason="invalid_or_missing_timestamps",
        )

    return TimingInfo(
        durations_seconds=tuple(0.0 for _ in frames),
        timeline_seconds=tuple(None for _ in frames),
        method="unavailable",
        fallback_used=True,
        fallback_reason="timestamps_and_fps_unavailable",
    )


def calculate_exposure(
    levels: Sequence[str],
    valid_flags: Sequence[bool],
    timing: TimingInfo,
) -> dict[str, float | str | bool | None]:
    if len(levels) != len(valid_flags) or len(levels) != len(
        timing.durations_seconds
    ):
        raise ValueError("Levels, valid flags and frame durations must have equal length.")

    total_valid = sum(
        duration
        for valid, duration in zip(valid_flags, timing.durations_seconds)
        if valid
    )
    durations = {
        level: sum(
            duration
            for frame_level, valid, duration in zip(
                levels,
                valid_flags,
                timing.durations_seconds,
            )
            if valid and frame_level == level
        )
        for level in RISK_LEVELS
    }
    longest = {
        level: longest_sequence_seconds(levels, valid_flags, timing, level)
        for level in ("moderate", "high", "critical")
    }

    result: dict[str, float | str | bool | None] = {
        "total_valid_duration_seconds": _rounded(total_valid),
        "timing_method": timing.method,
        "timing_fallback_used": timing.fallback_used,
        "timing_fallback_reason": timing.fallback_reason,
    }
    for level in RISK_LEVELS:
        result[f"{level}_duration_seconds"] = _rounded(durations[level])
        if level != "low":
            result[f"longest_{level}_sequence_seconds"] = _rounded(
                longest[level]
            )
        if level != "low":
            ratio = durations[level] / total_valid if total_valid > 0 else 0.0
            result[f"{level}_exposure_ratio"] = _rounded(ratio)
    return result


def cumulative_exposure_ratio(
    levels: Sequence[str],
    valid_flags: Sequence[bool],
    timing: TimingInfo,
    minimum_level: BandLevel,
) -> float:
    total_valid = sum(
        duration
        for valid, duration in zip(valid_flags, timing.durations_seconds)
        if valid
    )
    if total_valid <= 0:
        return 0.0
    minimum_severity = RISK_SEVERITY[minimum_level]
    duration = sum(
        frame_duration
        for level, valid, frame_duration in zip(
            levels,
            valid_flags,
            timing.durations_seconds,
        )
        if valid and RISK_SEVERITY.get(level, -1) >= minimum_severity
    )
    return min(1.0, max(0.0, duration / total_valid))


def longest_sequence_seconds(
    levels: Sequence[str],
    valid_flags: Sequence[bool],
    timing: TimingInfo,
    minimum_level: BandLevel,
    *,
    exact: bool = True,
) -> float:
    minimum_severity = RISK_SEVERITY[minimum_level]
    longest = 0.0
    current = 0.0
    for level, valid, duration in zip(
        levels,
        valid_flags,
        timing.durations_seconds,
    ):
        severity = RISK_SEVERITY.get(level, -1)
        matches = valid and (
            level == minimum_level if exact else severity >= minimum_severity
        )
        if matches:
            current += duration
            longest = max(longest, current)
        else:
            current = 0.0
    return longest


def _timestamp(frame: dict[str, Any]) -> float | None:
    for field in (
        "timestamp",
        "output_timestamp_seconds",
        "source_timestamp_seconds",
    ):
        value = frame.get(field)
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        ):
            return float(value)
    return None


def _timestamps_are_usable(values: Sequence[float | None]) -> bool:
    if len(values) < 2 or any(value is None for value in values):
        return False
    concrete = [float(value) for value in values if value is not None]
    return all(current > previous for previous, current in zip(concrete, concrete[1:]))


def _rounded(value: float) -> float:
    return round(value, 6)
