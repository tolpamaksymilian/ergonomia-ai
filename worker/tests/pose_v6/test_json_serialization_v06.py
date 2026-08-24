from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import pytest

from worker.src.json_utils import JsonSerializationError, make_json_safe
from worker.src.pose_v5.holding import (
    HoldingEvidenceV3,
    HoldingFrameV3,
    HoldingStateV3,
    bimanual_holding_v3,
)
from worker.src.pose_v6.serialization import (
    PoseOutputSerializationError,
    serialize_pose_document,
    write_pose_document,
)
from worker.src.pose_v6.temporal_reconstruction import (
    PointSource,
    TemporalFrame,
    validate_analysis_bones,
)


class _MotionState(StrEnum):
    FAST = "FAST_MOTION"


@dataclass(frozen=True)
class _DiagnosticSample:
    accepted: np.bool_
    count: np.int64


class _UnknownValue:
    pass


def test_make_json_safe_normalizes_approved_numpy_and_python_types() -> None:
    payload = {
        "analysis_usable": np.bool_(True),
        "frame_count": np.int64(12),
        "quality": np.float32(0.75),
        "double_quality": np.float64(0.625),
        "flags": np.array([True, False], dtype=np.bool_),
        "keypoints": np.array([[1.25, 2.5], [3.75, 4.0]], dtype=np.float32),
        "motion": _MotionState.FAST,
        "path": Path("pose-diagnostics.json"),
        "tuple_value": (np.int32(1), np.float64(2.0)),
        "dataclass_value": _DiagnosticSample(np.bool_(False), np.int64(3)),
    }

    safe = make_json_safe(payload)

    assert safe["analysis_usable"] is True
    assert safe["frame_count"] == 12
    assert type(safe["frame_count"]) is int
    assert safe["quality"] == pytest.approx(0.75)
    assert type(safe["quality"]) is float
    assert safe["double_quality"] == pytest.approx(0.625)
    assert type(safe["double_quality"]) is float
    assert safe["flags"] == [True, False]
    assert safe["keypoints"] == [[1.25, 2.5], [3.75, 4.0]]
    assert safe["motion"] == "FAST_MOTION"
    assert safe["path"] == "pose-diagnostics.json"
    assert safe["tuple_value"] == [1, 2.0]
    assert safe["dataclass_value"] == {"accepted": False, "count": 3}
    json.dumps(safe, allow_nan=False)


@pytest.mark.parametrize(
    "value",
    [np.float32(np.nan), float("nan"), np.float64(np.inf), float("-inf")],
)
def test_make_json_safe_maps_non_finite_measurements_to_null(value: float) -> None:
    safe = make_json_safe({"measurement": value})

    assert safe == {"measurement": None}
    assert json.dumps(safe, allow_nan=False) == '{"measurement": null}'


def test_make_json_safe_rejects_unknown_object_with_exact_path() -> None:
    document = {"frames": [{}, {"temporal": {"foo": _UnknownValue()}}]}

    with pytest.raises(JsonSerializationError) as raised:
        make_json_safe(document)

    assert raised.value.path == "$.frames[1].temporal.foo"
    assert raised.value.python_type.endswith("._UnknownValue")
    assert "type=_UnknownValue" in str(raised.value)


def test_make_json_safe_rejects_non_string_dictionary_key() -> None:
    with pytest.raises(JsonSerializationError, match="dictionary_key_must_be_string") as raised:
        make_json_safe({np.int64(7): "value"})

    assert raised.value.path == "$.<key>"


def test_make_json_safe_rejects_cyclic_container() -> None:
    values: list[object] = []
    values.append(values)

    with pytest.raises(JsonSerializationError, match="cyclic_reference") as raised:
        make_json_safe({"values": values})

    assert raised.value.path == "$.values[0]"


