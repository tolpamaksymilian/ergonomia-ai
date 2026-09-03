"""Lazy, staged official SAM 2.1 video silhouette backend for Pose V6.8."""

from __future__ import annotations

import gc
import hashlib
import logging
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from .config import SilhouetteConfig, frames_for_seconds
from .silhouette import (
    MaskQuality,
    PackedPersonMask,
    PersonSilhouetteFrame,
    assess_mask_sequence,
)
from .temporal_reconstruction import TemporalFrame


SAM2_REVISION = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
SAM2_MODELS: dict[str, dict[str, object]] = {
    "sam2.1_hiera_base_plus": {
        "config": "configs/sam2.1/sam2.1_hiera_b+.yaml",
        "checkpoint": "sam2.1_hiera_base_plus.pt",
        "bytes": 323_606_802,
        "sha256": "a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5",
    },
    "sam2.1_hiera_large": {
        "config": "configs/sam2.1/sam2.1_hiera_l.yaml",
        "checkpoint": "sam2.1_hiera_large.pt",
        "bytes": 898_083_611,
        "sha256": "2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318",
    },
}


@dataclass(frozen=True)
class Sam2SilhouetteResult:
    frames: tuple[PersonSilhouetteFrame, ...]
    summary: dict[str, object]
    runtime_seconds: float
    peak_vram_bytes: int
    model_name: str
    degraded: bool
    skip_reason: str | None

    @property
    def used_frames(self) -> int:
        return sum(frame.mask is not None for frame in self.frames)


