import cv2
import numpy as np

from worker.src.scene_detection.processor import analyze_scene_geometry, build_detection_document, normalize_detections


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
    assert document["detection_version"] == "scene-detection-v0.2-beta.1"
    assert document["candidates"][0]["source_class"] == "chair"
    assert "no_ergonomic_assessment" in document["limitations"]


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
