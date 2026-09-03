"""Auditable worst-frame exports for real-video Pose quality review."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


def load_pose_document(path: Path) -> dict[str, Any]:
    """Load a Pose document from JSON or its lossless gzip representation."""

    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            document = json.load(handle)
    else:
        document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Pose document root must be an object.")
    return document


def rank_worst_frames(
    pose_document: Mapping[str, Any],
    diagnostics: Mapping[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Prefer production diagnostics and fall back to conservative frame quality."""

    if diagnostics is not None:
        ranked = diagnostics.get("temporal_worst_frames")
        if isinstance(ranked, list):
            items = [dict(item) for item in ranked if isinstance(item, dict)]
            if items:
                return items[:limit]

    frames = pose_document.get("frames")
    if not isinstance(frames, list):
        return []
    candidates: list[tuple[float, dict[str, Any]]] = []
    for fallback_index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            continue
        final_state = frame.get("final_body_state_v68")
        body_quality = (
            final_state.get("body_quality")
            if isinstance(final_state, dict)
            else None
        )
        if not isinstance(body_quality, (int, float)):
            quality = frame.get("frame_quality")
            if isinstance(quality, dict):
                body_quality = quality.get("score", quality.get("quality"))
        if not isinstance(body_quality, (int, float)):
            body_quality = 0.0 if not frame.get("detected") else 0.5
        analysis_index = _integer(frame.get("analysis_frame_index"), fallback_index)
        candidates.append(
            (
                float(body_quality),
                {
                    "frame_index": analysis_index,
                    "source_frame_index": _integer(
                        frame.get("source_frame_index"), analysis_index
                    ),
                    "timestamp_seconds": _number(
                        frame.get("source_timestamp_seconds"), 0.0
                    ),
                    "score": round(1.0 - max(0.0, min(1.0, float(body_quality))), 6),
                    "reasons": ["LOWEST_AVAILABLE_BODY_QUALITY"],
                },
            )
        )
    candidates.sort(key=lambda candidate: candidate[0])
    return [item for _, item in candidates[:limit]]