def run_sam2_silhouette_expert(
    video_path: Path,
    job_directory: Path,
    body_records: Sequence[Mapping[str, object]],
    temporal_frames: Sequence[TemporalFrame],
    track_ids: Sequence[str],
    *,
    fps: float,
    config: SilhouetteConfig,
    logger: logging.Logger,
) -> Sam2SilhouetteResult:
    """Track the same person as Pose and return CPU-packed masks.

    SAM2 is imported and loaded only inside this stage, then explicitly
    released.  Any failure returns a provenance-rich degraded result rather
    than invalidating an otherwise valid Pose analysis.
    """

    count = len(body_records)
    if not (count == len(temporal_frames) == len(track_ids)):
        raise ValueError("SAM2 inputs must have equal frame counts")
    if not config.enabled:
        return empty_sam2_result(body_records, track_ids, model_name=config.model, reason="PROFILE_DISABLED")
    if count == 0:
        return empty_sam2_result(body_records, track_ids, model_name=config.model, reason="NO_FRAMES")
    repository = Path(__file__).resolve().parents[3]
    root = repository / "worker" / "models" / "sam2"
    source = root / "sources" / "sam2"
    metadata = SAM2_MODELS[config.model]
    checkpoint = root / "checkpoints" / str(metadata["checkpoint"])
    if not source.is_dir() or not checkpoint.is_file():
        return empty_sam2_result(
            body_records,
            track_ids,
            model_name=config.model,
            reason="SAM2_ARTIFACT_MISSING",
        )
    if checkpoint.stat().st_size != int(metadata["bytes"]):
        return empty_sam2_result(
            body_records,
            track_ids,
            model_name=config.model,
            reason="SAM2_ARTIFACT_SIZE_MISMATCH",
        )

    started = time.perf_counter()
    frames_directory = job_directory / "sam2-native-frames"
    source_indexes = [int(record["source_frame_index"]) for record in body_records]
    timestamps = [float(record["source_timestamp_seconds"]) for record in body_records]
    expected_bboxes = [_record_bbox(record) for record in body_records]
    body_scales = [max(1.0, float(getattr(record.get("pose_graph"), "body_scale", 1.0))) for record in body_records]
    torso_points = [_torso_points(frame) for frame in temporal_frames]
    scene_cuts = [
        bool(getattr(record.get("camera_motion"), "scene_cut", False))
        for record in body_records
    ]
    try:
        _extract_native_frames(video_path, frames_directory, source_indexes)
        sys.path.insert(0, str(source)) if str(source) not in sys.path else None
        import torch
        from sam2.build_sam import build_sam2_video_predictor

        if not torch.cuda.is_available():
            return empty_sam2_result(
                body_records, track_ids, model_name=config.model,
                reason="SAM2_CUDA_UNAVAILABLE",
            )
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        load_started = time.perf_counter()
        predictor = build_sam2_video_predictor(
            str(metadata["config"]),
            str(checkpoint),
            device="cuda",
            apply_postprocessing=False,
        )
        torch.cuda.synchronize()
        load_seconds = time.perf_counter() - load_started
        anchors = _initial_anchor_indexes(
            timestamps,
            track_ids,
            expected_bboxes,
            scene_cuts,
            interval_frames=frames_for_seconds(
                config.reanchor_interval_seconds, fps, minimum=1,
            ),
        )
        reanchor_rounds = 0
        packed_masks: tuple[PackedPersonMask | None, ...] = ()
        silhouette_frames: tuple[PersonSilhouetteFrame, ...] = ()
        propagation_seconds = 0.0
        try:
            for round_index in range(config.maximum_reanchor_rounds):
                reanchor_rounds = round_index + 1
                propagation_started = time.perf_counter()
                packed_masks = _propagate_masks(
                    predictor,
                    frames_directory,
                    anchors,
                    expected_bboxes,
                    torso_points,
                    count,
                )
                torch.cuda.synchronize()
                propagation_seconds += time.perf_counter() - propagation_started
                silhouette_frames = assess_mask_sequence(
                    packed_masks,
                    expected_bboxes,
                    torso_points,
                    body_scales,
                    source_frame_indexes=source_indexes,
                    timestamps=timestamps,
                    track_ids=track_ids,
                    anchor_indexes=anchors,
                    minimum_mask_confidence=config.minimum_mask_confidence,
                    minimum_bbox_agreement=config.minimum_bbox_agreement,
                    drift_centroid_scale_ratio=config.drift_centroid_scale_ratio,
                    drift_area_ratio_minimum=config.drift_area_ratio_minimum,
                    drift_area_ratio_maximum=config.drift_area_ratio_maximum,
                )
                drift_anchors = _drift_reanchors(silhouette_frames, anchors)
                if not drift_anchors or round_index + 1 >= config.maximum_reanchor_rounds:
                    break
                anchors.update(drift_anchors)
        finally:
            del predictor
            gc.collect()
            torch.cuda.empty_cache()
        peak_vram = int(torch.cuda.max_memory_allocated())
        drift_count = sum(frame.quality.drift_detected for frame in silhouette_frames)
        valid_frames = sum(frame.valid for frame in silhouette_frames)
        temporal_ious = [
            frame.quality.temporal_mask_iou for frame in silhouette_frames
            if frame.quality.temporal_mask_iou is not None
        ]
        summary = {
            "available": True,
            "enabled": True,
            "used": bool(valid_frames),
            "model_name": config.model,
            "upstream": "facebookresearch/sam2",
            "upstream_revision": SAM2_REVISION,
            "license": "Apache-2.0",
            "checkpoint_bytes": int(metadata["bytes"]),
            "checkpoint_sha256": str(metadata["sha256"]),
            "backend": "official SAM2VideoPredictor PyTorch CUDA",
            "sam2_used_frames": valid_frames,
            "sam2_mask_frames": sum(mask is not None for mask in packed_masks),
            "sam2_reanchors": len(anchors),
            "sam2_reanchor_rounds": reanchor_rounds,
            "sam2_drift_events": drift_count,
            "person_mask_coverage_ratio": round(valid_frames / max(1, count), 6),
            "person_mask_temporal_iou": (
                round(float(np.mean(temporal_ious)), 6) if temporal_ious else None
            ),
            "load_seconds": round(load_seconds, 4),
            "propagation_seconds": round(propagation_seconds, 4),
            "runtime_seconds": round(time.perf_counter() - started, 4),
            "peak_vram_bytes": peak_vram,
            "peak_vram_mib": round(peak_vram / (1024 * 1024), 2),
            "mask_is_pose_measurement": False,
            "degraded": not bool(valid_frames),
            "skip_reason": None if valid_frames else "NO_VALID_IDENTITY_MASKS",
        }
        logger.info(
            "Pose V6.8 SAM2: model=%s masks=%d/%d valid=%d reanchors=%d "
            "drift=%d runtime=%.2fs peak_vram=%.1fMiB",
            config.model,
            sum(mask is not None for mask in packed_masks),
            count,
            valid_frames,
            len(anchors),
            drift_count,
            float(summary["runtime_seconds"]),
            float(summary["peak_vram_mib"]),
        )
        return Sam2SilhouetteResult(
            silhouette_frames,
            summary,
            time.perf_counter() - started,
            peak_vram,
            config.model,
            not bool(valid_frames),
            None if valid_frames else "NO_VALID_IDENTITY_MASKS",
        )
    except (ImportError, OSError, RuntimeError, ValueError, cv2.error) as error:
        logger.warning(
            "Pose V6.8 SAM2 degraded fallback for model=%s: %s: %s",
            config.model,
            type(error).__name__,
            str(error)[:300],
        )
        result = empty_sam2_result(
            body_records,
            track_ids,
            model_name=config.model,
            reason=f"SAM2_RUNTIME_{type(error).__name__.upper()}",
        )
        return Sam2SilhouetteResult(
            result.frames,
            {**result.summary, "runtime_seconds": round(time.perf_counter() - started, 4)},
            time.perf_counter() - started,
            0,
            config.model,
            True,
            result.skip_reason,
        )


