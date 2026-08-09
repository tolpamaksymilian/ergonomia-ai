"""Metric-specific isolated-spike validation and movement features."""

from __future__ import annotations

import math

import numpy as np

from .schemas import MetricResult


METRIC_MAXIMUM_RATE_PER_SECOND: dict[str, float] = {
    "trunk_inclination_deg": 120.0,
    "neck_flexion_deg": 180.0,
    "left_upper_arm_elevation_deg": 240.0,
    "right_upper_arm_elevation_deg": 240.0,
    "left_elbow_flexion_deg": 320.0,
    "right_elbow_flexion_deg": 320.0,
    "left_forearm_inclination_deg": 360.0,
    "right_forearm_inclination_deg": 360.0,
    "left_wrist_flexion_deg": 480.0,
    "right_wrist_flexion_deg": 480.0,
    "left_hand_closure_ratio": 4.0,
    "right_hand_closure_ratio": 4.0,
    "left_pinch_distance_ratio": 5.0,
    "right_pinch_distance_ratio": 5.0,
}


def reject_isolated_metric_spikes(
    metric_name: str,
    results: list[MetricResult],
    timestamps: list[float | None],
) -> list[MetricResult]:
    if len(results) < 3 or len(results) != len(timestamps):
        return list(results)
    maximum_rate = METRIC_MAXIMUM_RATE_PER_SECOND[metric_name]
    output = list(results)
    for index in range(1, len(results) - 1):
        previous, current, following = results[index - 1 : index + 2]
        time_previous, time_current, time_following = timestamps[index - 1 : index + 2]
        if not all(item.valid and item.value is not None for item in (previous, current, following)):
            continue
        if None in {time_previous, time_current, time_following}:
            continue
        first_delta = float(time_current) - float(time_previous)  # type: ignore[arg-type]
        second_delta = float(time_following) - float(time_current)  # type: ignore[arg-type]
        if first_delta <= 0.0 or second_delta <= 0.0:
            continue
        first_rate = abs(float(current.value) - float(previous.value)) / first_delta
        second_rate = abs(float(following.value) - float(current.value)) / second_delta
        neighbor_rate = abs(float(following.value) - float(previous.value)) / (first_delta + second_delta)
        if first_rate > maximum_rate and second_rate > maximum_rate and neighbor_rate <= maximum_rate * 0.35:
            output[index] = MetricResult.rejected(current.source_points, "temporal_outlier")
    return output


def movement_features(
    results: list[MetricResult],
    timestamps: list[float | None],
) -> dict[str, int | float | None]:
    durations = frame_durations(timestamps)
    valid_flags = [
        bool(result.valid and result.value is not None and timestamp is not None)
        for result, timestamp in zip(results, timestamps)
    ]
    valid_duration = sum(
        duration for duration, valid in zip(durations, valid_flags) if valid
    )
    valid_sequence_durations: list[float] = []
    current_duration = 0.0
    for valid, duration in zip(valid_flags, durations):
        if valid:
            current_duration += duration
        elif current_duration > 0.0:
            valid_sequence_durations.append(current_duration)
            current_duration = 0.0
    if current_duration > 0.0:
        valid_sequence_durations.append(current_duration)

    sample_segments: list[list[tuple[float, float]]] = []
    current_segment: list[tuple[float, float]] = []
    for result, timestamp in zip(results, timestamps):
        sample_valid = (
            result.valid
            and result.value is not None
            and timestamp is not None
            and math.isfinite(float(timestamp))
        )
        if not sample_valid:
            if current_segment:
                sample_segments.append(current_segment)
                current_segment = []
            continue
        sample = (float(timestamp), float(result.value))
        if current_segment and sample[0] <= current_segment[-1][0]:
            sample_segments.append(current_segment)
            current_segment = []
        current_segment.append(sample)
    if current_segment:
        sample_segments.append(current_segment)
    samples = [sample for segment in sample_segments for sample in segment]
    if len(samples) < 3:
        return {
            "cycle_count": 0,
            "reversal_count": 0,
            "mean_cycle_seconds": None,
            "cycles_per_minute": None,
            "movement_range": None,
            "range_of_motion": None,
            "mean_absolute_rate_per_second": None,
            "median_absolute_velocity": None,
            "percentile_95_absolute_velocity": None,
            "peak_absolute_velocity": None,
            "longest_stable_posture_seconds": None,
            "valid_exposure_seconds": round(valid_duration, 6),
            "longest_valid_sequence_seconds": round(max(valid_sequence_durations, default=0.0), 6),
            "valid_sequence_count": len(valid_sequence_durations),
        }
    values = np.asarray([sample[1] for sample in samples], dtype=float)
    cycle_count = 0
    reversal_count = 0
    cycle_durations: list[float] = []
    rates: list[float] = []
    elapsed = 0.0
    for segment in sample_segments:
        if len(segment) < 2:
            continue
        times_segment = np.asarray([sample[0] for sample in segment], dtype=float)
        values_segment = np.asarray([sample[1] for sample in segment], dtype=float)
        deltas = np.diff(times_segment)
        rates.extend(
            (np.abs(np.diff(values_segment)) / deltas).astype(float).tolist()
        )
        elapsed += float(times_segment[-1] - times_segment[0])
        if len(segment) < 3:
            continue
        turning_points = _prominent_turning_points(times_segment, values_segment)
        reversal_count += len(turning_points)
        cycle_count += (len(turning_points) + 1) // 2 if turning_points else 0
        cycle_durations.extend(
            float(times_segment[turning_points[index + 2]] - times_segment[turning_points[index]])
            for index in range(len(turning_points) - 2)
            if index % 2 == 0
            and times_segment[turning_points[index + 2]] > times_segment[turning_points[index]]
        )
    mean_rate = float(np.mean(rates)) if rates else None
    rate_values = np.asarray(rates, dtype=float)
    stable_seconds = _longest_stable_duration(sample_segments, rate_values)
    movement_range = float(np.ptp(values))
    return {
        "cycle_count": cycle_count,
        "reversal_count": reversal_count,
        "mean_cycle_seconds": (
            round(float(np.mean(cycle_durations)), 6) if cycle_durations else None
        ),
        "cycles_per_minute": (
            round(cycle_count / elapsed * 60.0, 6)
            if cycle_count > 0 and elapsed > 0.0
            else None
        ),
        "movement_range": round(movement_range, 6),
        "range_of_motion": round(movement_range, 6),
        "mean_absolute_rate_per_second": (
            round(mean_rate, 6) if mean_rate is not None else None
        ),
        "median_absolute_velocity": (
            round(float(np.median(rate_values)), 6) if rate_values.size else None
        ),
        "percentile_95_absolute_velocity": (
            round(float(np.percentile(rate_values, 95)), 6)
            if rate_values.size
            else None
        ),
        "peak_absolute_velocity": (
            round(float(np.max(rate_values)), 6) if rate_values.size else None
        ),
        "longest_stable_posture_seconds": (
            round(stable_seconds, 6) if stable_seconds is not None else None
        ),
        "valid_exposure_seconds": round(valid_duration, 6),
        "longest_valid_sequence_seconds": round(max(valid_sequence_durations, default=0.0), 6),
        "valid_sequence_count": len(valid_sequence_durations),
    }


