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
            "mean_cycle_seconds": None,
            "cycles_per_minute": None,
            "movement_range": None,
            "mean_absolute_rate_per_second": None,
            "valid_exposure_seconds": round(valid_duration, 6),
            "longest_valid_sequence_seconds": round(max(valid_sequence_durations, default=0.0), 6),
            "valid_sequence_count": len(valid_sequence_durations),
        }
    values = np.asarray([sample[1] for sample in samples], dtype=float)
    cycle_count = 0
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
        derivative = np.diff(values_segment)
        epsilon = max(1e-6, float(np.ptp(values_segment)) * 0.03)
        signs = np.sign(np.where(np.abs(derivative) >= epsilon, derivative, 0.0))
        turning_points: list[int] = []
        previous_sign = 0.0
        for index, sign in enumerate(signs, start=1):
            if sign == 0.0:
                continue
            if previous_sign and sign != previous_sign:
                turning_points.append(index - 1)
            previous_sign = sign
        cycle_count += (len(turning_points) + 1) // 2 if turning_points else 0
        cycle_durations.extend(
            float(times_segment[turning_points[index + 2]] - times_segment[turning_points[index]])
            for index in range(len(turning_points) - 2)
            if index % 2 == 0
            and times_segment[turning_points[index + 2]] > times_segment[turning_points[index]]
        )
    mean_rate = float(np.mean(rates)) if rates else None
    return {
        "cycle_count": cycle_count,
        "mean_cycle_seconds": (
            round(float(np.mean(cycle_durations)), 6) if cycle_durations else None
        ),
        "cycles_per_minute": (
            round(cycle_count / elapsed * 60.0, 6)
            if cycle_count > 0 and elapsed > 0.0
            else None
        ),
        "movement_range": round(float(np.ptp(values)), 6),
        "mean_absolute_rate_per_second": (
            round(mean_rate, 6) if mean_rate is not None else None
        ),
        "valid_exposure_seconds": round(valid_duration, 6),
        "longest_valid_sequence_seconds": round(max(valid_sequence_durations, default=0.0), 6),
        "valid_sequence_count": len(valid_sequence_durations),
    }


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
