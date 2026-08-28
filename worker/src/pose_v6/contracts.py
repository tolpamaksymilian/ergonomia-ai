"""Explicit production boundaries for the final Pose V6 skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .temporal_reconstruction import TemporalFrame


@dataclass(frozen=True)
class FinalSkeletonContractReport:
    frame_count: int
    joint_count: int
    identity_checked: bool
    immutable_checked: bool = False
    v66_metadata_checked: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": True,
            "frame_count": self.frame_count,
            "joint_count": self.joint_count,
            "identity_checked": self.identity_checked,
            "coordinates_finite_for_usable_joints": True,
            "serialization_shapes_valid": True,
            "immutable_final_skeleton": self.immutable_checked,
            "coordinate_space_contract": (
                "ORIGINAL_PIXELS" if self.v66_metadata_checked else None
            ),
            "atomic_endpoint_metadata_valid": self.v66_metadata_checked,
        }


class FinalSkeletonContractError(ValueError):
    """A final skeleton invariant failed and artifact writing must stop."""

    def __init__(
        self,
        *,
        field: str,
        frame_index: int | None,
        actual_shape: tuple[int, ...] | None,
        expected: str,
    ) -> None:
        location = f" frame={frame_index}" if frame_index is not None else ""
        shape = f" actual_shape={actual_shape}" if actual_shape is not None else ""
        super().__init__(
            f"FinalSkeletonContract failed:{location} field={field}{shape} "
            f"expected={expected}"
        )
        self.field = field
        self.frame_index = frame_index
        self.actual_shape = actual_shape
        self.expected = expected


def validate_final_skeleton_contract(
    frames: Sequence[TemporalFrame],
    *,
    expected_frame_count: int,
    body_joint_count: int,
    identity_scores: Sequence[float] | None = None,
    require_immutable: bool = False,
    require_v66_metadata: bool = False,
) -> FinalSkeletonContractReport:
    """Validate geometry and serialization invariants before artifact writing.

    Canonical per-frame shapes are ``points=(joint, 2)`` and every scalar
    joint field is ``(joint,)``.  Diagnostic NaNs are allowed only in
    ``flow_errors``; coordinates of analytically usable/rendered joints and
    all scores must be finite.
    """

    if expected_frame_count <= 0 or body_joint_count <= 0:
        raise FinalSkeletonContractError(
            field="counts", frame_index=None, actual_shape=None,
            expected="positive expected_frame_count and body_joint_count",
        )
    if len(frames) != expected_frame_count:
        raise FinalSkeletonContractError(
            field="frames", frame_index=None, actual_shape=(len(frames),),
            expected=f"({expected_frame_count},)",
        )
    if identity_scores is not None and len(identity_scores) != len(frames):
        raise FinalSkeletonContractError(
            field="identity_scores", frame_index=None,
            actual_shape=(len(identity_scores),), expected=f"({len(frames)},)",
        )

    for frame_index, frame in enumerate(frames):
        _require_joint_points(frame.analysis_points, body_joint_count, "analysis_points", frame_index)
        _require_joint_points(frame.render_points, body_joint_count, "render_points", frame_index)
        for field, values in (
            ("analysis_scores", frame.analysis_scores),
            ("render_scores", frame.render_scores),
            ("analysis_usable", frame.analysis_usable),
            ("prediction_age_seconds", frame.prediction_age_seconds),
            ("flow_errors", frame.flow_errors),
        ):
            _require_joint_vector(values, body_joint_count, field, frame_index)
            if require_immutable and np.asarray(values).flags.writeable:
                raise FinalSkeletonContractError(
                    field=field,
                    frame_index=frame_index,
                    actual_shape=tuple(int(value) for value in np.asarray(values).shape),
                    expected="immutable ndarray",
                )
        if require_immutable:
            for field, values in (
                ("analysis_points", frame.analysis_points),
                ("render_points", frame.render_points),
            ):
                if np.asarray(values).flags.writeable:
                    raise FinalSkeletonContractError(
                        field=field,
                        frame_index=frame_index,
                        actual_shape=tuple(int(value) for value in np.asarray(values).shape),
                        expected="immutable ndarray",
                    )
        if len(frame.sources) < body_joint_count:
            raise FinalSkeletonContractError(
                field="sources", frame_index=frame_index,
                actual_shape=(len(frame.sources),), expected=f"at least ({body_joint_count},)",
            )
        if require_v66_metadata:
            if frame.frame_timestamp_seconds is None or not np.isfinite(
                float(frame.frame_timestamp_seconds)
            ):
                raise FinalSkeletonContractError(
                    field="frame_timestamp_seconds", frame_index=frame_index,
                    actual_shape=None, expected="finite native timestamp",
                )
            if frame.effective_timestamps is None:
                raise FinalSkeletonContractError(
                    field="effective_timestamps", frame_index=frame_index,
                    actual_shape=None, expected=f"({body_joint_count},)",
                )
            _require_joint_vector(
                frame.effective_timestamps,
                body_joint_count,
                "effective_timestamps",
                frame_index,
            )
            if not np.isfinite(
                np.asarray(frame.effective_timestamps[:body_joint_count], dtype=np.float64)
            ).all():
                raise FinalSkeletonContractError(
                    field="effective_timestamps", frame_index=frame_index,
                    actual_shape=None, expected="finite endpoint timestamps",
                )
            if len(frame.source_passes) < body_joint_count:
                raise FinalSkeletonContractError(
                    field="source_passes", frame_index=frame_index,
                    actual_shape=(len(frame.source_passes),),
                    expected=f"at least ({body_joint_count},)",
                )
            if len(frame.coordinate_spaces) < body_joint_count or any(
                str(value) != "ORIGINAL_PIXELS"
                for value in frame.coordinate_spaces[:body_joint_count]
            ):
                raise FinalSkeletonContractError(
                    field="coordinate_spaces", frame_index=frame_index,
                    actual_shape=(len(frame.coordinate_spaces),),
                    expected=f"{body_joint_count} ORIGINAL_PIXELS entries",
                )
            if frame.track_id is None or not str(frame.track_id).strip():
                raise FinalSkeletonContractError(
                    field="track_id", frame_index=frame_index,
                    actual_shape=None, expected="non-empty final track id",
                )

        analysis_scores = np.asarray(frame.analysis_scores[:body_joint_count], dtype=np.float64)
        render_scores = np.asarray(frame.render_scores[:body_joint_count], dtype=np.float64)
        if not np.isfinite(analysis_scores).all() or not np.isfinite(render_scores).all():
            raise FinalSkeletonContractError(
                field="scores", frame_index=frame_index, actual_shape=None,
                expected="finite values",
            )
        if np.any((analysis_scores < 0.0) | (analysis_scores > 1.0)) or np.any(
            (render_scores < 0.0) | (render_scores > 1.0)
        ):
            raise FinalSkeletonContractError(
                field="scores", frame_index=frame_index, actual_shape=None,
                expected="values in range 0..1",
            )
        usable = np.asarray(frame.analysis_usable[:body_joint_count], dtype=bool)
        if np.any(usable) and not np.isfinite(
            np.asarray(frame.analysis_points[:body_joint_count], dtype=np.float64)[usable]
        ).all():
            raise FinalSkeletonContractError(
                field="analysis_points", frame_index=frame_index, actual_shape=None,
                expected="finite coordinates for usable joints",
            )
        rendered = render_scores > 0.0
        if np.any(rendered) and not np.isfinite(
            np.asarray(frame.render_points[:body_joint_count], dtype=np.float64)[rendered]
        ).all():
            raise FinalSkeletonContractError(
                field="render_points", frame_index=frame_index, actual_shape=None,
                expected="finite coordinates for rendered joints",
            )
        if identity_scores is not None:
            identity = float(identity_scores[frame_index])
            if not np.isfinite(identity) or not 0.0 <= identity <= 1.0:
                raise FinalSkeletonContractError(
                    field="identity_scores", frame_index=frame_index,
                    actual_shape=None, expected="finite value in range 0..1",
                )

    return FinalSkeletonContractReport(
        frame_count=len(frames), joint_count=body_joint_count,
        identity_checked=identity_scores is not None,
        immutable_checked=require_immutable,
        v66_metadata_checked=require_v66_metadata,
    )


def _require_joint_points(
    values: np.ndarray, joint_count: int, field: str, frame_index: int,
) -> None:
    array = np.asarray(values)
    if array.ndim != 2 or array.shape[0] < joint_count or array.shape[1] != 2:
        raise FinalSkeletonContractError(
            field=field, frame_index=frame_index,
            actual_shape=tuple(int(value) for value in array.shape),
            expected=f"at least ({joint_count}, 2)",
        )


def _require_joint_vector(
    values: np.ndarray, joint_count: int, field: str, frame_index: int,
) -> None:
    array = np.asarray(values)
    if array.ndim != 1 or array.shape[0] < joint_count:
        raise FinalSkeletonContractError(
            field=field, frame_index=frame_index,
            actual_shape=tuple(int(value) for value in array.shape),
            expected=f"at least ({joint_count},)",
        )


__all__ = [
    "FinalSkeletonContractError",
    "FinalSkeletonContractReport",
    "validate_final_skeleton_contract",
]