def build_reason_document(
    rank_item: Mapping[str, Any],
    frame: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the explicit P64 evidence document without inventing measurements."""

    frame = frame or {}
    silhouette = _mapping(frame.get("person_silhouette_v68"))
    mask_quality = _mapping(silhouette.get("quality"))
    evidence = _mapping(frame.get("silhouette_evidence_v68"))
    final_state = _mapping(frame.get("final_body_state_v68"))
    temporal = _mapping(frame.get("temporal_expert_v67"))
    if not temporal:
        temporal = _mapping(rank_item.get("temporal_expert_v67"))
    tap_tracks = _mapping(temporal.get("tapnext_tracks"))
    tap_forward: dict[str, Any] = {}
    tap_backward: dict[str, Any] = {}
    for joint, raw_track in tap_tracks.items():
        track = _mapping(raw_track)
        if "forward_point" in track:
            tap_forward[str(joint)] = {
                "point": track.get("forward_point"),
                "visible": track.get("forward_visible"),
            }
        if "backward_point" in track:
            tap_backward[str(joint)] = {
                "point": track.get("backward_point"),
                "visible": track.get("backward_visible"),
            }

    rejection_reasons: list[str] = []
    for source in (
        rank_item.get("reasons"),
        mask_quality.get("rejection_reasons"),
        final_state.get("decision_reasons"),
    ):
        if isinstance(source, list):
            for reason in source:
                text = str(reason)
                if text and text not in rejection_reasons:
                    rejection_reasons.append(text)

    body_quality = final_state.get("body_quality")
    if body_quality is None:
        body_quality = frame.get("body_quality", rank_item.get("score"))
    mesh = _mapping(frame.get("mesh_referee_v68"))
    return {
        "frame": _integer(
            frame.get("analysis_frame_index"),
            _integer(rank_item.get("frame_index"), 0),
        ),
        "source_frame_index": _integer(
            frame.get("source_frame_index"),
            _integer(rank_item.get("source_frame_index"), 0),
        ),
        "timestamp_seconds": _number(
            frame.get("source_timestamp_seconds"),
            _number(rank_item.get("timestamp_seconds"), 0.0),
        ),
        "body_quality": body_quality,
        "motion_state": frame.get("motion_v6", rank_item.get("motion_state")),
        "mask_quality": mask_quality or None,
        "raw_rtmw": frame.get("raw_keypoints"),
        "tar": temporal.get("tar_candidate"),
        "tap_forward": tap_forward or None,
        "tap_backward": tap_backward or None,
        "selected_hypothesis": final_state.get("selected_hypothesis_id"),
        "silhouette_support": {
            "valid": silhouette.get("valid"),
            "mask_influence": evidence.get("mask_influence"),
            "alignment_score": evidence.get(
                "skeleton_to_silhouette_alignment_score"
            ),
            "joint_evidence": evidence.get("joint_evidence"),
            "bone_evidence": evidence.get("bone_evidence"),
        },
        "rejection_reasons": rejection_reasons,
        "mesh_3d_agreement": mesh.get("agreement") if mesh else None,
        "mesh_3d_status": mesh.get("status") if mesh else "NOT_USED",
        "accuracy_claimed": False,
    }


def export_worst_frames(
    source_path: Path,
    overlay_path: Path,
    output_directory: Path,
    pose_document: Mapping[str, Any],
    diagnostics: Mapping[str, Any] | None = None,
    *,
    limit: int = 30,
) -> list[Path]:
    """Export original/overlay/debug/mask/reason artifacts per ranked frame."""

    ranked = rank_worst_frames(pose_document, diagnostics, limit=limit)
    frames_raw = pose_document.get("frames")
    frames = [frame for frame in frames_raw if isinstance(frame, dict)] if isinstance(frames_raw, list) else []
    by_analysis_index = {
        _integer(frame.get("analysis_frame_index"), index): frame
        for index, frame in enumerate(frames)
    }
    destination = output_directory / "worst-frames"
    destination.mkdir(parents=True, exist_ok=True)
    source_capture = cv2.VideoCapture(str(source_path))
    overlay_capture = cv2.VideoCapture(str(overlay_path))
    exported: list[Path] = []
    try:
        for rank, item in enumerate(ranked[:limit], start=1):
            analysis_index = _integer(item.get("frame_index"), -1)
            source_index = _integer(item.get("source_frame_index"), analysis_index)
            if analysis_index < 0 or source_index < 0:
                continue
            source_capture.set(cv2.CAP_PROP_POS_FRAMES, source_index)
            overlay_capture.set(cv2.CAP_PROP_POS_FRAMES, analysis_index)
            source_ok, source_frame = source_capture.read()
            overlay_ok, overlay_frame = overlay_capture.read()
            if not source_ok or source_frame is None or not overlay_ok or overlay_frame is None:
                continue
            frame = by_analysis_index.get(analysis_index)
            frame_directory = destination / f"{rank:02d}-frame-{analysis_index:06d}"
            frame_directory.mkdir(parents=True, exist_ok=True)
            _write_png(frame_directory / "original.png", source_frame)
            _write_png(frame_directory / "overlay.png", overlay_frame)
            mask = _render_mask(source_frame.shape[:2], frame)
            _write_png(frame_directory / "mask.png", mask)
            debug = _render_debug(overlay_frame, frame, item, rank)
            _write_png(frame_directory / "debug.png", debug)
            reason = build_reason_document(item, frame)
            (frame_directory / "reason.json").write_text(
                json.dumps(reason, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            exported.append(frame_directory)
    finally:
        source_capture.release()
        overlay_capture.release()
    return exported


def _render_mask(shape: Sequence[int], frame: Mapping[str, Any] | None) -> np.ndarray:
    height, width = int(shape[0]), int(shape[1])
    mask = np.zeros((height, width), dtype=np.uint8)
    silhouette = _mapping((frame or {}).get("person_silhouette_v68"))
    contour = silhouette.get("person_contour")
    if isinstance(contour, list) and len(contour) >= 3:
        points = np.asarray(contour, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [points], 255)
    else:
        cv2.putText(
            mask,
            "MASK UNAVAILABLE FOR THIS PIPELINE VERSION",
            (24, max(42, height // 2)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            180,
            2,
            cv2.LINE_AA,
        )
    return mask


def _render_debug(
    overlay: np.ndarray,
    frame: Mapping[str, Any] | None,
    item: Mapping[str, Any],
    rank: int,
) -> np.ndarray:
    debug = overlay.copy()
    silhouette = _mapping((frame or {}).get("person_silhouette_v68"))
    contour = silhouette.get("person_contour")
    if isinstance(contour, list) and len(contour) >= 3:
        points = np.asarray(contour, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(debug, [points], True, (255, 80, 220), 2, cv2.LINE_AA)
    temporal = _mapping((frame or {}).get("temporal_expert_v67"))
    if not temporal:
        temporal = _mapping(item.get("temporal_expert_v67"))
    _draw_candidate_points(debug, temporal.get("tar_candidate"), (220, 60, 230))
    tracks = _mapping(temporal.get("tapnext_tracks"))
    for raw_track in tracks.values():
        track = _mapping(raw_track)
        for name, color in (
            ("forward_point", (40, 220, 255)),
            ("backward_point", (255, 190, 40)),
        ):
            point = track.get(name)
            if isinstance(point, list) and len(point) == 2:
                cv2.circle(debug, _point(point), 4, color, 1, cv2.LINE_AA)
    cv2.rectangle(debug, (0, 0), (debug.shape[1], 76), (5, 12, 20), -1)
    cv2.putText(
        debug,
        f"worst-rank={rank} frame={item.get('frame_index')} score={item.get('score')}",
        (12, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 245, 255), 1, cv2.LINE_AA,
    )
    reasons = item.get("reasons")
    reason_text = ", ".join(str(value) for value in reasons) if isinstance(reasons, list) else ""
    cv2.putText(
        debug,
        (reason_text or "LOWEST_COMPOSITE_QUALITY")[:125],
        (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (80, 210, 255), 1, cv2.LINE_AA,
    )
    return debug


def _draw_candidate_points(image: np.ndarray, raw: Any, color: tuple[int, int, int]) -> None:
    for value in _mapping(raw).values():
        point = _mapping(value).get("point")
        if isinstance(point, list) and len(point) == 2:
            cv2.circle(image, _point(point), 4, color, 1, cv2.LINE_AA)


def _write_png(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise OSError(f"Failed to write image: {path}")


def _point(value: Sequence[Any]) -> tuple[int, int]:
    return round(float(value[0])), round(float(value[1]))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _number(value: Any, fallback: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return fallback
