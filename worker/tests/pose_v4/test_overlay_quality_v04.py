from __future__ import annotations

import math

import numpy as np
import pytest

from worker.src.pose_v4.hand_graph import (
    HandGraphConfig,
    PalmScaleProfile,
    analyze_hand_graph_frame,
)
from worker.src.pose_v4.overlay import (
    BoneRenderController,
    BoneRenderPhase,
    MetricColorHysteresis,
    OverlayConfig,
    VisualSeverity,
    classify_metric_severity,
    safe_bone_segment,
)
from worker.src.pose_v4.quality import (
    ImageQualityV2,
    RegionQuality,
    analyze_image_quality_v2,
    build_frame_quality_v2,
    summarize_quality_v2,
)

from .conftest import make_hand_v4


@pytest.mark.parametrize(
    ("metric", "value", "expected"),
    [
        ("trunk_inclination_deg", 5.0, VisualSeverity.NEUTRAL),
        ("trunk_inclination_deg", 20.0, VisualSeverity.MILD),
        ("trunk_inclination_deg", 35.0, VisualSeverity.ELEVATED),
        ("trunk_inclination_deg", 60.0, VisualSeverity.STRONG),
        ("left_upper_arm_elevation_deg", 10.0, VisualSeverity.NEUTRAL),
        ("left_upper_arm_elevation_deg", 35.0, VisualSeverity.MILD),
        ("left_upper_arm_elevation_deg", 70.0, VisualSeverity.ELEVATED),
        ("left_upper_arm_elevation_deg", 110.0, VisualSeverity.STRONG),
        ("left_elbow_flexion_deg", 90.0, VisualSeverity.NEUTRAL),
        ("left_elbow_flexion_deg", 0.0, VisualSeverity.STRONG),
    ],
)
def test_geometric_visual_severity_bands(metric, value, expected):
    assert classify_metric_severity(metric, value, True, 0.9) == expected


@pytest.mark.parametrize(
    "value,valid,quality",
    [(None, False, 0.0), (20.0, False, 0.9), (20.0, True, 0.1), (math.nan, True, 0.9)],
)
def test_invalid_or_low_quality_metric_is_gray_unknown(value, valid, quality):
    assert classify_metric_severity(
        "trunk_inclination_deg", value, valid, quality
    ) == VisualSeverity.UNKNOWN


def test_unknown_metric_has_no_invented_color_band():
    assert classify_metric_severity("invented_metric", 50.0, True, 1.0) == VisualSeverity.UNKNOWN


def test_color_hysteresis_requires_confirmation():
    state = MetricColorHysteresis(confirmation_frames=2)
    assert state.update("trunk_inclination_deg", 0.0, True, 1.0, minimum_quality=0.5) == VisualSeverity.NEUTRAL
    assert state.update("trunk_inclination_deg", 60.0, True, 1.0, minimum_quality=0.5) == VisualSeverity.NEUTRAL
    assert state.update("trunk_inclination_deg", 60.0, True, 1.0, minimum_quality=0.5) == VisualSeverity.STRONG


def test_unknown_color_bypasses_hysteresis_for_safety():
    state = MetricColorHysteresis(confirmation_frames=3)
    state.update("trunk_inclination_deg", 0.0, True, 1.0, minimum_quality=0.5)
    assert state.update("trunk_inclination_deg", None, False, 0.0, minimum_quality=0.5) == VisualSeverity.UNKNOWN


@pytest.mark.parametrize(
    "first,second",
    [
        (None, np.array([1, 1])),
        (np.array([1, 1]), None),
        (np.array([math.nan, 1]), np.array([2, 2])),
        (np.array([math.inf, 1]), np.array([2, 2])),
        (np.array([10, 10]), np.array([10, 10])),
        (np.array([-1, 10]), np.array([20, 20])),
        (np.array([10, 10]), np.array([641, 20])),
    ],
)
def test_render_safety_rejects_invalid_endpoints(first, second):
    assert not safe_bone_segment(
        "left_forearm", first, second, body_scale=500, expected_length=100,
        frame_width=640, frame_height=600,
    )


def test_render_safety_accepts_normal_segment():
    assert safe_bone_segment(
        "left_forearm", np.array([100, 100]), np.array([140, 150]),
        body_scale=500, expected_length=65, frame_width=640, frame_height=600,
    )


@pytest.mark.parametrize("end", [(600, 500), (500, 100), (100, 550)])
def test_render_safety_never_allows_half_screen_line(end):
    assert not safe_bone_segment(
        "left_forearm", np.array([100, 100]), np.asarray(end),
        body_scale=500, expected_length=65, frame_width=640, frame_height=600,
    )


def test_bone_controller_fades_last_good_geometry_not_bad_new_geometry():
    controller = BoneRenderController(OverlayConfig(fade_frames=2, render_quality_threshold=0.5))
    good = controller.update(
        "left_forearm", np.array([100, 100]), np.array([140, 150]),
        valid=True, render_confidence=0.9, body_scale=500, expected_length=65,
        frame_width=640, frame_height=600, severity=VisualSeverity.NEUTRAL,
    )
    bad = controller.update(
        "left_forearm", np.array([100, 100]), np.array([620, 580]),
        valid=True, render_confidence=0.9, body_scale=500, expected_length=65,
        frame_width=640, frame_height=600, severity=VisualSeverity.STRONG,
    )
    assert good.phase == BoneRenderPhase.FADING_IN
    assert bad.phase == BoneRenderPhase.HIDDEN
    assert bad.second is None
    assert bad.safety_rejected


