"""Official TAPNext++ 512 adapter used as bidirectional point evidence.

The Google DeepMind implementation is Apache-2.0 and is installed from a
pinned upstream revision by ``worker/tools/install_temporal_experts.py``.
TAPNext++ predictions are never emitted as pose measurements.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


TAPNEXT_MODEL_NAME = "TAPNext++-TRecViT-B-512"
TAPNEXT_CHECKPOINT_FILENAME = "tapnextpp_512.ckpt"
TAPNEXT_CHECKPOINT_BYTES = 2_532_283_010


@dataclass(frozen=True)
class TapTrackSequence:
    points: np.ndarray
    visible: np.ndarray
    inference_seconds: float
    peak_vram_bytes: int | None
    direction: str


@dataclass(frozen=True)
class BidirectionalTapTracks:
    forward: TapTrackSequence
    backward: TapTrackSequence
    model_name: str = TAPNEXT_MODEL_NAME


class TapNextPPBackend:
    def __init__(
        self,
        checkpoint_path: Path,
        *,
        source_root: Path | None = None,
        device: str = "cuda",
    ) -> None:
        checkpoint_path = Path(checkpoint_path)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"TAPNext++ checkpoint not found: {checkpoint_path}")
        if checkpoint_path.stat().st_size != TAPNEXT_CHECKPOINT_BYTES:
            raise RuntimeError("TAPNext++ checkpoint is incomplete or has an unexpected size")
        source = _resolve_source_root(source_root)
        if not (source / "tapnet" / "tapnext" / "tapnext_torch.py").is_file():
            raise FileNotFoundError(
                "TAPNext++ official source is missing; run "
                "worker/tools/install_temporal_experts.py"
            )
        source_text = str(source)
        if source_text not in sys.path:
            sys.path.insert(0, source_text)
        torch = importlib.import_module("torch")
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("TAPNext++ requested CUDA but CUDA is unavailable")
        wrapper_module = importlib.import_module("tapnet.tapnextpp.votsp2026.model")
        self._torch = torch
        self.device = torch.device(device)
        self.model = wrapper_module.TAPNextPP.from_checkpoint(
            checkpoint_path,
            device=self.device,
            half_precision=False,
            compile_model=False,
            input_resolution=512,
        )

    def track_bidirectional(
        self,
        frames_bgr: Sequence[np.ndarray],
        start_points_xy: np.ndarray,
        end_points_xy: np.ndarray,
    ) -> BidirectionalTapTracks:
        if not frames_bgr:
            raise ValueError("TAPNext++ requires at least one frame")
        forward = self._track(frames_bgr, start_points_xy, direction="forward")
        reversed_result = self._track(
            tuple(reversed(frames_bgr)), end_points_xy, direction="backward",
        )
        backward = TapTrackSequence(
            points=reversed_result.points[::-1].copy(),
            visible=reversed_result.visible[::-1].copy(),
            inference_seconds=reversed_result.inference_seconds,
            peak_vram_bytes=reversed_result.peak_vram_bytes,
            direction="backward",
        )
        return BidirectionalTapTracks(forward, backward)

    def _track(
        self,
        frames_bgr: Sequence[np.ndarray],
        seed_points_xy: np.ndarray,
        *,
        direction: str,
    ) -> TapTrackSequence:
        seeds = np.asarray(seed_points_xy, dtype=np.float32)
        if seeds.ndim != 2 or seeds.shape[1] != 2 or not np.isfinite(seeds).all():
            raise ValueError("TAPNext++ seed points must be finite [N,2]")
        output_points = np.zeros((len(frames_bgr), len(seeds), 2), dtype=np.float32)
        output_visible = np.zeros((len(frames_bgr), len(seeds)), dtype=bool)
        state = None
        if self.device.type == "cuda":
            self._torch.cuda.reset_peak_memory_stats(self.device)
            self._torch.cuda.synchronize(self.device)
        started = time.perf_counter()
        for index, frame in enumerate(frames_bgr):
            positions, visible, state = self.model.track_frame(
                frame,
                query_points_xy=seeds if index == 0 else None,
                state=state,
                autocast=True,
            )
            output_points[index] = positions
            output_visible[index] = visible
        if self.device.type == "cuda":
            self._torch.cuda.synchronize(self.device)
            peak_vram = int(self._torch.cuda.max_memory_allocated(self.device))
        else:
            peak_vram = None
        return TapTrackSequence(
            output_points,
            output_visible,
            time.perf_counter() - started,
            peak_vram,
            direction,
        )

    def close(self) -> None:
        model = getattr(self, "model", None)
        if model is not None:
            model.to("cpu")
            del self.model
        if self.device.type == "cuda":
            self._torch.cuda.empty_cache()


def _resolve_source_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return Path(explicit).resolve()
    configured = os.getenv("POSE_TAPNEXT_SOURCE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    repository = Path(__file__).resolve().parents[3]
    installed = repository / "worker" / "models" / "temporal" / "sources" / "tapnet"
    if installed.is_dir():
        return installed
    return repository / ".runtime" / "external" / "tapnet"


__all__ = [
    "BidirectionalTapTracks",
    "TAPNEXT_CHECKPOINT_FILENAME",
    "TAPNEXT_MODEL_NAME",
    "TapNextPPBackend",
    "TapTrackSequence",
]
