"""Inference-only TAR-ViTPose Base adapter for Pose V6.7.

The architecture follows the official Apache-2.0 TAR-ViTPose implementation
(CVPR 2026).  It is reproduced here without MMPose's training registries and
compiled MMCV operators, which are not needed for inference and are currently
incompatible with the worker's modern Torch/CUDA runtime.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


TAR_MODEL_NAME = "TAR-ViTPose-B-17"
TAR_INPUT_SIZE = (288, 384)  # width, height
TAR_WINDOW_SIZE = 5
TAR_CHECKPOINT_BYTES = 1_619_532_723


@dataclass(frozen=True)
class TarPoseObservation:
    points: np.ndarray
    scores: np.ndarray
    inference_seconds: float
    peak_vram_bytes: int | None
    model_name: str = TAR_MODEL_NAME
    coordinate_space: str = "ORIGINAL_PIXELS"


class TarVitPoseBackend:
    """Load the official Base checkpoint and infer a five-frame pose window."""

    def __init__(self, checkpoint_path: Path, *, device: str = "cuda") -> None:
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"TAR-ViTPose checkpoint not found: {self.checkpoint_path}")
        if self.checkpoint_path.stat().st_size != TAR_CHECKPOINT_BYTES:
            raise RuntimeError("TAR-ViTPose checkpoint is incomplete or has an unexpected size")
        self.device_name = device
        self._torch = _import_torch()
        if device.startswith("cuda") and not self._torch.cuda.is_available():
            raise RuntimeError("TAR-ViTPose requested CUDA but CUDA is unavailable")
        self.device = self._torch.device(device)
        self.model = _build_tar_model(self._torch)
        checkpoint = self._torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=False,
            mmap=True,
        )
        state = checkpoint.get("model_state_dict", checkpoint)
        if not isinstance(state, dict):
            raise RuntimeError("TAR-ViTPose checkpoint has no model state dictionary")
        missing, unexpected = self.model.load_state_dict(state, strict=False)
        if missing or unexpected:
            raise RuntimeError(
                "TAR-ViTPose checkpoint contract mismatch: "
                f"missing={missing[:5]}, unexpected={unexpected[:5]}"
            )
        del checkpoint, state
        self.model.eval().to(self.device)

    @property
    def input_size(self) -> tuple[int, int]:
        return TAR_INPUT_SIZE

    def infer_window(
        self,
        frames_bgr: Sequence[np.ndarray],
        bbox_xyxy: np.ndarray,
    ) -> TarPoseObservation:
        if len(frames_bgr) != TAR_WINDOW_SIZE:
            raise ValueError(f"TAR-ViTPose requires exactly {TAR_WINDOW_SIZE} frames")
        if any(frame is None or frame.size == 0 for frame in frames_bgr):
            raise ValueError("TAR-ViTPose received an empty frame")
        transform = _crop_transform(
            np.asarray(bbox_xyxy, dtype=np.float32),
            frames_bgr[TAR_WINDOW_SIZE // 2].shape[1],
            frames_bgr[TAR_WINDOW_SIZE // 2].shape[0],
        )
        tensor = self._torch.stack([
            _preprocess(frame, transform, self._torch) for frame in frames_bgr
        ]).unsqueeze(0).to(self.device, non_blocking=True)
        if self.device.type == "cuda":
            self._torch.cuda.reset_peak_memory_stats(self.device)
            self._torch.cuda.synchronize(self.device)
        started = time.perf_counter()
        with self._torch.inference_mode():
            context = (
                self._torch.amp.autocast("cuda", dtype=self._torch.float16)
                if self.device.type == "cuda"
                else self._torch.amp.autocast("cpu", enabled=False)
            )
            with context:
                heatmaps = self.model(tensor)[0].float().cpu().numpy()
        if self.device.type == "cuda":
            self._torch.cuda.synchronize(self.device)
            peak_vram = int(self._torch.cuda.max_memory_allocated(self.device))
        else:
            peak_vram = None
        elapsed = time.perf_counter() - started
        points, scores = _decode_heatmaps(heatmaps, transform)
        return TarPoseObservation(points, scores, elapsed, peak_vram)

    def close(self) -> None:
        model = getattr(self, "model", None)
        if model is not None:
            model.to("cpu")
            del self.model
        if self.device.type == "cuda":
            self._torch.cuda.empty_cache()


@dataclass(frozen=True)
class _CropTransform:
    source_xyxy: tuple[float, float, float, float]
    affine: np.ndarray
    inverse_affine: np.ndarray


def _crop_transform(
    bbox: np.ndarray,
    frame_width: int,
    frame_height: int,
    *,
    padding: float = 1.25,
) -> _CropTransform:
    bbox = np.asarray(bbox, dtype=np.float32).reshape(-1)
    if bbox.size != 4 or not np.isfinite(bbox).all():
        raise ValueError("TAR-ViTPose bbox must contain four finite values")
    x1, y1, x2, y2 = (float(value) for value in bbox)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("TAR-ViTPose bbox must have positive area")
    center_x, center_y = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    width, height = (x2 - x1) * padding, (y2 - y1) * padding
    target_aspect = TAR_INPUT_SIZE[0] / TAR_INPUT_SIZE[1]
    if width / max(height, 1e-6) > target_aspect:
        height = width / target_aspect
    else:
        width = height * target_aspect
    source = np.asarray([
        [center_x - width * 0.5, center_y - height * 0.5],
        [center_x + width * 0.5, center_y - height * 0.5],
        [center_x - width * 0.5, center_y + height * 0.5],
    ], dtype=np.float32)
    destination = np.asarray([
        [0.0, 0.0],
        [float(TAR_INPUT_SIZE[0] - 1), 0.0],
        [0.0, float(TAR_INPUT_SIZE[1] - 1)],
    ], dtype=np.float32)
    affine = cv2.getAffineTransform(source, destination)
    inverse = cv2.invertAffineTransform(affine)
    return _CropTransform(
        (center_x - width * 0.5, center_y - height * 0.5,
         center_x + width * 0.5, center_y + height * 0.5),
        affine,
        inverse,
    )


def _preprocess(frame: np.ndarray, transform: _CropTransform, torch: object):
    crop = cv2.warpAffine(
        frame,
        transform.affine,
        TAR_INPUT_SIZE,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().div_(255.0)
    mean = torch.tensor((0.485, 0.456, 0.406)).view(3, 1, 1)
    std = torch.tensor((0.229, 0.224, 0.225)).view(3, 1, 1)
    return (tensor - mean) / std


def _decode_heatmaps(
    heatmaps: np.ndarray,
    transform: _CropTransform,
) -> tuple[np.ndarray, np.ndarray]:
    if heatmaps.ndim != 3 or heatmaps.shape[0] != 17:
        raise RuntimeError(f"unexpected TAR-ViTPose heatmap shape: {heatmaps.shape}")
    joint_count, height, width = heatmaps.shape
    points = np.zeros((joint_count, 2), dtype=np.float32)
    scores = np.zeros((joint_count,), dtype=np.float32)
    for joint in range(joint_count):
        heatmap = heatmaps[joint]
        flat_index = int(np.argmax(heatmap))
        y, x = divmod(flat_index, width)
        # Quarter-pixel refinement is the decoder convention used by the
        # official Gaussian heatmap head.
        refined_x, refined_y = float(x), float(y)
        if 1 <= x < width - 1:
            refined_x += float(np.sign(heatmap[y, x + 1] - heatmap[y, x - 1])) * 0.25
        if 1 <= y < height - 1:
            refined_y += float(np.sign(heatmap[y + 1, x] - heatmap[y - 1, x])) * 0.25
        crop_point = np.asarray([[
            refined_x * (TAR_INPUT_SIZE[0] / width),
            refined_y * (TAR_INPUT_SIZE[1] / height),
        ]], dtype=np.float32)
        source_point = cv2.transform(crop_point[None, :, :], transform.inverse_affine)[0, 0]
        points[joint] = source_point
        peak = float(heatmap[y, x])
        scores[joint] = float(np.clip(peak, 0.0, 1.0)) if math.isfinite(peak) else 0.0
    return points, scores


def _import_torch():
    try:
        import torch
    except ImportError as error:
        raise RuntimeError("TAR-ViTPose requires the worker Torch runtime") from error
    return torch


def _build_tar_model(torch: object):
    nn = torch.nn

    class PatchEmbed(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.projection = nn.Conv2d(3, 768, 16, stride=16, padding=2)

        def forward(self, value):
            return self.projection(value)

    class ViTAttention(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.qkv = nn.Linear(768, 768 * 3)
            self.proj = nn.Linear(768, 768)

        def forward(self, value):
            batch, tokens, width = value.shape
            qkv = self.qkv(value).reshape(batch, tokens, 3, 12, width // 12)
            qkv = qkv.permute(2, 0, 3, 1, 4)
            query, key, projected_value = qkv.unbind(0)
            attention = (query @ key.transpose(-2, -1)) * ((width // 12) ** -0.5)
            attention = attention.softmax(dim=-1)
            output = (attention @ projected_value).transpose(1, 2).reshape(
                batch, tokens, width,
            )
            return self.proj(output)

    class ViTFFN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.layers = nn.Sequential(
                nn.Sequential(nn.Linear(768, 3072), nn.GELU(), nn.Dropout(0.0)),
                nn.Linear(3072, 768),
                nn.Dropout(0.0),
            )

        def forward(self, value):
            return self.layers(value)

    class ViTBlock(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.ln1 = nn.LayerNorm(768, eps=1e-6)
            self.attn = ViTAttention()
            self.ln2 = nn.LayerNorm(768, eps=1e-6)
            self.ffn = ViTFFN()

        def forward(self, value):
            value = value + self.attn(self.ln1(value))
            return value + self.ffn(self.ln2(value))

    class VisionTransformer(nn.Module):
        """Inference-only ViTPose-B backbone with checkpoint-identical keys."""

        def __init__(self) -> None:
            super().__init__()
            self.pos_embed = nn.Parameter(torch.zeros(1, 16 * 12, 768))
            self.patch_embed = PatchEmbed()
            self.layers = nn.ModuleList([ViTBlock() for _ in range(12)])
            self.ln1 = nn.LayerNorm(768, eps=1e-6)

        def forward(self, value):
            value = self.patch_embed(value)
            height, width = value.shape[-2:]
            value = value.flatten(2).transpose(1, 2)
            position = self.pos_embed.reshape(1, 16, 12, 768).permute(0, 3, 1, 2)
            if (height, width) != (16, 12):
                position = torch.nn.functional.interpolate(
                    position, size=(height, width), mode="bicubic", align_corners=False,
                )
            position = position.flatten(2).transpose(1, 2).to(dtype=value.dtype)
            value = value + position
            for layer in self.layers:
                value = layer(value)
            value = self.ln1(value)
            return (value.transpose(1, 2).reshape(-1, 768, height, width),)

    class CrossAttention(nn.Module):
        def __init__(self, embed_dim: int, num_heads: int) -> None:
            super().__init__()
            self.mha = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
            self.norm = nn.LayerNorm(embed_dim)

        def forward(self, query, context, attn_mask=None):
            output, weight = self.mha(query, context, context, attn_mask=attn_mask)
            return self.norm(query + output), weight

    class SelfAttention(nn.Module):
        def __init__(self, embed_dim: int, num_heads: int) -> None:
            super().__init__()
            self.mha = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
            self.norm = nn.LayerNorm(embed_dim)

        def forward(self, value):
            output, _ = self.mha(value, value, value)
            return self.norm(value + output)

    class FFNLayer(nn.Module):
        def __init__(self, width: int) -> None:
            super().__init__()
            self.fc1 = nn.Linear(width, width * 2)
            self.act = nn.GELU()
            self.fc2 = nn.Linear(width * 2, width)
            self.drop = nn.Dropout(0.0)
            self.norm = nn.LayerNorm(width)

        def forward(self, value):
            residual = value
            value = self.drop(self.fc2(self.act(self.fc1(value))))
            return self.norm(value + residual)

    class HeatmapHead(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.deconv_layers = nn.Sequential(
                nn.ConvTranspose2d(768, 256, 4, 2, 1, bias=False),
                nn.BatchNorm2d(256), nn.ReLU(),
                nn.ConvTranspose2d(256, 256, 4, 2, 1, bias=False),
                nn.BatchNorm2d(256), nn.ReLU(),
            )
            self.final_layer = nn.Conv2d(256, 17, 1)

    class InnerPose(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = VisionTransformer()
            self.head = HeatmapHead()

    class TarVitPose(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.model = InnerPose()
            self.backbone = self.model.backbone
            self.heatmap_head = nn.Sequential(
                self.model.head.deconv_layers, self.model.head.final_layer,
            )
            self.query_feat = nn.Embedding(17, 768)
            self.query_pe = nn.Embedding(17, 768)
            self.masked_attention_layers = nn.ModuleList([
                CrossAttention(768, 4) for _ in range(6)
            ])
            self.self_attention_layers = nn.ModuleList([
                SelfAttention(768, 4) for _ in range(6)
            ])
            self.ffn_layers = nn.ModuleList([FFNLayer(768) for _ in range(6)])
            self.cross_attention = CrossAttention(768, 4)

        def _attention_mask(self, heatmap):
            minimum = heatmap.amin(dim=(2, 3), keepdim=True)
            maximum = heatmap.amax(dim=(2, 3), keepdim=True)
            normalized = (heatmap - minimum) / (maximum - minimum + 1e-6)
            normalized = torch.nn.functional.interpolate(
                normalized, size=(24, 18), mode="bilinear", align_corners=False,
            )
            mask = normalized.lt(0.2).reshape(-1, 5, 17, 24, 18)
            return mask.flatten(3).unsqueeze(1).repeat(1, 4, 1, 1, 1).flatten(0, 1).detach()

        def forward(self, value):
            batch, frames, channels, height, width = value.shape
            features = self.backbone(value.view(-1, channels, height, width))[0]
            features = features.view(batch * frames, 768, 24, 18)
            initial = self.heatmap_head(features)
            mask = self._attention_mask(initial).reshape(-1, 17, frames, 24 * 18).flatten(2)
            features = features.view(batch, frames, 768, 24, 18)
            output = self.query_feat.weight.unsqueeze(0).repeat(batch, 1, 1)
            output = output + self.query_pe.weight.unsqueeze(0).repeat(batch, 1, 1)
            tokens = features.flatten(3).reshape(batch, frames, 24 * 18, 768)
            center = tokens[:, frames // 2]
            context = tokens.flatten(1, 2)
            for cross, self_attention, ffn in zip(
                self.masked_attention_layers,
                self.self_attention_layers,
                self.ffn_layers,
            ):
                output, _ = cross(output, context, attn_mask=mask)
                output = self_attention(output)
                output = ffn(output)
            center, _ = self.cross_attention(center, output)
            return self.heatmap_head(center.view(batch, 768, 24, 18))

    return TarVitPose()


__all__ = [
    "TAR_INPUT_SIZE",
    "TAR_MODEL_NAME",
    "TAR_WINDOW_SIZE",
    "TarPoseObservation",
    "TarVitPoseBackend",
]