def test_fade_out_reaches_hidden_after_configured_frames():
    controller = BoneRenderController(OverlayConfig(fade_frames=2, render_quality_threshold=0.5))
    kwargs = dict(
        name="left_forearm", body_scale=500, expected_length=65,
        frame_width=640, frame_height=600, severity=VisualSeverity.NEUTRAL,
    )
    controller.update(first=np.array([100, 100]), second=np.array([140, 150]), valid=True, render_confidence=0.9, **kwargs)
    controller.update(first=np.array([100, 100]), second=np.array([140, 150]), valid=True, render_confidence=0.9, **kwargs)
    first = controller.update(first=None, second=None, valid=False, render_confidence=0.0, **kwargs)
    second = controller.update(first=None, second=None, valid=False, render_confidence=0.0, **kwargs)
    assert first.phase == BoneRenderPhase.FADING_OUT
    assert second.phase == BoneRenderPhase.HIDDEN


@pytest.mark.parametrize(
    "field,value",
    [
        ("render_quality_threshold", -0.1),
        ("metric_quality_threshold", 1.1),
        ("fade_frames", 9),
        ("maximum_expected_length_ratio", 1.0),
        ("maximum_diagonal_ratio", 1.0),
    ],
)
def test_invalid_overlay_config_fails_fast(field, value):
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(OverlayConfig(), **{field: value}).validate()


def test_local_image_quality_contains_body_and_hand_regions():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    image[:, ::2] = 255
    quality = analyze_image_quality_v2(
        image,
        body_roi=(20, 10, 140, 115),
        left_hand_roi=(0, 0, 40, 40),
        right_hand_roi=(120, 0, 160, 40),
    )
    assert quality.body_quality.available
    assert quality.left_hand_quality.available
    assert quality.right_hand_quality.available
    assert 0.0 <= quality.global_quality.blur_quality <= 1.0


def test_empty_local_roi_is_explicitly_unavailable():
    quality = analyze_image_quality_v2(
        np.zeros((20, 20, 3), dtype=np.uint8),
        body_roi=None,
        left_hand_roi=(10, 10, 10, 10),
        right_hand_roi=None,
    )
    assert quality.left_hand_quality.available is False
    assert quality.left_hand_quality.blur_quality == 0.0


def _hand_graph(body, side="left"):
    return analyze_hand_graph_frame(
        side, make_hand_v4(), body, [], None, PalmScaleProfile(), None, HandGraphConfig()
    )


def test_frame_quality_v2_propagates_distinct_components(graph_factory):
    _, body = graph_factory()
    region = RegionQuality(True, 0.8, 0.9, False, False, False)
    image = ImageQualityV2(region, region, region, region)
    quality = build_frame_quality_v2(
        image, body=body, left_hand=_hand_graph(body),
        right_hand=_hand_graph(body, "right"), tracking_identity_score=0.9,
    )
    assert set(quality.components) == {
        "body", "body_coverage", "limb_visibility", "hands", "blur",
        "local_hand_blur", "exposure", "tracking", "occlusion",
    }
    assert 0.0 <= quality.score <= 1.0


@pytest.mark.parametrize(
    "code,kwargs",
    [
        ("HIGH_MOTION_BLUR", {"motion_blur": True}),
        ("UNDEREXPOSED", {"underexposed": True}),
        ("OVEREXPOSED", {"overexposed": True}),
    ],
)
def test_frame_quality_uses_controlled_image_warning_codes(code, kwargs, graph_factory):
    _, body = graph_factory()
    values = dict(available=True, blur_quality=0.2, exposure_quality=0.2, motion_blur=False, underexposed=False, overexposed=False)
    values.update(kwargs)
    region = RegionQuality(**values)
    image = ImageQualityV2(region, region, region, region)
    quality = build_frame_quality_v2(
        image, body=body, left_hand=_hand_graph(body),
        right_hand=_hand_graph(body, "right"), tracking_identity_score=0.9,
    )
    assert code in quality.reasons


def test_quality_summary_emits_requested_operational_warnings(graph_factory):
    _, body = graph_factory()
    region = RegionQuality(True, 0.1, 0.8, True, False, False)
    image = ImageQualityV2(region, region, region, region)
    frame = build_frame_quality_v2(
        image, body=body, left_hand=_hand_graph(body),
        right_hand=_hand_graph(body, "right"), tracking_identity_score=0.8,
    )
    summary = summarize_quality_v2(
        [frame] * 10, track_losses=3, hand_assignment_switches=3,
        finger_rejections=30, holding_uncertain_seconds=2.0,
    )
    assert {"EXCESSIVE_TRACK_LOSS", "EXCESSIVE_HAND_SWAP_RISK", "HIGH_FINGER_REJECTION", "HIGH_MOTION_BLUR", "HOLDING_LOW_CONFIDENCE"} <= set(summary["warning_codes"])
