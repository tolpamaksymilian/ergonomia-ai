from __future__ import annotations

from worker.src.pose_v4.overlay_layout import LabelRequest, place_overlay_labels
from worker.src.pose_v4.overlay import overlay_dimensions


def test_label_layout_avoids_overlap_when_space_is_available() -> None:
    layout = place_overlay_labels([
        LabelRequest("trunk", (100, 100), (80, 26), 3),
        LabelRequest("neck", (104, 104), (70, 26), 3),
        LabelRequest("elbow", (110, 110), (75, 26), 2),
    ], 640, 480)
    visible = [item.bounds for item in layout.labels if item.visible]
    assert len(visible) == 3
    for index, first in enumerate(visible):
        for second in visible[index + 1:]:
            assert first[2] <= second[0] or second[2] <= first[0] or first[3] <= second[1] or second[3] <= first[1]
    assert layout.overlap_count == 0


def test_label_layout_reports_suppressed_labels_in_tiny_safe_area() -> None:
    requests = [LabelRequest(str(index), (50, 50), (70, 28), index) for index in range(10)]
    layout = place_overlay_labels(requests, 120, 90)
    assert layout.overlap_count > 0
    assert 0.0 <= layout.readability_score < 1.0


def test_primary_metric_priority_wins_collision() -> None:
    layout = place_overlay_labels([
        LabelRequest("wrist", (50, 50), (90, 30), 1),
        LabelRequest("trunk", (50, 50), (90, 30), 3),
    ], 130, 70)
    trunk = next(item for item in layout.labels if item.key == "trunk")
    assert trunk.visible is True


def test_standard_overlay_uses_thicker_scalable_bones_and_joints() -> None:
    assert overlay_dimensions(480) == (3, 3)
    assert overlay_dimensions(1080) == (6, 6)
    assert overlay_dimensions(2160) == (10, 11)
