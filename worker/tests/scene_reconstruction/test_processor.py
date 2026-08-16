from __future__ import annotations

import copy

import pytest

from worker.src.scene_reconstruction.processor import (
    ReconstructionInputError,
    build_reconstruction_input,
    reconstruct_scene,
    reconstruction_summary,
)


def point(x: float, y: float) -> dict[str, object]:
    raw = {"x": x, "y": y}
    return {"raw": raw, "snapped": None, "effective": dict(raw), "snapSourceId": None, "snapDistancePx": None}


def constraint(identifier: str, kind: str, value: float, *, segment: bool = False) -> dict[str, object]:
    return {
        "id": identifier, "type": kind, "nodeIds": [], "objectId": "table", "regionId": "top",
        "target": {"kind": "OBJECT", "id": "table", "point": None}, "rawValue": value,
        "effectiveValue": value, "unit": "cm", "source": "USER_PROVIDED", "weight": 1,
        "useForSolver": True, "status": "ACTIVE", "residual": None,
        "imageSegment": {"start": {"x": .3, "y": .8}, "end": {"x": .3, "y": .8 - value * 2 / 900}} if segment else None,
    }


def scene(*, heights: list[float] | None = None, depth: bool = True) -> dict[str, object]:
    heights = heights or [80, 80, 80, 80]
    constraints = [constraint(f"h-{index}", "HEIGHT", value, segment=True) for index, value in enumerate(heights)]
    constraints.append(constraint("width", "WIDTH", 160))
    if depth:
        constraints.append(constraint("depth", "DEPTH", 70))
    return {
        "schema_version": "1.5",
        "objects": [{"id": "table", "name": "Blat", "status": "USER_CONFIRMED", "shapeAssumptions": ["RECTANGULAR", "PLANAR"]}],
        "regions": [
            {"id": "floor", "type": "FLOOR_REGION", "quality": "HIGH", "polygonImageNormalized": [point(.1, .7), point(.9, .7), point(.95, .95), point(.05, .95)]},
            {"id": "top", "type": "WORK_SURFACE", "associatedObjectId": "table", "quality": "HIGH", "polygonImageNormalized": [point(.2, .3), point(.8, .3), point(.7, .5), point(.25, .5)]},
        ],
        "planes": [], "calibration": {"references": []},
        "constraintGraph": {"version": "scene-constraint-graph-v1.0", "nodes": [], "constraints": constraints},
    }


def solve(value: dict[str, object]) -> dict[str, object]:
    source = build_reconstruction_input(value, None, scene_revision="fixture", image_width=1200, image_height=900)
    return reconstruct_scene(source)


def test_complete_table_is_solved_without_guessing_dimensions() -> None:
    result = solve(scene())
    assert result["status"] == "SOLVED"
    assert result["derivedDimensions"]["table"] == {"heightCm": 80.0, "widthCm": 160.0, "depthCm": 70.0}
    top_plane = next(item for item in result["planes"] if item["regionId"] == "top")
    assert len(top_plane["homography"]) == 9
    assert top_plane["homography"] != [1, 0, 0, 0, 1, 0, 0, 0, 1]


def test_projective_floor_maps_movement_zone_into_world_centimeters() -> None:
    value = scene()
    value["regions"].append({
        "id": "move", "type": "MOVEMENT_ZONE", "quality": "HIGH",
        "polygonImageNormalized": [point(.2, .75), point(.8, .75), point(.85, .9), point(.15, .9)],
    })
    ground_width = constraint("ground-width", "WIDTH", 240)
    ground_depth = constraint("ground-depth", "DEPTH", 180)
    for item in (ground_width, ground_depth):
        item["objectId"] = None
        item["regionId"] = "floor"
    value["constraintGraph"]["constraints"].extend([ground_width, ground_depth])
    result = solve(value)
    movement = result["worldGeometry"]["region:move"]
    assert movement["status"] == "PROJECTIVE"
    assert len(movement["polygonCm"]) == 4
    assert all(point["y"] == 0.0 for point in movement["polygonCm"])


def test_outlier_height_is_isolated() -> None:
    result = solve(scene(heights=[80, 80, 80, 300]))
    assert result["outlierConstraintIds"] == ["h-3"]
    assert result["derivedDimensions"]["table"]["heightCm"] == 80.0


