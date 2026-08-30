"""Run real TAR-ViTPose and TAPNext++ inference without starting a worker."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from worker.src.pose_v6.tapnextpp_backend import TapNextPPBackend
from worker.src.pose_v6.tar_vitpose_backend import TarVitPoseBackend
from worker.src.pose_v6.temporal_expert_fusion import (
    CORE_LIMB_JOINTS,
    TrackerEvidence,
    fuse_core_frame,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path)
    parser.add_argument("--frames", type=int, default=5)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    frames = _frames(args.video, max(5, args.frames))
    height, width = frames[0].shape[:2]
    bbox = np.asarray((width * 0.25, height * 0.05, width * 0.75, height * 0.95), dtype=np.float32)

    tar_path = repository / "worker/models/temporal/tar-vitpose/tarvitpose_b_17.pt"
    tap_path = repository / "worker/models/temporal/tapnextpp/tapnextpp_512.ckpt"
    print(f"TAR_INSTALLED={tar_path.is_file()} TAR_BYTES={tar_path.stat().st_size if tar_path.is_file() else 0}")
    print(f"TAPNEXT_INSTALLED={tap_path.is_file()} TAPNEXT_BYTES={tap_path.stat().st_size if tap_path.is_file() else 0}")
    tar = TarVitPoseBackend(tar_path)
    try:
        observation = tar.infer_window(frames[:5], bbox)
        print(
            f"TAR_OK points={observation.points.shape[0]} "
            f"seconds={observation.inference_seconds:.3f} "
            f"peak_vram_mb={(observation.peak_vram_bytes or 0) / 1024 / 1024:.1f}"
        )
        seeds = observation.points[[5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]]
    finally:
        tar.close()

    tap = TapNextPPBackend(tap_path)
    try:
        tracks = tap.track_bidirectional(frames, seeds, seeds)
        print(
            f"TAPNEXT_OK points={tracks.forward.points.shape[1]} "
            f"frames={tracks.forward.points.shape[0]} "
            f"seconds={tracks.forward.inference_seconds + tracks.backward.inference_seconds:.3f} "
            f"peak_vram_mb={max(tracks.forward.peak_vram_bytes or 0, tracks.backward.peak_vram_bytes or 0) / 1024 / 1024:.1f}"
        )
        middle = len(frames) // 2
        evidence = {
            joint: TrackerEvidence(
                tuple(float(value) for value in tracks.forward.points[middle, offset]),
                tuple(float(value) for value in tracks.backward.points[middle, offset]),
                bool(tracks.forward.visible[middle, offset]),
                bool(tracks.backward.visible[middle, offset]),
            )
            for offset, joint in enumerate(CORE_LIMB_JOINTS)
        }
        primary_points = np.zeros((133, 2), dtype=np.float32)
        primary_scores = np.zeros(133, dtype=np.float32)
        primary_points[:17] = observation.points + np.asarray((1.0, -1.0), dtype=np.float32)
        primary_scores[:17] = np.maximum(observation.scores, 0.85)
        tar_scores = np.maximum(observation.scores, 0.82)
        fusion = fuse_core_frame(
            primary_points, primary_scores,
            observation.points, tar_scores,
            evidence, body_scale=max(height * 0.75, 1.0),
        )
        accepted = sum(decision.accepted for decision in fusion.values())
        finite = all(
            decision.point is not None
            and np.isfinite(np.asarray(decision.point, dtype=float)).all()
            for decision in fusion.values() if decision.accepted
        )
        print(
            f"FUSION_PASS={accepted == len(CORE_LIMB_JOINTS) and finite} "
            f"accepted={accepted} rejected={len(CORE_LIMB_JOINTS) - accepted}"
        )
    finally:
        tap.close()
    return 0


def _frames(video: Path | None, count: int) -> list[np.ndarray]:
    if video is None:
        output = []
        for index in range(count):
            frame = np.zeros((512, 512, 3), dtype=np.uint8)
            cv2.circle(frame, (180 + index * 8, 210), 35, (225, 225, 225), -1)
            cv2.line(frame, (180 + index * 8, 245), (180 + index * 8, 390), (180, 180, 180), 22)
            output.append(frame)
        return output
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    output: list[np.ndarray] = []
    try:
        while len(output) < count:
            success, frame = capture.read()
            if not success or frame is None:
                break
            output.append(frame)
    finally:
        capture.release()
    if len(output) < count:
        raise RuntimeError(f"video contains fewer than {count} readable frames")
    return output


if __name__ == "__main__":
    raise SystemExit(main())
