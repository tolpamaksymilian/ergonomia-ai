"""Precise late-stage Pose failures and idempotent finalization recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping


LATE_STAGE_CODES = {
    "artifact-serialization": ("POSE_ARTIFACT_SERIALIZATION_ERROR", "serialization", False),
    "artifact-compression": ("POSE_ARTIFACT_COMPRESSION_ERROR", "compression", True),
    "artifact-upload": ("POSE_ARTIFACT_UPLOAD_ERROR", "storage", True),
    "database-finalization": ("POSE_DATABASE_FINALIZATION_ERROR", "supabase-rpc", True),
}


@dataclass(frozen=True)
class PoseFailureDetails:
    stage: str
    code: str
    message: str
    component: str
    timestamp: str
    retryable: bool
    http_status: int | None
    upstream_error_code: str | None


class PoseStageError(RuntimeError):
    def __init__(self, stage: str, cause: BaseException):
        code, component, retryable = LATE_STAGE_CODES.get(
            stage, ("POSE_INFERENCE_ERROR", "pose-worker", False)
        )
        self.failure = PoseFailureDetails(
            stage=stage,
            code=code,
            message=safe_exception_message(cause),
            component=component,
            timestamp=datetime.now(timezone.utc).isoformat(),
            retryable=retryable,
            http_status=_http_status(cause),
            upstream_error_code=_upstream_code(cause),
        )
        self.error_code = code
        self.__cause__ = cause
        super().__init__(self.failure.message)


def safe_exception_message(error: BaseException) -> str:
    payload = _error_payload(error)
    message = payload.get("message") if payload else None
    value = _redact_sensitive_text(str(message if message is not None else error).strip())
    return (value or type(error).__name__)[:1800]


def _redact_sensitive_text(value: str) -> str:
    value = re.sub(
        r"(?i)\b(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|secret)\b\s*[:=]\s*[^\s,;}'\"]+",
        r"\1=[REDACTED]",
        value,
    )
    return re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        "[REDACTED_TOKEN]",
        value,
    )


def _error_payload(error: BaseException) -> Mapping[str, object]:
    if error.args and isinstance(error.args[0], Mapping):
        return error.args[0]
    return {}


def _http_status(error: BaseException) -> int | None:
    payload = _error_payload(error)
    value = payload.get("statusCode", payload.get("status"))
    try:
        status = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return status if status is not None and 100 <= status <= 599 else None


def _upstream_code(error: BaseException) -> str | None:
    value = _error_payload(error).get("code")
    return str(value)[:100] if value is not None and str(value).strip() else None


def build_completion_parameters(
    pose_document: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    worker_id: str,
) -> dict[str, object]:
    """Rebuild the V4 completion call from immutable uploaded artifacts."""

    analysis_id = _required_text(pose_document, "analysis_id")
    run_id = _required_text(pose_document, "analysis_run_id")
    generation_id = _required_text(pose_document, "artifact_generation_id")
    if manifest.get("analysis_run_id") != run_id or manifest.get("artifact_generation_id") != generation_id:
        raise ValueError("Artifact manifest provenance does not match Pose JSON.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Artifact manifest does not contain artifact paths.")
    summary = pose_document.get("summary")
    active = pose_document.get("active_segment")
    configuration = pose_document.get("configuration")
    if not isinstance(summary, Mapping) or not isinstance(active, Mapping):
        raise ValueError("Pose JSON does not contain completion summary.")
    configuration = configuration if isinstance(configuration, Mapping) else {}
    left = summary.get("left_hand")
    right = summary.get("right_hand")
    left = left if isinstance(left, Mapping) else {}
    right = right if isinstance(right, Mapping) else {}
    usage = pose_document.get("model_usage")
    usage = usage if isinstance(usage, Mapping) else {}

    return {
        "p_analysis_id": analysis_id,
        "p_worker_id": worker_id,
        "p_result_video_path": _required_artifact(artifacts, "overlay"),
        "p_result_json_path": _required_artifact(artifacts, "keypoints"),
        "p_thumbnail_path": _required_artifact(artifacts, "thumbnail"),
        "p_pose_model": str(pose_document.get("pose_model") or "RTMW WholeBody"),
        "p_sample_stride": int(configuration.get("inference_stride", 1) or 1),
        "p_processed_frames": int(summary.get("processed_frames", 0) or 0),
        "p_detected_frames": int(summary.get("detected_frames", 0) or 0),
        "p_average_confidence": float(summary.get("average_body_confidence", 0.0) or 0.0),
        "p_active_start_frame": int(active.get("source_start_frame", 0) or 0),
        "p_active_end_frame": int(active.get("source_end_frame", 0) or 0),
        "p_active_start_seconds": float(active.get("source_start_seconds", 0.0) or 0.0),
        "p_active_end_seconds": float(active.get("source_end_seconds", 0.0) or 0.0),
        "p_active_duration_seconds": float(active.get("output_duration_seconds", 0.0) or 0.0),
        "p_presence_ratio": float(summary.get("presence_ratio", 0.0) or 0.0),
        "p_tracking_method": str(configuration.get("tracking_method") or "unknown"),
        "p_smoothing_method": str(configuration.get("smoothing_method") or "unknown"),
        "p_quality_version": str(pose_document.get("quality_version") or pose_document.get("pose_version") or "unknown"),
        "p_hand_model": str(pose_document.get("hand_model") or "unknown"),
        "p_left_hand_valid_ratio": float(left.get("valid_ratio", 0.0) or 0.0),
        "p_right_hand_valid_ratio": float(right.get("valid_ratio", 0.0) or 0.0),
        "p_left_hand_rejected_frames": int(left.get("rejected_frames", 0) or 0),
        "p_right_hand_rejected_frames": int(right.get("rejected_frames", 0) or 0),
        "p_analysis_run_id": run_id,
        "p_artifact_generation_id": generation_id,
        "p_temporal_experts_actually_used": bool(usage.get("temporal_experts_actually_used", False)),
        "p_temporal_expert_frames_count": int(usage.get("temporal_expert_frames_count", 0) or 0),
        "p_model_usage": dict(usage),
    }


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"Pose JSON is missing {key}.")
    return result


def _required_artifact(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"Artifact manifest is missing {key}.")
    return result


__all__ = [
    "PoseFailureDetails",
    "PoseStageError",
    "build_completion_parameters",
    "safe_exception_message",
]