def test_width_constraints_do_not_change_vertical_scale() -> None:
    value = scene()
    before = solve(value)["verticalScaleModel"]["pixelsPerCm"]
    value["constraintGraph"]["constraints"].extend(constraint(f"extra-width-{index}", "WIDTH", 150 + index) for index in range(20))
    assert solve(value)["verticalScaleModel"]["pixelsPerCm"] == before


def test_spatial_heights_create_local_inverse_affine_vertical_scale() -> None:
    value = scene()
    heights = [item for item in value["constraintGraph"]["constraints"] if item["type"] == "HEIGHT"][:3]
    value["constraintGraph"]["constraints"] = [item for item in value["constraintGraph"]["constraints"] if item["type"] != "HEIGHT"] + heights
    for index, (item, center_y) in enumerate(zip(heights, (.25, .5, .75))):
        pixels_per_cm = 1 / (.42 + .16 * center_y)
        half = 80 * pixels_per_cm / 900 / 2
        item["id"] = f"perspective-{index}"
        item["imageSegment"] = {"start": {"x": .3 + index * .15, "y": center_y + half}, "end": {"x": .3 + index * .15, "y": center_y - half}}
    result = solve(value)
    assert result["verticalScaleModel"]["kind"] == "INVERSE_AFFINE_VERTICAL"
    assert len(result["verticalScaleModel"]["coefficients"]) == 2


def test_missing_depth_is_partial_and_requests_exact_depth() -> None:
    result = solve(scene(depth=False))
    assert result["readiness"]["HUMAN_PLACEMENT"]["status"] == "READY"
    assert result["readiness"]["COLLISION"]["status"] == "NEEDS_DEPTH"
    assert result["nextBestMeasurements"][0]["measurementKind"] == "OBJECT_DEPTH"


def test_region_without_dimensions_is_explicitly_underdetermined() -> None:
    value = scene()
    value["constraintGraph"]["constraints"] = []
    result = solve(value)
    assert result["status"] == "UNDERDETERMINED"
    assert len(result["nextBestMeasurements"]) == 1
    assert result["nextBestMeasurements"][0]["measurementKind"] == "VERTICAL_HEIGHT"


def test_self_intersection_is_repaired_with_raw_audit() -> None:
    value = scene()
    polygon = [point(.2, .3), point(.8, .7), point(.8, .3), point(.2, .7)]
    value["regions"][1]["polygonImageNormalized"] = polygon
    result = solve(value)
    assert result["autoRepairs"][0]["type"] == "POLYGON_ORDER"
    assert result["autoRepairs"][0]["before"] == [item["raw"] for item in polygon]


def test_two_conflicting_user_widths_do_not_mutate_raw_values() -> None:
    value = scene()
    value["constraintGraph"]["constraints"] = [item for item in value["constraintGraph"]["constraints"] if item["type"] != "WIDTH"]
    first, second = constraint("front", "WIDTH", 120), constraint("back", "WIDTH", 220)
    value["constraintGraph"]["constraints"].extend([first, second])
    result = solve(value)
    assert result["status"] == "INCONSISTENT"
    assert first["rawValue"] == 120 and second["rawValue"] == 220


def test_summary_excludes_full_source_state() -> None:
    summary = reconstruction_summary(solve(scene()))
    assert "reconstructionState" in summary
    assert "constraintGraph" not in summary
    assert "regions" not in summary


def test_old_schema_is_rejected_by_worker_and_normalized_by_application() -> None:
    value = copy.deepcopy(scene())
    value["schema_version"] = "1.4"
    with pytest.raises(ReconstructionInputError, match="unsupported_scene_schema"):
        build_reconstruction_input(value, None, scene_revision="fixture", image_width=1200, image_height=900)


def test_mirrored_legacy_reference_is_not_added_twice() -> None:
    value = scene()
    mirrored = value["constraintGraph"]["constraints"][0]
    mirrored["target"] = {"kind": "EDGE", "id": "reference-1", "point": None}
    value["calibration"]["references"] = [{
        "id": "reference-1", "semanticStatus": "CONFIRMED", "active": True,
        "axis": "VERTICAL", "valueCm": 80, "objectId": "table", "useForCalibration": True,
        "start": {"x": .3, "y": .8}, "end": {"x": .3, "y": .62},
    }]
    source = build_reconstruction_input(value, None, scene_revision="fixture", image_width=1200, image_height=900)
    identifiers = [item["target"].get("id") for item in source["constraintGraph"]["constraints"]]
    assert identifiers.count("reference-1") == 1
