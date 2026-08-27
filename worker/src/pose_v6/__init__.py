"""Pose Pipeline V6.5 temporal-continuity and production-hardening layer.

V6 extends the validated V3/V4/V5 pipeline.  It does not replace the detector,
pose model, hand model, biomechanical graph or downstream ergonomic formulas.
"""

POSE_VERSION = "pose-v6.5.0-beta.1"
POSE_SCHEMA_VERSION = "6.0"
WORKER_VERSION = "0.13.0-beta.1"

__all__ = ["POSE_SCHEMA_VERSION", "POSE_VERSION", "WORKER_VERSION"]