def empty_sam2_result(
    body_records: Sequence[Mapping[str, object]],
    track_ids: Sequence[str],
    *,
    model_name: str,
    reason: str,
) -> Sam2SilhouetteResult:
    frames = tuple(
        PersonSilhouetteFrame(
            source_frame_index=int(record.get("source_frame_index", index)),
            timestamp_seconds=float(record.get("source_timestamp_seconds", 0.0)),
            person_track_id=str(track_ids[index]) if index < len(track_ids) else "unknown",
            mask=None,
            quality=MaskQuality(0.0, 0.0, 0.0, 0.0, None, 0.0, True, 0.0, (reason,)),
        )
        for index, record in enumerate(body_records)
    )
    return Sam2SilhouetteResult(
        frames=frames,
        summary={
            "available": reason not in {"SAM2_ARTIFACT_MISSING", "SAM2_ARTIFACT_SIZE_MISMATCH"},
            "enabled": reason != "PROFILE_DISABLED",
            "used": False,
            "model_name": model_name,
            "sam2_used_frames": 0,
            "sam2_mask_frames": 0,
            "sam2_reanchors": 0,
            "sam2_drift_events": 0,
            "degraded": True,
            "skip_reason": reason,
            "mask_is_pose_measurement": False,
        },
        runtime_seconds=0.0,
        peak_vram_bytes=0,
        model_name=model_name,
        degraded=True,
        skip_reason=reason,
    )


def _propagate_masks(
    predictor: object,
    frames_directory: Path,
    anchor_indexes: set[int],
    bboxes: Sequence[tuple[float, float, float, float] | None],
    torso_points: Sequence[np.ndarray | None],
    frame_count: int,
) -> tuple[PackedPersonMask | None, ...]:
    state = predictor.init_state(
        video_path=str(frames_directory),
        offload_video_to_cpu=True,
        offload_state_to_cpu=True,
        async_loading_frames=False,
    )
    try:
        prompted = 0
        for index in sorted(anchor_indexes):
            bbox = bboxes[index]
            if bbox is None:
                continue
            torso = torso_points[index]
            positive = _positive_points(torso, bbox)
            predictor.add_new_points_or_box(
                state,
                frame_idx=index,
                obj_id=1,
                points=positive,
                labels=np.ones(len(positive), dtype=np.int32),
                box=np.asarray(bbox, dtype=np.float32),
            )
            prompted += 1
        if prompted == 0:
            raise RuntimeError("SAM2 has no valid same-person initialization prompt")
        masks: list[PackedPersonMask | None] = [None] * frame_count
        for frame_index, _, logits in predictor.propagate_in_video(state):
            values = logits[0, 0].detach().float().cpu().numpy()
            binary = values > 0.0
            positive_values = values[binary]
            confidence = (
                float(np.mean(1.0 / (1.0 + np.exp(-np.clip(positive_values, -20.0, 20.0)))))
                if positive_values.size else 0.0
            )
            masks[int(frame_index)] = PackedPersonMask.from_mask(
                binary,
                logit_confidence=confidence,
            )
        return tuple(masks)
    finally:
        predictor.reset_state(state)


def _extract_native_frames(
    video_path: Path,
    target: Path,
    source_indexes: Sequence[int],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob("*.jpg"):
        old.unlink()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"SAM2 cannot open source video: {video_path}")
    previous_source = -2
    try:
        for output_index, source_index in enumerate(source_indexes):
            if source_index != previous_source + 1:
                capture.set(cv2.CAP_PROP_POS_FRAMES, int(source_index))
            success, frame = capture.read()
            if not success or frame is None or frame.size == 0:
                raise RuntimeError(f"SAM2 cannot read native frame {source_index}")
            if not cv2.imwrite(
                str(target / f"{output_index:06}.jpg"),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 96],
            ):
                raise RuntimeError(f"SAM2 cannot write native frame {source_index}")
            previous_source = source_index
    finally:
        capture.release()


