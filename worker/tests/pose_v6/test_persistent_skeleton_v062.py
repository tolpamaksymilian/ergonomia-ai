from __future__ import annotations

import numpy as np

from worker.src.pose_v6.render_continuity import PersistentBoneRenderer, summarize_render_sources


MAIN = ("shoulders", "left_upper_arm", "left_forearm", "right_upper_arm", "right_forearm", "hips", "left_thigh", "left_lower_leg", "right_thigh", "right_lower_leg")


def test_main_skeleton_stays_visible_through_single_missing_measurement() -> None:
    renderer = PersistentBoneRenderer(persistence_seconds=.5, minimum_quality=.35)
    frames = []
    for frame_index in range(3):
        current = {}
        for offset, name in enumerate(MAIN):
            first = None if frame_index == 1 and name == "left_forearm" else np.asarray((20 + offset, 20), dtype=np.float32)
            second = None if first is None else np.asarray((30 + offset, 30), dtype=np.float32)
            current[name] = renderer.update(name, first, second, first_source="MEASURED", second_source="MEASURED", confidence=.9 if first is not None else 0, timestamp_seconds=frame_index * .1, bbox=np.asarray((0, 0, 100, 180)), expected_length=15, frame_width=200, frame_height=200)
        frames.append(current)
    summary = summarize_render_sources(frames, eligible_frames=[True, True, True])
    assert summary["main_skeleton_render_coverage_ratio"] == 1.0
    assert summary["single_frame_bone_flicker_count"] == 0
    assert frames[1]["left_forearm"].visibility_state == "VISIBLE_PREDICTED"