def _prominent_turning_points(
    times: np.ndarray,
    values: np.ndarray,
) -> list[int]:
    """Return alternating peaks/valleys with data-scaled prominence and time."""

    if values.size < 3:
        return []
    span = float(np.ptp(values))
    prominence = max(1e-6, span * 0.08)
    raw = [
        index
        for index in range(1, values.size - 1)
        if (
            (values[index] > values[index - 1] and values[index] >= values[index + 1])
            or (values[index] < values[index - 1] and values[index] <= values[index + 1])
        )
    ]
    accepted: list[int] = []
    for index in raw:
        local_prominence = min(
            abs(float(values[index] - values[index - 1])),
            abs(float(values[index] - values[index + 1])),
        )
        if local_prominence < prominence:
            continue
        if accepted and float(times[index] - times[accepted[-1]]) < 0.15:
            previous = accepted[-1]
            if abs(float(values[index] - np.median(values))) > abs(
                float(values[previous] - np.median(values))
            ):
                accepted[-1] = index
            continue
        accepted.append(index)
    return accepted


def _longest_stable_duration(
    segments: list[list[tuple[float, float]]],
    rates: np.ndarray,
) -> float | None:
    if rates.size == 0:
        return None
    # A data-adaptive motion plateau, not an ergonomic or normative threshold.
    threshold = float(np.percentile(rates, 35))
    longest = 0.0
    for segment in segments:
        start: float | None = None
        for previous, current in zip(segment, segment[1:]):
            delta = current[0] - previous[0]
            rate = abs(current[1] - previous[1]) / delta if delta > 1e-9 else math.inf
            if rate <= threshold + 1e-12:
                start = previous[0] if start is None else start
                longest = max(longest, current[0] - start)
            else:
                start = None
    return longest


def frame_durations(timestamps: list[float | None]) -> list[float]:
    if not timestamps:
        return []
    positive_deltas = [
        float(timestamps[index + 1]) - float(timestamps[index])
        for index in range(len(timestamps) - 1)
        if timestamps[index] is not None
        and timestamps[index + 1] is not None
        and float(timestamps[index + 1]) > float(timestamps[index])
    ]
    fallback = positive_deltas[-1] if positive_deltas else 0.0
    durations: list[float] = []
    for index, timestamp in enumerate(timestamps):
        if (
            timestamp is not None
            and index + 1 < len(timestamps)
            and timestamps[index + 1] is not None
        ):
            delta = float(timestamps[index + 1]) - float(timestamp)
            durations.append(delta if delta > 0.0 and math.isfinite(delta) else fallback)
        else:
            durations.append(fallback)
    return durations
