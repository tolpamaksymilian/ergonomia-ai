from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from worker.src.pose_v6.worst_frame_export import (
    build_reason_document,
    export_worst_frames,
    rank_worst_frames,
)


def _write_video(path: Path, colors: list[int]) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48)
    )
    assert writer.isOpened()
    try:
        for color in colors:
            writer.write(np.full((48, 64, 3), color, dtype=np.uint8))
    finally:
        writer.release()


def _pose_document() -> dict[str, object]:
    frames: list[dict[str, object]] = []
    for index, quality in enumerate((0.9, 0.1, 0.7)):
        frames.append(
            {
                "analysis_frame_index": index,
                "source_frame_index": index,
                "source_timestamp_seconds": index / 10,
                "detected": True,
                "raw_keypoints": [[10.0, 12.0]],
                "final_body_state_v68": {
                    "body_quality": quality,
                    "selected_hypothesis_id": f"H{index}",
                    "decision_reasons": ["sequence_level_full_body_selection"],
                },
                "person_silhouette_v68": {
                    "valid": True,
                    "person_contour": [[10, 10], [40, 10], [40, 40], [10, 40]],
                    "quality": {"mask_confidence": 0.8, "rejection_reasons": []},
                },
                "silhouette_evidence_v68": {
                    "mask_influence": 0.6,
                    "skeleton_to_silhouette_alignment_score": 0.9,
                },
            }
        )
    return {"schema_version": "6.0", "frames": frames}


def test_rank_worst_frames_falls_back_to_lowest_body_quality() -> None:
    ranked = rank_worst_frames(_pose_document(), None, limit=2)
    assert [item["frame_index"] for item in ranked] == [1, 2]


def test_reason_document_keeps_required_evidence_without_accuracy_claim() -> None:
    frame = _pose_document()["frames"][1]  # type: ignore[index]
    reason = build_reason_document({"frame_index": 1, "reasons": ["TEST"]}, frame)
    assert reason["raw_rtmw"] == [[10.0, 12.0]]
    assert reason["selected_hypothesis"] == "H1"
    assert reason["silhouette_support"]["alignment_score"] == 0.9
    assert reason["accuracy_claimed"] is False


def test_export_writes_exact_five_artifacts_and_nonempty_mask(tmp_path: Path) -> None:
    source = tmp_path / "source.avi"
    overlay = tmp_path / "overlay.avi"
    _write_video(source, [20, 40, 60])
    _write_video(overlay, [80, 100, 120])
    exported = export_worst_frames(
        source,
        overlay,
        tmp_path / "review",
        _pose_document(),
        None,
        limit=1,
    )
    assert len(exported) == 1
    names = {path.name for path in exported[0].iterdir()}
    assert names == {"original.png", "overlay.png", "debug.png", "mask.png", "reason.json"}
    mask = cv2.imread(str(exported[0] / "mask.png"), cv2.IMREAD_GRAYSCALE)
    assert mask is not None and int(mask.max()) == 255
    reason = json.loads((exported[0] / "reason.json").read_text(encoding="utf-8"))
    assert reason["frame"] == 1
