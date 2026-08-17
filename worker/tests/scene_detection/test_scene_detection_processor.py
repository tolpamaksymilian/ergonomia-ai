import cv2
import numpy as np

from worker.src.scene_detection.processor import (
    analyze_scene_geometry,
    build_detection_document,
    extract_user_annotations,
    filter_candidates_against_user_annotations,
    normalize_detections,
)


def test_zero_detections_is_valid_result():
    assert normalize_detections([], [], image_width=1000, image_height=500) == []


def test_one_supported_detection_is_normalized():
    result = normalize_detections([[100, 50, 500, 300]], [60], image_width=1000, image_height=500)
    assert len(result) == 1
    assert result[0].source_class == "dining table"
    assert result[0].suggested_scene_type == "TABLE"
    assert result[0].bounding_box.x == 0.1


def test_multiple_and_overlapping_duplicates_are_stable():
    result = normalize_detections([[0, 0, 200, 200], [2, 2, 198, 198], [300, 20, 500, 200]], [56, 56, 62], image_width=600, image_height=300)
    assert len(result) == 2


def test_unsupported_class_is_not_invented():
    assert normalize_detections([[0, 0, 100, 100]], [0], image_width=100, image_height=100) == []


def test_document_keeps_source_class_and_limitations():
    candidates = normalize_detections([[0, 0, 100, 100]], [56], image_width=100, image_height=100)
    document = build_detection_document("analysis", 100, 100, candidates)
    assert document["detection_version"] == "scene-detection-v0.3-beta.1"
    assert document["candidates"][0]["source_class"] == "chair"
    assert "no_ergonomic_assessment" in document["limitations"]
    assert document["result_status"] == "SUCCESS"


def test_zero_detections_is_explicit_success_no_objects():
    document = build_detection_document("analysis", 100, 100, [])
    assert document["result_status"] == "SUCCESS_NO_OBJECTS"


def test_lightweight_geometry_pass_finds_lines_without_ml():
    image = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.line(image, (40, 330), (560, 330), (255, 255, 255), 4)
    cv2.line(image, (100, 50), (100, 350), (255, 255, 255), 4)
    result = analyze_scene_geometry(image, [])
    orientations = {item["orientation"] for item in result["geometry_candidates"]}
    assert "HORIZONTAL" in orientations
    assert "VERTICAL" in orientations
    assert result["floor_candidates"]


def test_table_gets_width_height_and_depth_suggestions_without_values():
    candidates = normalize_detections([[100, 80, 500, 300]], [60], image_width=600, image_height=400)
    result = analyze_scene_geometry(np.zeros((400, 600, 3), dtype=np.uint8), candidates)
    suggestions = result["dimension_suggestions"]
    types = {item["dimension_type"] for item in suggestions}
    assert {"workSurfaceHeightCm", "widthCm", "depthCm"} <= types
    assert all(item["estimated_value_cm"] is None for item in suggestions)
    depth = next(item for item in suggestions if item["dimension_type"] == "depthCm")
    assert depth["estimate_status"] == "UNKNOWN"
    assert depth["evidence_quality"] == "LOW"


def test_v02_document_contains_optional_geometry_contract():
    geometry = {"geometry_candidates": [], "dimension_suggestions": [], "perspective_evidence": {"evidence_quality": "LOW"}, "floor_candidates": [], "surface_candidates": []}
    document = build_detection_document("analysis", 100, 100, [], geometry)
    assert set(("geometry_candidates", "dimension_suggestions", "perspective_evidence", "floor_candidates", "surface_candidates")) <= document.keys()


def test_guided_context_contains_all_manual_constraints_without_human_or_assessment_data():
    scene = {
        "regions": [
            {"id": "floor", "type": "FLOOR_REGION", "source": "USER_PROVIDED"},
            {"id": "movement", "type": "MOVEMENT_ZONE", "source": "USER_PROVIDED"},
            {"id": "surface", "type": "WORK_SURFACE", "source": "USER_PROVIDED"},
        ],
        "calibration": {"references": [
            {"id": "h1", "axis": "VERTICAL", "active": True},
            {"id": "h2", "axis": "VERTICAL", "active": True},
            {"id": "w1", "axis": "HORIZONTAL", "active": True},
        ]},
        "objects": [{"id": "table", "source": "USER", "status": "USER_ADDED", "bbox": {"x": .1, "y": .2, "width": .6, "height": .5}}],
        "constraintGraph": {"version": "scene-constraint-graph-v1.0", "nodes": [], "constraints": [{"id": "c", "source": "USER_PROVIDED"}]},
        "humans": [{"id": "must-not-leak"}],
        "technicalInsights": [{"id": "must-not-leak"}],
    }
    context = extract_user_annotations(scene, "revision")
    assert len(context["floor_regions"]) == 1
    assert len(context["movement_zones"]) == 1
    assert len(context["height_references"]) == 2
    assert len(context["dimension_references"]) == 1
    assert len(context["manual_objects"]) == 1
    assert len(context["manual_surfaces"]) == 1
    assert len(context["constraint_graph"]["constraints"]) == 1
    assert "humans" not in context and "technicalInsights" not in context


def test_manual_object_suppresses_overlapping_detector_candidate_but_keeps_new_object():
    candidates = normalize_detections([[100, 100, 500, 400], [700, 100, 900, 300]], [62, 56], image_width=1000, image_height=500)
    annotations = {"manual_objects": [{"bbox": {"x": .09, "y": .19, "width": .43, "height": .63}}]}
    filtered = filter_candidates_against_user_annotations(candidates, annotations)
    assert len(filtered) == 1
    assert filtered[0].suggested_scene_type == "CHAIR"


def test_detection_document_reports_annotation_counts_not_full_manual_state():
    annotations = {
        "scene_revision": "revision", "floor_regions": [{}], "movement_zones": [{}],
        "height_references": [{}, {}], "dimension_references": [{}], "manual_objects": [{}],
        "manual_surfaces": [{}], "constraint_graph": {"constraints": [{}, {}]},
    }
    document = build_detection_document("analysis", 100, 100, [], user_annotations=annotations)
    context = document["user_annotation_context"]
    assert context["height_reference_count"] == 2
    assert context["constraint_count"] == 2
    assert "manual_objects" not in context