def _representative_pose_document() -> dict[str, object]:
    return {
        "schema_version": "6.0",
        "analysis_id": "analysis-test",
        "summary": {
            "temporal_v6": {
                "analysis_usable_coverage_ratio": np.float32(0.75),
                "quality_summary_valid": np.bool_(True),
            },
            "render_v6": {
                "render_bone_coverage_ratio": np.float64(0.8),
            },
        },
        "frames": [
            {
                "source_frame_index": np.int64(137),
                "motion_v6": {
                    "state": _MotionState.FAST,
                    "fast_motion_detected": np.bool_(True),
                },
                "temporal_v6": {
                    "joint_provenance": [PointSource.MEASURED, PointSource.INTERPOLATED],
                    "analysis_usable": np.array([True, False], dtype=np.bool_),
                    "analysis_bones": {
                        "left_forearm": {
                            "valid": np.bool_(True),
                            "length_pixels": np.float32(52.25),
                        }
                    },
                    "reconstruction": {
                        "points": np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
                    },
                },
                "holding": {"v3": {"bimanual_confirmed": np.bool_(False)}},
                "render": {
                    "safety_rejections": np.int32(0),
                    "maximum_rendered_length": np.float32(np.nan),
                },
                "frame_quality": {"score": np.float32(0.91)},
            }
        ],
    }


def test_final_pose_keypoints_document_is_strict_json(tmp_path: Path) -> None:
    destination = tmp_path / "pose-keypoints.json"

    write_pose_document(
        destination,
        _representative_pose_document(),
        document_name="pose-keypoints",
    )

    parsed = json.loads(destination.read_text(encoding="utf-8"))
    assert parsed["frames"][0]["temporal_v6"]["analysis_bones"]["left_forearm"]["valid"] is True
    assert parsed["frames"][0]["render"]["maximum_rendered_length"] is None
    json.dumps(parsed, allow_nan=False)


def test_final_pose_diagnostics_document_is_strict_json(tmp_path: Path) -> None:
    destination = tmp_path / "pose-diagnostics.json"
    diagnostics = {
        "schema_version": "4.0",
        "analysis_id": "analysis-test",
        "tracking": {"recovery_success": np.bool_(True)},
        "temporal_v6": {"point_source_counts": {"MEASURED": np.int64(20)}},
        "render": {"coverage": np.float32(0.625)},
        "worst_frame_indices": np.array([2, 8], dtype=np.int64),
    }

    write_pose_document(
        destination,
        diagnostics,
        document_name="pose-diagnostics",
        pretty=True,
    )

    parsed = json.loads(destination.read_text(encoding="utf-8"))
    assert parsed["tracking"]["recovery_success"] is True
    assert parsed["worst_frame_indices"] == [2, 8]


def test_pose_boundary_keeps_document_name_and_nested_path() -> None:
    document = {"frames": [{"temporal_v6": {"unexpected": _UnknownValue()}}]}

    with pytest.raises(PoseOutputSerializationError) as raised:
        serialize_pose_document(document, document_name="pose-keypoints")

    assert raised.value.error_code == "POSE_OUTPUT_SERIALIZATION_ERROR"
    assert raised.value.document_name == "pose-keypoints"
    assert raised.value.path == "$.frames[0].temporal_v6.unexpected"


def test_temporal_bone_validator_returns_native_bool() -> None:
    points = np.array([[0.0, 0.0], [10.0, 0.0]], dtype=np.float32)
    scores = np.array([0.9, 0.8], dtype=np.float32)
    frame = TemporalFrame(
        analysis_points=points,
        analysis_scores=scores,
        render_points=points,
        render_scores=scores,
        sources=(PointSource.MEASURED, PointSource.MEASURED),
        analysis_usable=np.array([True, True], dtype=np.bool_),
        prediction_age_seconds=np.zeros(2, dtype=np.float32),
        flow_errors=np.zeros(2, dtype=np.float32),
    )

    result = validate_analysis_bones(
        frame,
        {"segment": (0, 1)},
        {"segment": 10.0},
        body_scale=100.0,
    )

    assert result["segment"]["valid"] is True


def test_bimanual_holding_v3_returns_native_bool_for_numpy_evidence() -> None:
    evidence = HoldingEvidenceV3(
        grip=np.float32(0.8),
        contact_evidence=np.float32(0.8),
        object_proximity=np.float32(0.8),
        common_motion=np.float32(0.8),
        temporal_persistence=np.float32(0.8),
        occlusion_pattern=np.float32(0.8),
        release=np.float32(0.0),
        quality=np.float32(0.8),
    )
    frame = HoldingFrameV3(
        HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT,
        np.float32(0.8),
        evidence,
        np.float32(0.8),
        (),
    )

    assert bimanual_holding_v3([frame], [frame])[0] is True
