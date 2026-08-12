from worker.src.scene_detection.processor import build_detection_document, normalize_detections


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
    assert document["detection_version"] == "scene-detection-v0.1-beta.1"
    assert document["candidates"][0]["source_class"] == "chair"
    assert "no_ergonomic_assessment" in document["limitations"]
