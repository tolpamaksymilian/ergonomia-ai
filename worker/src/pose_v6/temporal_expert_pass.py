"""Real temporal expert execution for Pose V6.7 hard-motion segments."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from .tapnextpp_backend import BidirectionalTapTracks, TapNextPPBackend
from .tar_vitpose_backend import TAR_WINDOW_SIZE, TarPoseObservation, TarVitPoseBackend
from .temporal_expert_fusion import (
    CORE_LIMB_JOINTS,
    JointFusionDecision,
    TrackerEvidence,
    fuse_core_frame,
)


@dataclass(frozen=True)
class TemporalExpertFrameResult:
    frame_index: int
    tar: TarPoseObservation
    tracker: Mapping[int, TrackerEvidence]
    fusion: Mapping[int, JointFusionDecision]
    tracker_reason: str = "NO_TRACK_EVIDENCE"

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": (
                "TAR-ViTPose-B-17+TAPNext++-512"
                if self.tracker else "TAR-ViTPose-B-17"
            ),
            "coordinate_space": "ORIGINAL_PIXELS",
            "tar_model": self.tar.model_name,
            "tar_inference_seconds": round(self.tar.inference_seconds, 6),
            "tar_peak_vram_bytes": self.tar.peak_vram_bytes,
            "mapped_joint_indexes": list(CORE_LIMB_JOINTS),
            "hand_face_foot_mapping_enabled": False,
            "tar_candidate": {
                str(index): {
                    "point": [
                        round(float(self.tar.points[index, 0]), 3),
                        round(float(self.tar.points[index, 1]), 3),
                    ],
                    "quality": round(float(self.tar.scores[index]), 6),
                    "spatial_status": (
                        self.tar.point_statuses[index]
                        if index < len(self.tar.point_statuses) else "UNKNOWN"
                    ),
                }
                for index in CORE_LIMB_JOINTS
            },
            "tapnext_tracks": {
                str(index): {
                    "forward_point": (
                        list(evidence.forward_point)
                        if evidence.forward_point is not None else None
                    ),
                    "backward_point": (
                        list(evidence.backward_point)
                        if evidence.backward_point is not None else None
                    ),
                    "forward_visible": evidence.forward_visible,
                    "backward_visible": evidence.backward_visible,
                }
                for index, evidence in self.tracker.items()
            },
            "tracker_available": bool(self.tracker),
            "tracker_reason": self.tracker_reason,
            "fusion": {
                str(index): decision.to_dict()
                for index, decision in self.fusion.items()
            },
        }


@dataclass(frozen=True)
class TemporalExpertPassResult:
    frames: Mapping[int, TemporalExpertFrameResult]
    summary: Mapping[str, object]


@dataclass(frozen=True)
class TapAnchorSegment:
    hard_start: int
    hard_end: int
    forward_anchor: int | None
    backward_anchor: int | None
    reason: str

    @property
    def available(self) -> bool:
        return self.forward_anchor is not None and self.backward_anchor is not None


def run_temporal_expert_pass(
    video_path: Path,
    records: Sequence[Mapping[str, object]],
    specialist_indexes: set[int],
    *,
    repository_root: Path,
    device: str = "cuda",
) -> TemporalExpertPassResult:
    """Execute TAR measurements and bidirectional TAP support on real frames."""

    enabled = os.getenv("POSE_TEMPORAL_EXPERT_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on", "tak",
    }
    tap_enabled = os.getenv("POSE_TAPNEXT_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on", "tak",
    }
    summary: dict[str, object] = {
        "version": "temporal-expert-v1",
        "enabled": enabled,
        "backend_executed": False,
        "tar_executed": False,
        "tapnext_executed": False,
        "tapnext_enabled": tap_enabled,
        "candidate_frame_count": len(specialist_indexes),
        "executed_frame_count": 0,
        "accepted_joint_count": 0,
        "rejected_joint_count": 0,
        "mapped_joint_indexes": list(CORE_LIMB_JOINTS),
        "mapping_scope": "COCO17_CORE_BODY_ONLY",
        "tracker_is_pose_measurement": False,
    }
    if not enabled or not records or not specialist_indexes:
        summary["reason"] = "DISABLED" if not enabled else "NO_HARD_MOTION_FRAMES"
        return TemporalExpertPassResult({}, summary)

    tar_checkpoint = _configured_path(
        "POSE_TAR_VITPOSE_CHECKPOINT",
        repository_root / "worker" / "models" / "temporal" / "tar-vitpose" / "tarvitpose_b_17.pt",
    )
    tap_checkpoint = _configured_path(
        "POSE_TAPNEXT_CHECKPOINT",
        repository_root / "worker" / "models" / "temporal" / "tapnextpp" / "tapnextpp_512.ckpt",
    )
    required_artifacts = (tar_checkpoint, tap_checkpoint) if tap_enabled else (tar_checkpoint,)
    missing = [str(path) for path in required_artifacts if not path.is_file()]
    if missing:
        summary["reason"] = "TEMPORAL_EXPERT_WEIGHTS_MISSING"
        summary["missing_artifact_count"] = len(missing)
        return TemporalExpertPassResult({}, summary)

    anchor_search_frames = max(
        1, int(os.getenv("POSE_TAPNEXT_ANCHOR_SEARCH_FRAMES", "12")),
    )
    anchor_segments = _tap_anchor_segments(
        specialist_indexes, records, maximum_search_frames=anchor_search_frames,
    )
    required_indexes = set()
    for segment in anchor_segments:
        if segment.available:
            required_indexes.update(range(
                int(segment.forward_anchor), int(segment.backward_anchor) + 1,
            ))
    for center in specialist_indexes:
        required_indexes.update(
            min(max(center + offset, 0), len(records) - 1)
            for offset in range(-(TAR_WINDOW_SIZE // 2), TAR_WINDOW_SIZE // 2 + 1)
        )
    video_frames = _read_frames(video_path, records, required_indexes)
    missing_frames = required_indexes - video_frames.keys()
    if missing_frames:
        summary["reason"] = "TEMPORAL_EXPERT_FRAME_READ_FAILED"
        summary["missing_frame_count"] = len(missing_frames)
        return TemporalExpertPassResult({}, summary)

    tar_observations: dict[int, TarPoseObservation] = {}
    tar_backend = TarVitPoseBackend(tar_checkpoint, device=device)
    try:
        for center in sorted(specialist_indexes):
            window_indexes = [
                min(max(center + offset, 0), len(records) - 1)
                for offset in range(-(TAR_WINDOW_SIZE // 2), TAR_WINDOW_SIZE // 2 + 1)
            ]
            bbox = _record_bbox(records[center])
            if bbox is None:
                continue
            tar_observations[center] = tar_backend.infer_window(
                [video_frames[index] for index in window_indexes], bbox,
            )
    finally:
        tar_backend.close()
    summary["tar_executed"] = bool(tar_observations)
    summary["tar_frame_count"] = len(tar_observations)
    summary["tar_inference_seconds"] = round(sum(
        observation.inference_seconds for observation in tar_observations.values()
    ), 6)
    summary["tar_peak_vram_bytes"] = max((
        observation.peak_vram_bytes or 0 for observation in tar_observations.values()
    ), default=0)

    track_evidence: dict[int, dict[int, TrackerEvidence]] = {}
    tracker_reasons: dict[int, str] = {
        index: segment.reason
        for segment in anchor_segments
        for index in range(segment.hard_start, segment.hard_end + 1)
    }
    tap_seconds = 0.0
    tap_peak = 0
    no_anchor_count = sum(not segment.available for segment in anchor_segments)
    if tap_enabled and any(segment.available for segment in anchor_segments):
        tap_backend = TapNextPPBackend(tap_checkpoint, device=device)
        try:
            for segment in anchor_segments:
                if not segment.available:
                    continue
                start = int(segment.forward_anchor)
                end = int(segment.backward_anchor)
                common_joints = tuple(
                    joint for joint in CORE_LIMB_JOINTS
                    if _good_anchor_joint(records[start], joint)
                    and _good_anchor_joint(records[end], joint)
                )
                if not common_joints:
                    for index in range(segment.hard_start, segment.hard_end + 1):
                        tracker_reasons[index] = "NO_COMMON_VALID_ANCHOR_JOINTS"
                    continue
                segment_frames = [video_frames[index] for index in range(start, end + 1)]
                start_points = np.stack([
                    np.asarray(records[start]["raw_points"], dtype=np.float32)[joint]
                    for joint in common_joints
                ])
                end_points = np.stack([
                    np.asarray(records[end]["raw_points"], dtype=np.float32)[joint]
                    for joint in common_joints
                ])
                tracks = tap_backend.track_bidirectional(segment_frames, start_points, end_points)
                tap_seconds += tracks.forward.inference_seconds + tracks.backward.inference_seconds
                tap_peak = max(
                    tap_peak,
                    tracks.forward.peak_vram_bytes or 0,
                    tracks.backward.peak_vram_bytes or 0,
                )
                _merge_track_evidence(track_evidence, tracks, start, common_joints)
                for index in range(segment.hard_start, segment.hard_end + 1):
                    tracker_reasons[index] = "VALID_BIDIRECTIONAL_ANCHORS"
        finally:
            tap_backend.close()
    summary["tapnext_executed"] = bool(track_evidence)
    summary["tapnext_inference_seconds"] = round(tap_seconds, 6)
    summary["tapnext_peak_vram_bytes"] = tap_peak
    summary["bidirectional_tracking"] = True
    summary["tap_anchor_search_frames"] = anchor_search_frames
    summary["tap_anchor_segment_count"] = len(anchor_segments)
    summary["tap_no_valid_anchor_segment_count"] = no_anchor_count
    summary["tracker_available"] = bool(track_evidence)
    summary["tracker_reason"] = (
        "VALID_BIDIRECTIONAL_ANCHORS" if track_evidence
        else "NO_VALID_ANCHOR" if no_anchor_count else "NO_COMMON_VALID_ANCHOR_JOINTS"
    )

    frame_results: dict[int, TemporalExpertFrameResult] = {}
    for frame_index, tar in tar_observations.items():
        record = records[frame_index]
        evidence = _validated_track_evidence(
            track_evidence.get(frame_index, {}),
            video_frames[frame_index].shape[1],
            video_frames[frame_index].shape[0],
        )
        decisions = fuse_core_frame(
            np.asarray(record["raw_points"], dtype=np.float32),
            np.asarray(record["raw_scores"], dtype=np.float32),
            tar.points,
            tar.scores,
            evidence,
            body_scale=max(float(record["pose_graph"].body_scale), 1.0),
        )
        frame_results[frame_index] = TemporalExpertFrameResult(
            frame_index, tar, evidence, decisions,
            tracker_reasons.get(frame_index, "NO_VALID_ANCHOR"),
        )
    accepted = sum(
        decision.accepted
        for frame in frame_results.values()
        for decision in frame.fusion.values()
    )
    possible = len(frame_results) * len(CORE_LIMB_JOINTS)
    summary.update({
        "backend_executed": bool(frame_results),
        "executed_frame_count": len(frame_results),
        "accepted_joint_count": accepted,
        "rejected_joint_count": max(0, possible - accepted),
        "usage_ratio": round(len(frame_results) / max(1, len(records)), 6),
        "reason": "EXECUTED" if frame_results else "NO_VALID_TEMPORAL_OBSERVATIONS",
    })
    return TemporalExpertPassResult(frame_results, summary)


def _segments(indexes: set[int], frame_count: int, *, padding: int) -> tuple[tuple[int, int], ...]:
    if not indexes:
        return ()
    runs: list[list[int]] = []
    for index in sorted(indexes):
        if not runs or index > runs[-1][-1] + 1:
            runs.append([index])
        else:
            runs[-1].append(index)
    expanded = [
        (max(0, run[0] - padding), min(frame_count - 1, run[-1] + padding))
        for run in runs
    ]
    merged: list[tuple[int, int]] = []
    for start, end in expanded:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _tap_anchor_segments(
    indexes: set[int],
    records: Sequence[Mapping[str, object]],
    *,
    maximum_search_frames: int,
    minimum_good_joints: int = 6,
) -> tuple[TapAnchorSegment, ...]:
    """Find native, trustworthy frames bracketing each contiguous hard run."""

    if not indexes or not records:
        return ()
    runs = _segments(indexes, len(records), padding=0)
    output: list[TapAnchorSegment] = []
    for hard_start, hard_end in runs:
        forward_anchor = next((
            candidate
            for candidate in range(
                hard_start - 1,
                max(-1, hard_start - maximum_search_frames - 1),
                -1,
            )
            if len(_good_anchor_joints(records[candidate])) >= minimum_good_joints
        ), None)
        backward_anchor = next((
            candidate
            for candidate in range(
                hard_end + 1,
                min(len(records), hard_end + maximum_search_frames + 1),
            )
            if len(_good_anchor_joints(records[candidate])) >= minimum_good_joints
        ), None)
        if forward_anchor is None or backward_anchor is None:
            reason = "NO_VALID_ANCHOR"
        else:
            reason = "VALID_BIDIRECTIONAL_ANCHORS"
        output.append(TapAnchorSegment(
            hard_start, hard_end, forward_anchor, backward_anchor, reason,
        ))
    return tuple(output)


def _read_frames(
    video_path: Path,
    records: Sequence[Mapping[str, object]],
    indexes: set[int],
) -> dict[int, np.ndarray]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return {}
    output: dict[int, np.ndarray] = {}
    try:
        for index in sorted(indexes):
            source_index = int(records[index]["source_frame_index"])
            capture.set(cv2.CAP_PROP_POS_FRAMES, source_index)
            success, frame = capture.read()
            if success and frame is not None and frame.size:
                output[index] = frame
    finally:
        capture.release()
    return output


def _merge_track_evidence(
    destination: dict[int, dict[int, TrackerEvidence]],
    tracks: BidirectionalTapTracks,
    start_index: int,
    joints: tuple[int, ...],
) -> None:
    for offset in range(tracks.forward.points.shape[0]):
        frame = destination.setdefault(start_index + offset, {})
        for track_index, joint in enumerate(joints):
            forward = tracks.forward.points[offset, track_index]
            backward = tracks.backward.points[offset, track_index]
            frame[joint] = TrackerEvidence(
                (float(forward[0]), float(forward[1])),
                (float(backward[0]), float(backward[1])),
                bool(tracks.forward.visible[offset, track_index]),
                bool(tracks.backward.visible[offset, track_index]),
            )


def _validated_track_evidence(
    evidence: Mapping[int, TrackerEvidence],
    frame_width: int,
    frame_height: int,
) -> dict[int, TrackerEvidence]:
    """Reject tracker support outside native pixels before pose fusion.

    TAP remains support-only; canonical bone, chain, velocity and side gates are
    applied to the selected image measurement by the production anatomy pass.
    """

    output: dict[int, TrackerEvidence] = {}
    for joint, item in evidence.items():
        forward_valid = item.forward_visible and _point_in_frame(
            item.forward_point, frame_width, frame_height,
        )
        backward_valid = item.backward_visible and _point_in_frame(
            item.backward_point, frame_width, frame_height,
        )
        output[joint] = TrackerEvidence(
            item.forward_point if forward_valid else None,
            item.backward_point if backward_valid else None,
            forward_valid,
            backward_valid,
        )
    return output


def _record_bbox(record: Mapping[str, object]) -> np.ndarray | None:
    for key in ("render_bbox_array", "bbox_array"):
        value = record.get(key)
        if value is None:
            continue
        bbox = np.asarray(value, dtype=np.float32).reshape(-1)
        if bbox.size == 4 and np.isfinite(bbox).all() and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
            return bbox
    return None


def _good_anchor_joints(
    record: Mapping[str, object], joint: int | None = None,
) -> tuple[int, ...] | bool:
    if joint is not None:
        return _good_anchor_joint(record, joint)
    return tuple(index for index in CORE_LIMB_JOINTS if _good_anchor_joint(record, index))


def _good_anchor_joint(record: Mapping[str, object], joint: int) -> bool:
    points = np.asarray(record["raw_points"], dtype=np.float32)
    scores = np.asarray(record["raw_scores"], dtype=np.float32)
    if not (
        joint < len(points) and joint < len(scores)
        and float(scores[joint]) >= 0.60
        and bool(np.isfinite(points[joint]).all())
        and not bool(np.allclose(points[joint], 0.0))
        and bool(record.get("detected", True))
        and not bool(record.get("prevalidation_motion_blur", False))
        and float(record.get("tracking_identity_score", 1.0)) >= 0.55
    ):
        return False
    graph = record.get("pose_graph")
    joints = getattr(graph, "joints", None)
    if joints is None or joint >= len(joints):
        return False
    state = joints[joint]
    source = str(getattr(getattr(state, "source", None), "value", getattr(state, "source", "")))
    temporal = str(getattr(
        getattr(state, "temporal_state", None), "value", getattr(state, "temporal_state", ""),
    ))
    occlusion = str(getattr(
        getattr(state, "occlusion_state", None), "value", getattr(state, "occlusion_state", ""),
    ))
    rejection_reasons = tuple(str(value).upper() for value in getattr(
        state, "rejection_reasons", (),
    ))
    if (
        not bool(getattr(state, "valid", False))
        or float(getattr(state, "quality", 0.0)) < 0.55
        or source.lower() != "raw"
        or temporal.upper() != "STABLE"
        or occlusion.upper() != "VISIBLE"
        or any("SIDE" in reason or "CROSS" in reason for reason in rejection_reasons)
    ):
        return False
    joint_name = str(getattr(state, "name", ""))
    related_bones = [
        bone for bone in getattr(graph, "bones", {}).values()
        if joint_name in {str(getattr(bone, "joint_a", "")), str(getattr(bone, "joint_b", ""))}
    ]
    return not related_bones or all(
        bool(getattr(bone, "valid", False)) and float(getattr(bone, "quality", 0.0)) >= 0.45
        for bone in related_bones
    )


def _strong_joint(record: Mapping[str, object], joint: int) -> bool:
    """Backward-compatible alias for callers/tests predating strict anchors."""

    return _good_anchor_joint(record, joint)


def _point_in_frame(
    point: tuple[float, float] | None,
    frame_width: int,
    frame_height: int,
) -> bool:
    if point is None:
        return False
    value = np.asarray(point, dtype=np.float64).reshape(-1)
    return bool(
        value.size == 2 and np.isfinite(value).all()
        and 0.0 <= value[0] < frame_width
        and 0.0 <= value[1] < frame_height
    )


def _configured_path(name: str, default: Path) -> Path:
    configured = os.getenv(name, "").strip()
    return Path(configured).expanduser().resolve() if configured else default.resolve()


__all__ = [
    "TemporalExpertFrameResult",
    "TemporalExpertPassResult",
    "TapAnchorSegment",
    "_tap_anchor_segments",
    "run_temporal_expert_pass",
]
