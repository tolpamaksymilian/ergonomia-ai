"""PTS-aware native video timeline with an explicit constant-FPS fallback."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeFrameTimeline:
    timestamps: tuple[float, ...]
    source: str
    fallback_used: bool
    frame_gap_count: int
    nominal_interval_seconds: float

    def timestamp(self, frame_index: int, fallback_fps: float) -> float:
        if 0 <= frame_index < len(self.timestamps):
            return self.timestamps[frame_index]
        return frame_index / max(fallback_fps, 1e-6)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "fallback_used": self.fallback_used,
            "frame_count": len(self.timestamps),
            "frame_gap_count": self.frame_gap_count,
            "nominal_interval_seconds": round(self.nominal_interval_seconds, 9),
            "hidden_frame_skipping_enabled": False,
            "every_native_frame_processed": True,
        }


def probe_native_frame_timeline(
    video_path: Path,
    *,
    fallback_fps: float,
    expected_frame_count: int,
    timeout_seconds: float = 30.0,
) -> NativeFrameTimeline:
    """Read best-effort presentation timestamps through ffprobe when available."""

    if fallback_fps <= 0.0 or expected_frame_count <= 0:
        raise ValueError("timeline fallback FPS and frame count must be positive")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is not None:
        command = [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "frame=best_effort_timestamp_time",
            "-of", "json",
            str(video_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
            document = json.loads(completed.stdout)
            frames = document.get("frames", []) if isinstance(document, dict) else []
            timestamps = tuple(
                float(item["best_effort_timestamp_time"])
                for item in frames
                if isinstance(item, dict)
                and _finite_number(item.get("best_effort_timestamp_time"))
            )
            if (
                len(timestamps) >= expected_frame_count
                and _strictly_increasing(timestamps[:expected_frame_count])
            ):
                return _build_timeline(
                    timestamps[:expected_frame_count],
                    source="ffprobe-best-effort-pts",
                    fallback_used=False,
                    fallback_fps=fallback_fps,
                )
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            pass
    timestamps = tuple(index / fallback_fps for index in range(expected_frame_count))
    return _build_timeline(
        timestamps,
        source="constant-fps-fallback",
        fallback_used=True,
        fallback_fps=fallback_fps,
    )


def _build_timeline(
    timestamps: tuple[float, ...],
    *,
    source: str,
    fallback_used: bool,
    fallback_fps: float,
) -> NativeFrameTimeline:
    deltas = [
        timestamps[index] - timestamps[index - 1]
        for index in range(1, len(timestamps))
    ]
    nominal = sorted(deltas)[len(deltas) // 2] if deltas else 1.0 / fallback_fps
    gaps = sum(delta > nominal * 1.8 for delta in deltas)
    return NativeFrameTimeline(
        timestamps,
        source,
        fallback_used,
        gaps,
        nominal,
    )


def _finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _strictly_increasing(values: tuple[float, ...]) -> bool:
    return all(
        math.isfinite(value)
        and (index == 0 or value > values[index - 1])
        for index, value in enumerate(values)
    )


__all__ = ["NativeFrameTimeline", "probe_native_frame_timeline"]
