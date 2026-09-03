"""Smoke benchmark official SAM 2.1 models on a real local video clip."""

from __future__ import annotations

import argparse
import gc
import gzip
import json
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


MODEL_CONFIGS = {
    "base_plus": (
        "configs/sam2.1/sam2.1_hiera_b+.yaml",
        "sam2.1_hiera_base_plus.pt",
    ),
    "large": (
        "configs/sam2.1/sam2.1_hiera_l.yaml",
        "sam2.1_hiera_large.pt",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("pose_json", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--models", nargs="+", choices=tuple(MODEL_CONFIGS), default=list(MODEL_CONFIGS))
    parser.add_argument("--frames", type=int, default=24)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("SAM2 smoke benchmark requires CUDA")
    document = _read_json(args.pose_json)
    frames = document.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("pose document does not contain frames")
    first = next(
        item for item in frames
        if isinstance(item, dict)
        and isinstance(item.get("bbox_xyxy"), list)
        and len(item["bbox_xyxy"]) == 4
    )
    start_frame = int(first["source_frame_index"])
    bbox = np.asarray(first["bbox_xyxy"], dtype=np.float32)
    clip_directory = args.output.parent / "sam2-smoke-frames"
    extracted = _extract_frames(args.video, clip_directory, start_frame, args.frames)
    if extracted <= 1:
        raise RuntimeError("not enough video frames for SAM2 propagation benchmark")
    results: list[dict[str, Any]] = []
    for model in args.models:
        results.append(_benchmark_model(model, clip_directory, bbox, extracted))
    payload = {
        "schema_version": "1.0",
        "device": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "source_video": str(args.video),
        "source_frame_index": start_frame,
        "frame_count": extracted,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


def _benchmark_model(
    model_key: str,
    clip_directory: Path,
    bbox: np.ndarray,
    frame_count: int,
) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[2]
    source = repository / "worker" / "models" / "sam2" / "sources" / "sam2"
    checkpoints = repository / "worker" / "models" / "sam2" / "checkpoints"
    sys.path.insert(0, str(source))
    from sam2.build_sam import build_sam2_video_predictor

    config, checkpoint_name = MODEL_CONFIGS[model_key]
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    predictor = build_sam2_video_predictor(
        config,
        str(checkpoints / checkpoint_name),
        device="cuda",
        apply_postprocessing=False,
    )
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - load_started
    init_started = time.perf_counter()
    state = predictor.init_state(
        video_path=str(clip_directory),
        offload_video_to_cpu=True,
        offload_state_to_cpu=True,
        async_loading_frames=False,
    )
    torch.cuda.synchronize()
    init_seconds = time.perf_counter() - init_started
    center = np.asarray([[(bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5]], dtype=np.float32)
    prompt_started = time.perf_counter()
    _, _, initial_logits = predictor.add_new_points_or_box(
        state,
        frame_idx=0,
        obj_id=1,
        points=center,
        labels=np.asarray([1], dtype=np.int32),
        box=bbox,
    )
    torch.cuda.synchronize()
    prompt_seconds = time.perf_counter() - prompt_started
    initial_mask = (initial_logits[0, 0] > 0.0).detach().cpu().numpy()
    propagation_started = time.perf_counter()
    masks: list[np.ndarray] = []
    for _, _, logits in predictor.propagate_in_video(state):
        masks.append((logits[0, 0] > 0.0).detach().cpu().numpy())
    torch.cuda.synchronize()
    propagation_seconds = time.perf_counter() - propagation_started
    peak_bytes = int(torch.cuda.max_memory_allocated())
    temporal_iou = [
        _iou(masks[index - 1], masks[index]) for index in range(1, len(masks))
    ]
    areas = [float(np.mean(mask)) for mask in masks]
    result = {
        "model": "sam2.1_hiera_base_plus" if model_key == "base_plus" else "sam2.1_hiera_large",
        "checkpoint": checkpoint_name,
        "load_seconds": round(load_seconds, 4),
        "video_init_seconds": round(init_seconds, 4),
        "single_frame_prompt_seconds": round(prompt_seconds, 4),
        "video_propagation_seconds": round(propagation_seconds, 4),
        "propagated_frames": len(masks),
        "frames_per_second": round(len(masks) / max(propagation_seconds, 1e-9), 4),
        "peak_vram_bytes": peak_bytes,
        "peak_vram_mib": round(peak_bytes / (1024 * 1024), 2),
        "initial_mask_area_ratio": round(float(np.mean(initial_mask)), 6),
        "mean_mask_area_ratio": round(float(np.mean(areas)), 6),
        "mean_temporal_mask_iou": round(float(np.mean(temporal_iou)), 6) if temporal_iou else None,
    }
    predictor.reset_state(state)
    del initial_logits, state, predictor, masks
    gc.collect()
    torch.cuda.empty_cache()
    return result


def _extract_frames(
    video_path: Path,
    target: Path,
    start_frame: int,
    requested: int,
) -> int:
    target.mkdir(parents=True, exist_ok=True)
    for existing in target.glob("*.jpg"):
        existing.unlink()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    count = 0
    try:
        while count < requested:
            success, frame = capture.read()
            if not success or frame is None:
                break
            if not cv2.imwrite(str(target / f"{count:05}.jpg"), frame):
                raise RuntimeError("failed to write SAM2 benchmark frame")
            count += 1
    finally:
        capture.release()
    return count


def _read_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("pose JSON root must be an object")
    return value


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    union = np.logical_or(first, second)
    if not np.any(union):
        return 1.0
    return float(np.logical_and(first, second).sum() / union.sum())


if __name__ == "__main__":
    raise SystemExit(main())
