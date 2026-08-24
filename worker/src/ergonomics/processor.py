"""Pose V3 JSON parsing, frame processing, summaries, and file output."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import compute_frame_metrics
from .dependencies import METRIC_DEPENDENCIES
from .schemas import FramePose, METRIC_NAMES, MetricResult, PointSample, RejectionReason, ValidatedHand
from .temporal import frame_durations, movement_features, reject_isolated_metric_spikes


SUPPORTED_POSE_SCHEMAS = frozenset({"3.0", "3.1", "4.0", "5.0", "5.1", "6.0"})
DEFAULT_KEYPOINT_QUALITY_THRESHOLD = 0.78
RECONSTRUCTED_KEYPOINT_QUALITY_FLOOR = 0.35
ANALYTICAL_RECONSTRUCTION_SOURCES = frozenset({"INTERPOLATED", "FLOW_TRACKED"})
BODY_KEYPOINT_INDICES: dict[str, int] = {
    "nose": 0,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
}


class InputSchemaError(ValueError):
    rejection_reason: RejectionReason = "unsupported_input_schema"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _metadata_number(value: Any) -> int | float | None:
    numeric = _finite_number(value)
    if numeric is None:
        return None
    return int(numeric) if numeric.is_integer() else numeric


def _timestamp(value: Any) -> float | None:
    numeric = _finite_number(value)
    return float(numeric) if numeric is not None else None


def _parse_coordinates(value: Any) -> tuple[np.ndarray | None, RejectionReason | None]:
    if value is None:
        return None, "missing_keypoint"
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None, "invalid_coordinate"
    if value[0] is None or value[1] is None:
        return None, "missing_keypoint"
    first = _finite_number(value[0])
    second = _finite_number(value[1])
    if first is None or second is None:
        return None, "invalid_coordinate"
    if abs(first) <= 1e-8 and abs(second) <= 1e-8:
        return None, "invalid_coordinate"
    return np.asarray([first, second], dtype=float), None


def _body_point(
    name: str,
    index: int,
    keypoints: Any,
    scores: Any,
    threshold: float,
    diagnostic: Any = None,
    temporal_diagnostic: Any = None,
) -> PointSample:
    coordinate_value = keypoints[index] if isinstance(keypoints, list) and index < len(keypoints) else None
    coordinates, coordinate_reason = _parse_coordinates(coordinate_value)
    score_value = scores[index] if isinstance(scores, list) and index < len(scores) else None
    score = _finite_number(score_value)
    if coordinate_reason is not None:
        return PointSample(name, None, 0.0, coordinate_reason)
    temporal_allows_analysis = (
        isinstance(temporal_diagnostic, dict)
        and temporal_diagnostic.get("analysis_usable") is True
    )
    temporal_source = (
        temporal_diagnostic.get("source")
        if isinstance(temporal_diagnostic, dict)
        else None
    )
    if (
        isinstance(temporal_diagnostic, dict)
        and temporal_diagnostic.get("analysis_usable") is False
    ):
        return PointSample(name, coordinates, 0.0, "geometry_validation_failed")
    if (
        isinstance(diagnostic, dict)
        and diagnostic.get("valid") is False
        and not temporal_allows_analysis
    ):
        reason_code = diagnostic.get("reason")
        reason_codes = diagnostic.get("rejection_reasons")
        if not isinstance(reason_code, str) and isinstance(reason_codes, list):
            reason_code = next(
                (item for item in reason_codes if isinstance(item, str)),
                None,
            )
        occlusion_state = diagnostic.get("occlusion_state")
        reason: RejectionReason = (
            "low_keypoint_quality"
            if reason_code == "LOW_CONFIDENCE"
            else "missing_keypoint"
            if reason_code in {"TRACK_LOST", "TRACK_REACQUIRING", "OCCLUDED"}
            or occlusion_state in {
                "OCCLUDED",
                "OCCLUDED_BY_BODY",
                "OUT_OF_FRAME",
                "UNKNOWN",
            }
            else "geometry_validation_failed"
        )
        return PointSample(name, coordinates, 0.0, reason)
    effective_threshold = (
        min(threshold, RECONSTRUCTED_KEYPOINT_QUALITY_FLOOR)
        if temporal_allows_analysis
        and temporal_source in ANALYTICAL_RECONSTRUCTION_SOURCES
        else threshold
    )
    if score is None or not 0.0 <= score <= 1.0 or score < effective_threshold:
        return PointSample(name, coordinates, 0.0, "low_keypoint_quality")
    return PointSample(name, coordinates, min(1.0, max(0.0, score)))


def _invalid_hand(side: str, reason: RejectionReason) -> ValidatedHand:
    return ValidatedHand(side=side, valid=False, quality=0.0, landmarks={}, rejection_reason=reason)  # type: ignore[arg-type]


def _parse_hand(side: str, value: Any) -> ValidatedHand:
    if not isinstance(value, dict) or value.get("visible") is not True:
        return _invalid_hand(side, "hand_not_valid")
    quality = _finite_number(value.get("quality"))
    if quality is None or not 0.0 <= quality <= 1.0:
        return _invalid_hand(side, "low_keypoint_quality")
    landmarks_value = value.get("landmarks_2d")
    if not isinstance(landmarks_value, list) or len(landmarks_value) != 21:
        return _invalid_hand(side, "missing_keypoint")

    landmarks: dict[int, PointSample] = {}
    point_validity = value.get("point_validity")
    for index, raw_point in enumerate(landmarks_value):
        coordinates, reason = _parse_coordinates(raw_point)
        if (
            isinstance(point_validity, list)
            and index < len(point_validity)
            and point_validity[index] is not True
        ):
            coordinates = None
            reason = "invalid_coordinate"
        name = f"{side}_hand_landmark_{index}"
        landmarks[index] = PointSample(
            name=name,
            coordinates=coordinates,
            quality=quality if reason is None else 0.0,
            rejection_reason=reason,
        )
    return ValidatedHand(
        side=side,  # type: ignore[arg-type]
        valid=True,
        quality=quality,
        landmarks=landmarks,
        rejection_reason=None,
    )


def _quality_threshold(document: dict[str, Any]) -> float:
    configuration = document.get("configuration")
    value = configuration.get("keypoint_threshold") if isinstance(configuration, dict) else None
    threshold = _finite_number(value)
    if threshold is None or not 0.0 <= threshold <= 1.0:
        return DEFAULT_KEYPOINT_QUALITY_THRESHOLD
    return threshold


def _parse_frame(value: Any, threshold: float) -> FramePose:
    frame = value if isinstance(value, dict) else {}
    keypoints = frame.get("smoothed_keypoints")
    scores = frame.get("scores")
    body_quality = frame.get("body_quality")
    joint_diagnostics = (
        body_quality.get("joints")
        if isinstance(body_quality, dict)
        and isinstance(body_quality.get("joints"), list)
        else []
    )
    temporal_v6 = frame.get("temporal_v6")
    temporal_joints = (
        temporal_v6.get("joints")
        if isinstance(temporal_v6, dict)
        and isinstance(temporal_v6.get("joints"), dict)
        else {}
    )
    body = {
        name: _body_point(
            name,
            index,
            keypoints,
            scores,
            threshold,
            joint_diagnostics[index] if index < len(joint_diagnostics) else None,
            temporal_joints.get(name),
        )
        for name, index in BODY_KEYPOINT_INDICES.items()
    }
    return FramePose(
        person_detected=(
            frame.get("detected") is True
            or sum(
                item.get("analysis_usable") is True
                for item in temporal_joints.values()
                if isinstance(item, dict)
            )
            >= 8
            and str(frame.get("tracking_state", "")).upper() != "LOST"
        ),
        body=body,
        left_hand=_parse_hand("left", frame.get("left_hand")),
        right_hand=_parse_hand("right", frame.get("right_hand")),
    )


def summarize_metric(results: list[MetricResult]) -> dict[str, int | float | None]:
    values = np.asarray(
        [result.value for result in results if result.valid and result.value is not None],
        dtype=float,
    )
    valid_frames = int(values.size)
    invalid_frames = len(results) - valid_frames
    valid_ratio = valid_frames / len(results) if results else 0.0
    if valid_frames == 0:
        return {
            "valid_frames": 0,
            "invalid_frames": invalid_frames,
            "valid_ratio": round(valid_ratio, 6),
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
            "percentile_95": None,
        }
    return {
        "valid_frames": valid_frames,
        "invalid_frames": invalid_frames,
        "valid_ratio": round(valid_ratio, 6),
        "mean": round(float(np.mean(values)), 6),
        "median": round(float(np.median(values)), 6),
        "minimum": round(float(np.min(values)), 6),
        "maximum": round(float(np.max(values)), 6),
        "percentile_95": round(float(np.percentile(values, 95)), 6),
    }


def _explicitly_invalid_bones(frame: dict[str, Any]) -> set[str]:
    body_quality = frame.get("body_quality")
    bones = (
        body_quality.get("bones")
        if isinstance(body_quality, dict) and isinstance(body_quality.get("bones"), dict)
        else {}
    )
    invalid = {
        name
        for name, diagnostic in bones.items()
        if isinstance(diagnostic, dict) and diagnostic.get("valid") is False
    }
    temporal_v6 = frame.get("temporal_v6")
    temporal_bones = (
        temporal_v6.get("analysis_bones")
        if isinstance(temporal_v6, dict)
        and isinstance(temporal_v6.get("analysis_bones"), dict)
        else {}
    )
    for name, diagnostic in temporal_bones.items():
        if not isinstance(name, str) or not isinstance(diagnostic, dict):
            continue
        if diagnostic.get("valid") is True:
            invalid.discard(name)
        elif diagnostic.get("valid") is False:
            invalid.add(name)
    return invalid


def compute_overlay_metrics_from_frame(
    frame: dict[str, Any],
    *,
    quality_threshold: float = DEFAULT_KEYPOINT_QUALITY_THRESHOLD,
) -> dict[str, dict[str, object]]:
    """Compute the same 14 raw metrics for the render layer.

    This public helper deliberately reuses the Metrics Engine parser and
    dependency graph so overlay colours/labels cannot drift from the data
    written by the ergonomics stage.
    """
    if not isinstance(frame, dict):
        raise TypeError("frame must be a dictionary")
    if not 0.0 <= quality_threshold <= 1.0:
        raise ValueError("quality_threshold must be in range 0..1")
    pose = _parse_frame(frame, quality_threshold)
    metrics = compute_frame_metrics(pose)
    invalid_bones = _explicitly_invalid_bones(frame)
    for name, dependency in METRIC_DEPENDENCIES.items():
        required_bones = dependency.get("required_bones", [])
        if (
            metrics[name].valid
            and isinstance(required_bones, list)
            and any(bone in invalid_bones for bone in required_bones)
        ):
            metrics[name] = MetricResult.rejected(
                metrics[name].source_points,
                "dependency_invalid",
            )
    return {name: metrics[name].to_dict() for name in METRIC_NAMES}


def process_pose_document(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise InputSchemaError("Główny element wejściowego JSON musi być obiektem.")
    schema_version = document.get("schema_version")
    if schema_version not in SUPPORTED_POSE_SCHEMAS:
        raise InputSchemaError(
            f"Nieobsługiwana wersja schematu pozy: {schema_version!r}; obsługiwane: {sorted(SUPPORTED_POSE_SCHEMAS)}."
        )
    frames_value = document.get("frames", [])
    if frames_value is None:
        frames_value = []
    if not isinstance(frames_value, list):
        raise InputSchemaError("Pole 'frames' musi być tablicą.")

    threshold = _quality_threshold(document)
    metric_series: dict[str, list[MetricResult]] = {name: [] for name in METRIC_NAMES}
    output_frames: list[dict[str, Any]] = []
    timestamps: list[float | None] = []
    for fallback_index, raw_frame in enumerate(frames_value):
        raw_frame_dict = raw_frame if isinstance(raw_frame, dict) else {}
        frame_pose = _parse_frame(raw_frame_dict, threshold)
        metrics = compute_frame_metrics(frame_pose)
        explicitly_invalid_bones = _explicitly_invalid_bones(raw_frame_dict)
        for name, dependency in METRIC_DEPENDENCIES.items():
            required_bones = dependency.get("required_bones", [])
            if (
                metrics[name].valid
                and isinstance(required_bones, list)
                and any(bone in explicitly_invalid_bones for bone in required_bones)
            ):
                metrics[name] = MetricResult.rejected(
                    metrics[name].source_points,
                    "dependency_invalid",
                )
        for name in METRIC_NAMES:
            metric_series[name].append(metrics[name])

        source_timestamp = _timestamp(raw_frame_dict.get("source_timestamp_seconds"))
        output_timestamp = _timestamp(raw_frame_dict.get("output_timestamp_seconds"))
        timestamp = source_timestamp if source_timestamp is not None else output_timestamp
        timestamps.append(timestamp)
        metric_payloads = {
            name: _metric_payload(metrics[name], raw_frame_dict, name)
            for name in METRIC_NAMES
        }
        output_frames.append(
            {
                "source_frame_index": _metadata_number(raw_frame_dict.get("source_frame_index")),
                "output_frame_index": _metadata_number(raw_frame_dict.get("output_frame_index"))
                if raw_frame_dict.get("output_frame_index") is not None
                else fallback_index,
                "analysis_frame_index": _metadata_number(raw_frame_dict.get("analysis_frame_index"))
                if raw_frame_dict.get("analysis_frame_index") is not None
                else fallback_index,
                "timestamp": timestamp,
                "source_timestamp_seconds": source_timestamp,
                "output_timestamp_seconds": output_timestamp,
                "person_detected": frame_pose.person_detected,
                "metrics": metric_payloads,
                "hand_activity": raw_frame_dict.get("holding")
                if isinstance(raw_frame_dict.get("holding"), dict)
                else None,
            }
        )

    for name in METRIC_NAMES:
        metric_series[name] = reject_isolated_metric_spikes(
            name, metric_series[name], timestamps
        )
        for index, result in enumerate(metric_series[name]):
            output_frames[index]["metrics"][name] = _metric_payload(
                result,
                frames_value[index] if isinstance(frames_value[index], dict) else {},
                name,
            )

    holding_metric_exposure = _holding_metric_exposure(
        output_frames,
        frame_durations(timestamps),
    )
    movement_summary = {
        name: movement_features(metric_series[name], timestamps)
        for name in METRIC_NAMES
    }
    source_summary = (
        document.get("summary")
        if isinstance(document.get("summary"), dict)
        else None
    )
    holding_activity = (
        source_summary.get("holding")
        if isinstance(source_summary, dict)
        and isinstance(source_summary.get("holding"), dict)
        else None
    )

    return {
        "schema_version": "1.0",
        "generated_by": "Ergonomia AI Ergonomics Metrics Engine",
        "source_pose_schema_version": schema_version,
        "analysis_id": document.get("analysis_id"),
        "coordinate_space": document.get("coordinate_space", "source-video-pixels"),
        "metrics_version": "ergonomics-metrics-v1.0",
        "configuration": {
            "interpolation_enabled": False,
            "threshold_scoring_enabled": False,
            "body_keypoint_quality_threshold": threshold,
            "quality_aggregation": "minimum_required_point_quality",
            "reconstructed_keypoint_quality_floor": RECONSTRUCTED_KEYPOINT_QUALITY_FLOOR,
            "dependency_graph": METRIC_DEPENDENCIES,
            "temporal_validation": "metric_specific_dt_aware_outlier_rejection-v2",
            "movement_features": "prominence-and-duration-v2",
            "normative_thresholds_applied": False,
        },
        "summary": {name: summarize_metric(metric_series[name]) for name in METRIC_NAMES},
        "movement_features": movement_summary,
        "posture_duration": {
            "trunk_posture_hold": movement_summary["trunk_inclination_deg"].get(
                "longest_stable_posture_seconds"
            ),
            "neck_posture_hold": movement_summary["neck_flexion_deg"].get(
                "longest_stable_posture_seconds"
            ),
            "left_arm_elevation_hold": movement_summary[
                "left_upper_arm_elevation_deg"
            ].get("longest_stable_posture_seconds"),
            "right_arm_elevation_hold": movement_summary[
                "right_upper_arm_elevation_deg"
            ].get("longest_stable_posture_seconds"),
            "left_wrist_posture_hold": movement_summary[
                "left_wrist_flexion_deg"
            ].get("longest_stable_posture_seconds"),
            "right_wrist_posture_hold": movement_summary[
                "right_wrist_flexion_deg"
            ].get("longest_stable_posture_seconds"),
            "definition": "data-adaptive stable plateau; no risk threshold applied",
        },
        "holding_metric_exposure": holding_metric_exposure,
        "hand_activity": holding_activity,
        "holding_activity": holding_activity,
        "source_quality_summary": source_summary,
        "source_coverage": document.get("coverage")
        if isinstance(document.get("coverage"), dict)
        else None,
        "quality_limitations": _quality_limitations(source_summary),
        "frames": output_frames,
    }


def _metric_payload(
    result: MetricResult,
    source_frame: dict[str, Any],
    metric_name: str,
) -> dict[str, object]:
    payload = result.to_dict()
    timeline_v6 = source_frame.get("timeline_v6")
    layers = timeline_v6.get("layers") if isinstance(timeline_v6, dict) else None
    layer_name = _metric_layer(metric_name)
    layer = layers.get(layer_name) if isinstance(layers, dict) else None
    if isinstance(layer, dict):
        payload["timeline_state"] = layer.get("state")
        payload["usability"] = (
            "usable_for_timeline_only"
            if not result.valid and layer.get("timeline_usable") is True
            else layer.get("usability")
        )
    return payload


def _metric_layer(metric_name: str) -> str:
    if metric_name == "trunk_inclination_deg":
        return "torso"
    if metric_name == "neck_flexion_deg":
        return "neck"
    if metric_name.startswith("left_hand") or metric_name.startswith("left_pinch"):
        return "left_hand"
    if metric_name.startswith("right_hand") or metric_name.startswith("right_pinch"):
        return "right_hand"
    if metric_name.startswith("left_wrist"):
        return "left_wrist"
    if metric_name.startswith("right_wrist"):
        return "right_wrist"
    if metric_name.startswith("left_"):
        return "left_arm"
    if metric_name.startswith("right_"):
        return "right_arm"
    return "torso"


def _quality_limitations(summary: dict[str, Any] | None) -> list[str]:
    if summary is None:
        return []
    quality = summary.get("quality")
    warnings = quality.get("warning_codes") if isinstance(quality, dict) else None
    if not isinstance(warnings, list):
        return []
    mapping = {
        "EXCESSIVE_HAND_OCCLUSION": "low_hand_visibility",
        "EXCESSIVE_LIMB_OCCLUSION": "body_occlusion",
        "LOW_BODY_COVERAGE": "frequent_out_of_frame_or_low_body_coverage",
        "HIGH_MOTION_BLUR": "high_motion_blur",
        "HOLDING_LOW_CONFIDENCE": "holding_uncertain",
    }
    return list(dict.fromkeys(mapping[code] for code in warnings if code in mapping))


def _holding_metric_exposure(
    frames: list[dict[str, Any]],
    durations: list[float],
) -> dict[str, Any] | None:
    dependencies = {
        "left": {
            "holding_with_valid_wrist_posture_seconds": "left_wrist_flexion_deg",
            "holding_with_valid_forearm_posture_seconds": "left_forearm_inclination_deg",
            "holding_with_valid_elbow_posture_seconds": "left_elbow_flexion_deg",
            "holding_with_valid_upper_arm_posture_seconds": "left_upper_arm_elevation_deg",
            "holding_with_valid_trunk_posture_seconds": "trunk_inclination_deg",
        },
        "right": {
            "holding_with_valid_wrist_posture_seconds": "right_wrist_flexion_deg",
            "holding_with_valid_forearm_posture_seconds": "right_forearm_inclination_deg",
            "holding_with_valid_elbow_posture_seconds": "right_elbow_flexion_deg",
            "holding_with_valid_upper_arm_posture_seconds": "right_upper_arm_elevation_deg",
            "holding_with_valid_trunk_posture_seconds": "trunk_inclination_deg",
        },
    }
    output: dict[str, Any] = {}
    observed_holding_data = False
    for side, metric_fields in dependencies.items():
        values = {field: 0.0 for field in metric_fields}
        holding_seconds = 0.0
        for frame, duration in zip(frames, durations):
            hand_activity = frame.get("hand_activity")
            if not isinstance(hand_activity, dict):
                continue
            side_activity = hand_activity.get(side)
            if not isinstance(side_activity, dict):
                continue
            observed_holding_data = True
            if side_activity.get("state") not in {
                "LIKELY_HOLDING",
                "LIKELY_HOLDING_UNKNOWN_OBJECT",
            }:
                continue
            holding_seconds += duration
            metrics = frame.get("metrics")
            if not isinstance(metrics, dict):
                continue
            for field, metric_name in metric_fields.items():
                metric = metrics.get(metric_name)
                if isinstance(metric, dict) and metric.get("valid") is True:
                    values[field] += duration
        output[side] = {
            "likely_holding_seconds": round(holding_seconds, 6),
            **{field: round(value, 6) for field, value in values.items()},
            "threshold_classification_applied": False,
        }
    return output if observed_holding_data else None


def process_pose_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source_path = Path(input_path)
    destination_path = Path(output_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Plik wejściowy nie istnieje: {source_path}")
    if not source_path.is_file():
        raise IsADirectoryError(f"Ścieżka wejściowa nie jest plikiem: {source_path}")
    with source_path.open("r", encoding="utf-8") as source_file:
        document = json.load(source_file)
    result = process_pose_document(document)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with destination_path.open("w", encoding="utf-8", newline="\n") as destination_file:
        json.dump(result, destination_file, ensure_ascii=False, indent=2, allow_nan=False)
        destination_file.write("\n")
    return result