def _initial_anchor_indexes(
    timestamps: Sequence[float],
    track_ids: Sequence[str],
    bboxes: Sequence[tuple[float, float, float, float] | None],
    scene_cuts: Sequence[bool],
    *,
    interval_frames: int,
) -> set[int]:
    anchors: set[int] = set()
    last_anchor = -interval_frames
    previous_track: str | None = None
    previous_bbox: tuple[float, float, float, float] | None = None
    for index, bbox in enumerate(bboxes):
        if bbox is None:
            continue
        track_changed = previous_track is not None and track_ids[index] != previous_track
        bbox_jump = _bbox_center_jump(previous_bbox, bbox) > 0.35
        if (
            not anchors
            or index - last_anchor >= interval_frames
            or bool(scene_cuts[index])
            or track_changed
            or bbox_jump
        ):
            anchors.add(index)
            last_anchor = index
        previous_track = track_ids[index]
        previous_bbox = bbox
    return anchors


def _drift_reanchors(
    frames: Sequence[PersonSilhouetteFrame],
    existing: set[int],
) -> set[int]:
    output: set[int] = set()
    last_added = -10
    for index, frame in enumerate(frames):
        if frame.quality.drift_detected and index not in existing and index - last_added >= 3:
            output.add(index)
            last_added = index
    return output


def _record_bbox(record: Mapping[str, object]) -> tuple[float, float, float, float] | None:
    value = record.get("render_bbox_array")
    if value is None:
        value = record.get("bbox_xyxy")
    if value is None:
        return None
    bbox = np.asarray(value, dtype=np.float64).reshape(-1)
    if bbox.size != 4 or not np.isfinite(bbox).all() or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return tuple(float(item) for item in bbox)


def _torso_points(frame: TemporalFrame) -> np.ndarray | None:
    indexes = [5, 6, 11, 12]
    points = [
        frame.render_points[index]
        for index in indexes
        if index < len(frame.render_scores)
        and frame.render_scores[index] > 0.0
        and np.isfinite(frame.render_points[index]).all()
    ]
    return np.asarray(points, dtype=np.float32) if points else None


def _positive_points(
    torso: np.ndarray | None,
    bbox: tuple[float, float, float, float],
) -> np.ndarray:
    """Return several same-person torso prompts, not one clothing-region point.

    On workwear footage a single center prompt can select only trousers or a
    shirt as an object. Shoulder/hip prompts plus the person bbox reliably ask
    SAM2 for the complete visible worker. Only finite points inside the locked
    detector bbox are allowed.
    """

    if torso is not None:
        values = np.asarray(torso, dtype=np.float64).reshape(-1, 2)
        valid = values[np.isfinite(values).all(axis=1)]
        valid = valid[
            (valid[:, 0] >= bbox[0])
            & (valid[:, 0] <= bbox[2])
            & (valid[:, 1] >= bbox[1])
            & (valid[:, 1] <= bbox[3])
        ] if len(valid) else valid
        if len(valid):
            return valid.astype(np.float32)
    return np.asarray([[
        (bbox[0] + bbox[2]) * 0.5,
        (bbox[1] + bbox[3]) * 0.5,
    ]], dtype=np.float32)


def _bbox_center_jump(
    first: tuple[float, float, float, float] | None,
    second: tuple[float, float, float, float],
) -> float:
    if first is None:
        return 0.0
    first_center = ((first[0] + first[2]) * 0.5, (first[1] + first[3]) * 0.5)
    second_center = ((second[0] + second[2]) * 0.5, (second[1] + second[3]) * 0.5)
    scale = max(1.0, math.hypot(first[2] - first[0], first[3] - first[1]))
    return math.dist(first_center, second_center) / scale


def checkpoint_sha256(model_name: str) -> str | None:
    metadata = SAM2_MODELS.get(model_name)
    if metadata is None:
        return None
    root = Path(__file__).resolve().parents[3] / "worker" / "models" / "sam2" / "checkpoints"
    path = root / str(metadata["checkpoint"])
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "SAM2_MODELS",
    "SAM2_REVISION",
    "Sam2SilhouetteResult",
    "checkpoint_sha256",
    "empty_sam2_result",
    "run_sam2_silhouette_expert",
]
