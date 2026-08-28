from __future__ import annotations

import argparse
from collections import Counter
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

# Torch powinien być zaimportowany przed onnxruntime na Windows.
import onnxruntime as ort

from dotenv import load_dotenv
from rtmlib import RTMPose, YOLOX
from supabase import Client, create_client

from pose_v3.hand_pipeline import (
    HandPipelineConfig,
    HandTrackSummary,
    MediaPipeHandEngine,
    RawHandFrame,
    enhance_hand_track,
    resolve_hand_model_path,
    serialize_hand_frame,
    serialize_hand_summary,
    stabilize_hand_track,
)
from pose_v3.body_validation import (
    BODY_BONES,
    BodyValidationConfig,
)
from pose_v3.hand_object import ObjectDetection
from pose_v3.smoothing import smooth_body_sequence
from pose_v3.tracking import (
    PersonTrackingStateMachine,
    TrackingConfig,
    TrackingState,
)
from ergonomics.processor import compute_overlay_metrics_from_frame
try:
    from worker.src.pose_artifact_storage import (
        compress_json_artifact,
        upload_compressed_json,
    )
except ModuleNotFoundError:  # pragma: no cover - worker/src direct execution
    from pose_artifact_storage import (
        compress_json_artifact,
        upload_compressed_json,
    )
try:
    from worker.src.pose_v6 import POSE_SCHEMA_VERSION, POSE_VERSION, WORKER_VERSION
    from worker.src.pose_v6.anatomical_stability import project_anatomical_sequence
    from worker.src.pose_v6.angle_engine import stabilize_angle_sequence
    from worker.src.pose_v6.config import PoseV6Config, frames_for_seconds, load_pose_v6_config
    from worker.src.pose_v6.coordinate_space import CoordinateSpaceError, original_pixel_candidate
    from worker.src.pose_v6.contracts import validate_final_skeleton_contract
    from worker.src.pose_v6.coverage import build_frame_layer_contract, coalesce_short_timeline_gaps, summarize_layer_coverage
    from worker.src.pose_v6.diagnostics import rank_temporal_worst_frames, summarize_temporal_frames
    from worker.src.pose_v6.expert_backend import assess_local_expert_candidates, pose_model_evaluation_table
    from worker.src.pose_v6.grip_v4 import analyze_grip_v4
    from worker.src.pose_v6.high_motion import (
        CORE_LIMB_CHAINS,
        build_limb_crops,
        compute_joint_kinematics,
        estimate_motion_blur,
        expected_chain_lengths,
        validate_chain_candidate,
    )
    from worker.src.pose_v6.integration import augment_pose_document_v6
    from worker.src.pose_v6.iterative_refinement import (
        PoseHypothesis,
        PoseAuditInputError,
        PoseErrorCode,
        audit_pose_sequence,
        compare_iteration_quality,
        detect_grip_flicker,
        fuse_pose_hypotheses,
        optimize_global_trajectories,
        select_critical_segments,
    )
    from worker.src.pose_v6.motion_analysis import MotionAnalyzer, MotionObservation, MotionState
    from worker.src.pose_v6.optical_flow import track_point_forward_backward
    from worker.src.pose_v6.render_continuity import PersistentBone, PersistentBoneRenderer, summarize_render_sources
    from worker.src.pose_v6.serialization import PoseOutputSerializationError, write_pose_document
    from worker.src.pose_v6.limb_consistency import (
        attach_temporal_metadata,
        enforce_limb_chain_consistency,
        freeze_temporal_frames,
    )
    from worker.src.pose_v6.temporal_supersampling import (
        HighMotionTemporalSupersampling,
        bidirectional_native_prediction,
    )
    from worker.src.pose_v6.temporal_reconstruction import PointSource, TemporalFrame, merge_flow_result, reconstruct_temporal_sequence, reject_reconstructed_analysis_joints, validate_analysis_bones
    from worker.src.pose_v6.temporal_tracker import BBoxMotionEstimator, BBoxSource, recovery_allowed
    from worker.src.pose_v6.timeline import probe_native_frame_timeline
    from worker.src.pose_v6.trajectory_refinement import refine_fixed_lag_sequence
except ModuleNotFoundError:  # pragma: no cover - worker/src direct execution fallback
    from pose_v6 import POSE_SCHEMA_VERSION, POSE_VERSION, WORKER_VERSION
    from pose_v6.anatomical_stability import project_anatomical_sequence
    from pose_v6.angle_engine import stabilize_angle_sequence
    from pose_v6.config import PoseV6Config, frames_for_seconds, load_pose_v6_config
    from pose_v6.coordinate_space import CoordinateSpaceError, original_pixel_candidate
    from pose_v6.contracts import validate_final_skeleton_contract
    from pose_v6.coverage import build_frame_layer_contract, coalesce_short_timeline_gaps, summarize_layer_coverage
    from pose_v6.diagnostics import rank_temporal_worst_frames, summarize_temporal_frames
    from pose_v6.expert_backend import assess_local_expert_candidates, pose_model_evaluation_table
    from pose_v6.grip_v4 import analyze_grip_v4
    from pose_v6.high_motion import (
        CORE_LIMB_CHAINS,
        build_limb_crops,
        compute_joint_kinematics,
        estimate_motion_blur,
        expected_chain_lengths,
        validate_chain_candidate,
    )
    from pose_v6.integration import augment_pose_document_v6
    from pose_v6.iterative_refinement import (
        PoseHypothesis,
        PoseAuditInputError,
        PoseErrorCode,
        audit_pose_sequence,
        compare_iteration_quality,
        detect_grip_flicker,
        fuse_pose_hypotheses,
        optimize_global_trajectories,
        select_critical_segments,
    )
    from pose_v6.motion_analysis import MotionAnalyzer, MotionObservation, MotionState
    from pose_v6.optical_flow import track_point_forward_backward
    from pose_v6.render_continuity import PersistentBone, PersistentBoneRenderer, summarize_render_sources
    from pose_v6.serialization import PoseOutputSerializationError, write_pose_document
    from pose_v6.limb_consistency import (
        attach_temporal_metadata,
        enforce_limb_chain_consistency,
        freeze_temporal_frames,
    )
    from pose_v6.temporal_supersampling import (
        HighMotionTemporalSupersampling,
        bidirectional_native_prediction,
    )
    from pose_v6.temporal_reconstruction import PointSource, TemporalFrame, merge_flow_result, reconstruct_temporal_sequence, reject_reconstructed_analysis_joints, validate_analysis_bones
    from pose_v6.temporal_tracker import BBoxMotionEstimator, BBoxSource, recovery_allowed
    from pose_v6.timeline import probe_native_frame_timeline
    from pose_v6.trajectory_refinement import refine_fixed_lag_sequence
from pose_v5.camera_motion import CameraMotionEstimator
from pose_v5.config import CameraMotionConfig, PoseV5Config, RefinementConfig
from pose_v5.integration import augment_pose_document_v5
from pose_v5.diagnostics import region_quality_coverage
from pose_v5.hand_rescue import enlarge_roi, observation_coverage, rescue_frame_indexes
from pose_v5.refinement import (
    RefinementResult,
    detect_difficult_segments,
    refine_frames,
)
from pose_v5.holding import (
    HoldingEvidenceV3,
    HoldingStateV3,
    analyze_holding_v3,
    bimanual_holding_v3,
)
from pose_v4.graph import (
    BiomechanicalPoseGraph,
    JOINT_NAMES,
    PoseGraphConfig,
    summarize_pose_graph,
)
from pose_v4.hand_graph import (
    HandAssignmentMemory,
    HandGraphConfig,
    analyze_hand_graph_sequence,
    assign_hands_to_body_v2,
    predict_hand_rois,
    union_hand_roi,
)
from pose_v4.holding import (
    HoldingV2Config,
    analyze_bimanual_holding_v2,
    analyze_holding_v2,
    serialize_holding_frame_v2,
    serialize_holding_summary_v2,
)
from pose_v4.object_tracking import track_object_sequence
from pose_v4.overlay import (
    BoneRenderController,
    MetricColorHysteresis,
    OverlayConfig,
    OverlayPalette,
    draw_pose_overlay_v4,
)
from pose_v4.quality import (
    analyze_image_quality_v2,
    build_frame_quality_v2,
    summarize_quality_v2,
)


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "pose-jobs"
LOG_DIRECTORY = WORKER_DIRECTORY / "logs"

QUALITY_VERSION = POSE_VERSION
TRACKING_METHOD = (
    "coco-yolox-track-conditioned-biomechanical-v6"
)
HAND_TRACKING_METHOD = (
    "mediapipe-adaptive-roi-global-assignment-hand-graph-v3"
)
SMOOTHING_METHOD = "offline-bidirectional-hermite-flow-body-v6+offline-hand-v3"

COCO_CLASS_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
    "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)
HAND_RELEVANT_COCO_CLASSES = frozenset(
    {24, 25, 26, 27, 28, 29, 32, 34, 35, 38, 39, 40, 41, 42, 43, 44, 45, 64, 65, 66, 67, 73, 76}
)

BODY_POINT_COUNT = 23
KEYPOINT_COUNT = 133

# COCO WholeBody: 0-16 ciało, 17-22 stopy, 23-90 twarz,
# 91-111 lewa dłoń, 112-132 prawa dłoń.
TORSO_EDGES = (
    (5, 6),
    (5, 11),
    (6, 12),
    (11, 12),
)

LEFT_BODY_EDGES = (
    (5, 7),
    (7, 9),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 18),
    (15, 19),
    (17, 18),
    (18, 19),
)

RIGHT_BODY_EDGES = (
    (6, 8),
    (8, 10),
    (12, 14),
    (14, 16),
    (16, 20),
    (16, 21),
    (16, 22),
    (20, 21),
    (21, 22),
)

HAND_LOCAL_EDGES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (0, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (0, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
)

# Detektor wieloklasowy YOLOX-X wytrenowany na COCO.
# W trybie multiclass filtrujemy wyłącznie klasę 0 = person.
COCO_PERSON_DETECTOR_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/"
    "releases/download/0.1.1rc0/yolox_x.onnx"
)

# RTMW-X WholeBody 133 keypoints, wejście 384x288.
RTMW_PERFORMANCE_URL = (
    "https://download.openmmlab.com/mmpose/v1/projects/"
    "rtmw/onnx_sdk/"
    "rtmw-dw-x-l_simcc-cocktail14_270e-384x288_20231122.zip"
)


@dataclass(frozen=True)
class PoseWorkerSettings:
    supabase_url: str
    supabase_secret_key: str
    source_bucket: str
    results_bucket: str
    worker_id: str
    poll_interval_seconds: int
    keep_worker_files: bool

    model_mode: str

    detector_score_threshold: float
    detector_nms_threshold: float
    detector_min_height_ratio: float
    detector_min_area_ratio: float
    detector_min_aspect_ratio: float
    detector_max_aspect_ratio: float
    detector_max_people: int

    keypoint_threshold: float
    body_presence_threshold: float
    body_min_keypoints: int

    scan_fps: float
    scan_min_quality: float
    scan_start_confirm_seconds: float
    scan_end_confirm_seconds: float
    active_pre_padding_seconds: float
    active_post_padding_seconds: float
    min_active_seconds: float
    min_presence_ratio: float

    track_min_iou: float
    track_max_center_jump_ratio: float

    body_reacquire_confirm_frames: int
    body_lost_after_missing_frames: int
    body_edge_margin_ratio: float
    body_max_joint_velocity_bbox_ratio: float
    body_max_joint_acceleration_bbox_ratio: float
    body_bone_log_tolerance: float
    body_max_interpolation_gap_frames: int
    body_max_prediction_frames: int
    body_scale_max_change_ratio: float

    pose_v5_refinement_enabled: bool
    pose_v5_max_refinement_ratio: float
    pose_v5_segment_padding_seconds: float
    pose_v5_min_quality_gain: float
    pose_v5_camera_motion_enabled: bool

    hand_model_path: Path
    hand_detection_confidence: float
    hand_presence_confidence: float
    hand_tracking_confidence: float
    hand_assignment_max_wrist_distance_ratio: float
    hand_handedness_soft_penalty: float
    hand_min_palm_size_pixels: float
    hand_min_forearm_pixels: float
    hand_min_lock_frames: int
    hand_max_interpolation_gap_frames: int
    hand_max_root_wrist_distance_ratio: float
    hand_min_scale_ratio: float
    hand_max_scale_ratio: float
    hand_max_scale_change_ratio: float
    hand_max_orientation_change_degrees: float
    hand_max_joint_velocity_palm_ratio: float
    hand_max_median_joint_velocity_palm_ratio: float
    hand_max_world_depth_jump_meters: float
    hand_bone_log_tolerance: float
    hand_max_bone_outliers: int
    hand_max_radius_forearm_ratio: float
    hand_max_bone_forearm_ratio: float
    hand_median_window: int
    hand_smoothing_alpha: float
    hand_bone_projection_strength: float
    hand_reacquire_confirm_frames: int
    hand_use_adaptive_roi: bool
    hand_rescue_enabled: bool
    hand_rescue_minimum_coverage: float
    hand_rescue_roi_scale: float
    hand_rescue_upscale_factor: float
    hand_rescue_maximum_ratio: float

    holding_enabled: bool
    holding_min_confirmation_seconds: float
    holding_release_confirmation_seconds: float
    holding_max_unknown_gap_seconds: float
    holding_enter_threshold: float
    holding_keep_threshold: float
    holding_exit_threshold: float
    holding_min_static_seconds: float

    draw_hands: bool
    draw_face: bool
    debug_overlay: bool
    draw_angles: bool
    draw_objects: bool
    render_quality_threshold: float
    render_fade_frames: int
    progress_update_interval_frames: int
    output_crf: int


@dataclass(frozen=True)
class ActiveSegmentPart:
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1


@dataclass(frozen=True)
class ActiveSegment:
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    scan_stride: int
    scan_presence_ratio: float
    segments: tuple[ActiveSegmentPart, ...] = ()

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1


@dataclass(frozen=True)
class PoseCandidate:
    keypoints: np.ndarray
    scores: np.ndarray
    bbox: np.ndarray
    body_keypoint_count: int
    body_average_confidence: float
    selection_score: float


@dataclass(frozen=True)
class PoseProcessingResult:
    video_path: Path
    json_path: Path
    thumbnail_path: Path
    diagnostics_path: Path
    processed_frames: int
    detected_frames: int
    average_confidence: float
    presence_ratio: float
    active_segment: ActiveSegment
    left_hand_summary: HandTrackSummary
    right_hand_summary: HandTrackSummary


def get_required_environment_variable(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Brakuje wymaganej zmiennej środowiskowej: {name}"
        )

    return value


def parse_boolean(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "tak",
        "on",
    }


def load_settings(*, require_supabase: bool = True) -> PoseWorkerSettings:
    if require_supabase and not ENV_PATH.exists():
        raise RuntimeError(f"Nie znaleziono konfiguracji: {ENV_PATH}")

    load_dotenv(ENV_PATH)

    model_mode = os.getenv(
        "POSE_MODEL_MODE",
        "performance",
    ).strip().lower()

    if model_mode != "performance":
        raise RuntimeError(
            "Pose Pipeline V6 korzysta z modelu performance. "
            "Ustaw POSE_MODEL_MODE=performance."
        )

    settings = PoseWorkerSettings(
        supabase_url=(
            get_required_environment_variable("SUPABASE_URL")
            if require_supabase
            else os.getenv("SUPABASE_URL", "https://local.invalid").strip()
            or "https://local.invalid"
        ),
        supabase_secret_key=(
            get_required_environment_variable("SUPABASE_SECRET_KEY")
            if require_supabase
            else os.getenv("SUPABASE_SECRET_KEY", "local-not-used").strip()
            or "local-not-used"
        ),
        source_bucket=os.getenv(
            "ANALYSIS_BUCKET",
            "analysis-videos",
        ).strip(),
        results_bucket=os.getenv(
            "ANALYSIS_RESULTS_BUCKET",
            "analysis-results",
        ).strip(),
        worker_id=os.getenv(
            "WORKER_ID",
            "local-worker-01",
        ).strip(),
        poll_interval_seconds=int(
            os.getenv(
                "WORKER_POLL_INTERVAL_SECONDS",
                "10",
            )
        ),
        keep_worker_files=parse_boolean(
            os.getenv("KEEP_WORKER_FILES"),
            default=False,
        ),
        model_mode=model_mode,
        detector_score_threshold=float(
            os.getenv(
                "POSE_DETECTOR_SCORE_THRESHOLD",
                "0.70",
            )
        ),
        detector_nms_threshold=float(
            os.getenv(
                "POSE_DETECTOR_NMS_THRESHOLD",
                "0.45",
            )
        ),
        detector_min_height_ratio=float(
            os.getenv(
                "POSE_DETECTOR_MIN_HEIGHT_RATIO",
                "0.16",
            )
        ),
        detector_min_area_ratio=float(
            os.getenv(
                "POSE_DETECTOR_MIN_AREA_RATIO",
                "0.010",
            )
        ),
        detector_min_aspect_ratio=float(
            os.getenv(
                "POSE_DETECTOR_MIN_ASPECT_RATIO",
                "0.12",
            )
        ),
        detector_max_aspect_ratio=float(
            os.getenv(
                "POSE_DETECTOR_MAX_ASPECT_RATIO",
                "1.60",
            )
        ),
        detector_max_people=int(
            os.getenv(
                "POSE_DETECTOR_MAX_PEOPLE",
                "2",
            )
        ),
        keypoint_threshold=float(
            os.getenv(
                "POSE_KEYPOINT_THRESHOLD",
                "0.78",
            )
        ),
        body_presence_threshold=float(
            os.getenv(
                "POSE_BODY_PRESENCE_THRESHOLD",
                "0.80",
            )
        ),
        body_min_keypoints=int(
            os.getenv(
                "POSE_BODY_MIN_KEYPOINTS",
                "7",
            )
        ),
        scan_fps=float(
            os.getenv(
                "POSE_SCAN_FPS",
                "5",
            )
        ),
        scan_min_quality=float(
            os.getenv(
                "POSE_SCAN_MIN_QUALITY",
                "0.72",
            )
        ),
        scan_start_confirm_seconds=float(
            os.getenv(
                "POSE_SCAN_START_CONFIRM_SECONDS",
                "0.40",
            )
        ),
        scan_end_confirm_seconds=float(
            os.getenv(
                "POSE_SCAN_END_CONFIRM_SECONDS",
                "0.45",
            )
        ),
        active_pre_padding_seconds=float(
            os.getenv(
                "POSE_ACTIVE_PRE_PADDING_SECONDS",
                "0.25",
            )
        ),
        active_post_padding_seconds=float(
            os.getenv(
                "POSE_ACTIVE_POST_PADDING_SECONDS",
                "0.25",
            )
        ),
        min_active_seconds=float(
            os.getenv(
                "POSE_MIN_ACTIVE_SECONDS",
                "0.80",
            )
        ),
        min_presence_ratio=float(
            os.getenv(
                "POSE_MIN_PRESENCE_RATIO",
                "0.65",
            )
        ),
        track_min_iou=float(
            os.getenv(
                "POSE_TRACK_MIN_IOU",
                "0.015",
            )
        ),
        track_max_center_jump_ratio=float(
            os.getenv(
                "POSE_TRACK_MAX_CENTER_JUMP_RATIO",
                "0.30",
            )
        ),
        body_reacquire_confirm_frames=int(
            os.getenv("POSE_BODY_REACQUIRE_CONFIRM_FRAMES", "3")
        ),
        body_lost_after_missing_frames=int(
            os.getenv("POSE_BODY_LOST_AFTER_MISSING_FRAMES", "2")
        ),
        body_edge_margin_ratio=float(
            os.getenv("POSE_BODY_EDGE_MARGIN_RATIO", "0.025")
        ),
        body_max_joint_velocity_bbox_ratio=float(
            os.getenv("POSE_BODY_MAX_JOINT_VELOCITY_BBOX_RATIO", "0.38")
        ),
        body_max_joint_acceleration_bbox_ratio=float(
            os.getenv("POSE_BODY_MAX_JOINT_ACCELERATION_BBOX_RATIO", "0.55")
        ),
        body_bone_log_tolerance=float(
            os.getenv("POSE_BODY_BONE_LOG_TOLERANCE", "0.42")
        ),
        body_max_interpolation_gap_frames=int(
            os.getenv("POSE_BODY_MAX_INTERPOLATION_GAP_FRAMES", "2")
        ),
        body_max_prediction_frames=int(
            os.getenv("POSE_BODY_MAX_PREDICTION_FRAMES", "2")
        ),
        body_scale_max_change_ratio=float(
            os.getenv("POSE_BODY_SCALE_MAX_CHANGE_RATIO", "0.18")
        ),
        pose_v5_refinement_enabled=parse_boolean(
            os.getenv("POSE_V5_REFINEMENT_ENABLED"), default=True
        ),
        pose_v5_max_refinement_ratio=float(
            os.getenv("POSE_V5_MAX_REFINEMENT_RATIO", "0.25")
        ),
        pose_v5_segment_padding_seconds=float(
            os.getenv("POSE_V5_SEGMENT_PADDING_SECONDS", "0.35")
        ),
        pose_v5_min_quality_gain=float(
            os.getenv("POSE_V5_MIN_QUALITY_GAIN", "0.04")
        ),
        pose_v5_camera_motion_enabled=parse_boolean(
            os.getenv("POSE_V5_CAMERA_MOTION_ENABLED"), default=True
        ),
        hand_model_path=resolve_hand_model_path(
            WORKER_DIRECTORY,
            os.getenv("POSE_HAND_MODEL_PATH"),
        ),
        hand_detection_confidence=float(
            os.getenv("POSE_HAND_DETECTION_CONFIDENCE", "0.65")
        ),
        hand_presence_confidence=float(
            os.getenv("POSE_HAND_PRESENCE_CONFIDENCE", "0.65")
        ),
        hand_tracking_confidence=float(
            os.getenv("POSE_HAND_TRACKING_CONFIDENCE", "0.65")
        ),
        hand_assignment_max_wrist_distance_ratio=float(
            os.getenv("POSE_HAND_ASSIGNMENT_MAX_WRIST_DISTANCE_RATIO", "1.05")
        ),
        hand_handedness_soft_penalty=float(
            os.getenv("POSE_HAND_HANDEDNESS_SOFT_PENALTY", "0.18")
        ),
        hand_min_palm_size_pixels=float(
            os.getenv("POSE_HAND_MIN_PALM_SIZE_PIXELS", "8.0")
        ),
        hand_min_forearm_pixels=float(
            os.getenv("POSE_HAND_MIN_FOREARM_PIXELS", "12.0")
        ),
        hand_min_lock_frames=int(
            os.getenv("POSE_HAND_MIN_LOCK_FRAMES", "2")
        ),
        hand_max_interpolation_gap_frames=int(
            os.getenv("POSE_HAND_MAX_INTERPOLATION_GAP_FRAMES", "1")
        ),
        hand_max_root_wrist_distance_ratio=float(
            os.getenv("POSE_HAND_MAX_ROOT_WRIST_DISTANCE_RATIO", "0.75")
        ),
        hand_min_scale_ratio=float(
            os.getenv("POSE_HAND_MIN_SCALE_RATIO", "0.50")
        ),
        hand_max_scale_ratio=float(
            os.getenv("POSE_HAND_MAX_SCALE_RATIO", "1.90")
        ),
        hand_max_scale_change_ratio=float(
            os.getenv("POSE_HAND_MAX_SCALE_CHANGE_RATIO", "0.48")
        ),
        hand_max_orientation_change_degrees=float(
            os.getenv("POSE_HAND_MAX_ORIENTATION_CHANGE_DEGREES", "105.0")
        ),
        hand_max_joint_velocity_palm_ratio=float(
            os.getenv("POSE_HAND_MAX_JOINT_VELOCITY_PALM_RATIO", "1.35")
        ),
        hand_max_median_joint_velocity_palm_ratio=float(
            os.getenv("POSE_HAND_MAX_MEDIAN_JOINT_VELOCITY_PALM_RATIO", "0.70")
        ),
        hand_max_world_depth_jump_meters=float(
            os.getenv("POSE_HAND_MAX_WORLD_DEPTH_JUMP_METERS", "0.11")
        ),
        hand_bone_log_tolerance=float(
            os.getenv("POSE_HAND_BONE_LOG_TOLERANCE", "0.52")
        ),
        hand_max_bone_outliers=int(
            os.getenv("POSE_HAND_MAX_BONE_OUTLIERS", "3")
        ),
        hand_max_radius_forearm_ratio=float(
            os.getenv("POSE_HAND_MAX_RADIUS_FOREARM_RATIO", "1.55")
        ),
        hand_max_bone_forearm_ratio=float(
            os.getenv("POSE_HAND_MAX_BONE_FOREARM_RATIO", "0.68")
        ),
        hand_median_window=int(
            os.getenv("POSE_HAND_MEDIAN_WINDOW", "3")
        ),
        hand_smoothing_alpha=float(
            os.getenv("POSE_HAND_SMOOTHING_ALPHA", "0.62")
        ),
        hand_bone_projection_strength=float(
            os.getenv("POSE_HAND_BONE_PROJECTION_STRENGTH", "0.42")
        ),
        hand_reacquire_confirm_frames=int(
            os.getenv("POSE_HAND_REACQUIRE_CONFIRM_FRAMES", "2")
        ),
        hand_use_adaptive_roi=parse_boolean(
            os.getenv("POSE_HAND_USE_ADAPTIVE_ROI"), default=True
        ),
        hand_rescue_enabled=parse_boolean(
            os.getenv("POSE_HAND_RESCUE_ENABLED"), default=True
        ),
        hand_rescue_minimum_coverage=float(
            os.getenv("POSE_HAND_RESCUE_MINIMUM_COVERAGE", "0.20")
        ),
        hand_rescue_roi_scale=float(
            os.getenv("POSE_HAND_RESCUE_ROI_SCALE", "1.75")
        ),
        hand_rescue_upscale_factor=float(
            os.getenv("POSE_HAND_RESCUE_UPSCALE_FACTOR", "1.75")
        ),
        hand_rescue_maximum_ratio=float(
            os.getenv("POSE_HAND_RESCUE_MAXIMUM_RATIO", "0.35")
        ),
        holding_enabled=parse_boolean(
            os.getenv("POSE_HOLDING_ENABLED"), default=True
        ),
        holding_min_confirmation_seconds=float(
            os.getenv("POSE_HOLDING_MIN_CONFIRMATION_SECONDS", "0.40")
        ),
        holding_release_confirmation_seconds=float(
            os.getenv("POSE_HOLDING_RELEASE_CONFIRMATION_SECONDS", "0.25")
        ),
        holding_max_unknown_gap_seconds=float(
            os.getenv("POSE_HOLDING_MAX_UNKNOWN_GAP_SECONDS", "0.20")
        ),
        holding_enter_threshold=float(
            os.getenv("POSE_HOLDING_ENTER_THRESHOLD", "0.68")
        ),
        holding_keep_threshold=float(
            os.getenv("POSE_HOLDING_KEEP_THRESHOLD", "0.52")
        ),
        holding_exit_threshold=float(
            os.getenv("POSE_HOLDING_EXIT_THRESHOLD", "0.36")
        ),
        holding_min_static_seconds=float(
            os.getenv("POSE_HOLDING_MIN_STATIC_SECONDS", "0.75")
        ),
        draw_hands=parse_boolean(
            os.getenv("POSE_DRAW_HANDS"),
            default=True,
        ),
        draw_face=parse_boolean(
            os.getenv("POSE_DRAW_FACE"),
            default=False,
        ),
        debug_overlay=parse_boolean(
            os.getenv("POSE_DEBUG_OVERLAY"), default=False
        ),
        draw_angles=parse_boolean(
            os.getenv("POSE_DRAW_ANGLES"), default=True
        ),
        draw_objects=parse_boolean(
            os.getenv("POSE_DRAW_OBJECTS"), default=False
        ),
        render_quality_threshold=float(
            os.getenv("POSE_RENDER_QUALITY_THRESHOLD", "0.58")
        ),
        render_fade_frames=int(
            os.getenv("POSE_RENDER_FADE_FRAMES", "3")
        ),
        progress_update_interval_frames=int(
            os.getenv(
                "POSE_PROGRESS_UPDATE_INTERVAL_FRAMES",
                "15",
            )
        ),
        output_crf=int(
            os.getenv(
                "POSE_OUTPUT_CRF",
                "22",
            )
        ),
    )

    if settings.poll_interval_seconds < 1:
        raise RuntimeError(
            "WORKER_POLL_INTERVAL_SECONDS musi być większe od zera."
        )

    if not settings.worker_id:
        raise RuntimeError("WORKER_ID nie może być pusty.")

    if not settings.source_bucket:
        raise RuntimeError("ANALYSIS_BUCKET nie może być pusty.")

    if not settings.results_bucket:
        raise RuntimeError(
            "ANALYSIS_RESULTS_BUCKET nie może być pusty."
        )

    if not 0 < settings.detector_score_threshold <= 1:
        raise RuntimeError(
            "POSE_DETECTOR_SCORE_THRESHOLD musi mieścić się "
            "w zakresie 0-1."
        )

    if not 0 < settings.detector_nms_threshold <= 1:
        raise RuntimeError(
            "POSE_DETECTOR_NMS_THRESHOLD musi mieścić się "
            "w zakresie 0-1."
        )

    if not 0 < settings.detector_min_height_ratio <= 1:
        raise RuntimeError(
            "POSE_DETECTOR_MIN_HEIGHT_RATIO musi mieścić się "
            "w zakresie 0-1."
        )

    if not 0 < settings.detector_min_area_ratio <= 1:
        raise RuntimeError(
            "POSE_DETECTOR_MIN_AREA_RATIO musi mieścić się "
            "w zakresie 0-1."
        )

    if (
        settings.detector_min_aspect_ratio <= 0
        or settings.detector_max_aspect_ratio
        <= settings.detector_min_aspect_ratio
    ):
        raise RuntimeError(
            "Nieprawidłowy zakres proporcji bounding boxa."
        )

    if settings.detector_max_people < 1:
        raise RuntimeError(
            "POSE_DETECTOR_MAX_PEOPLE musi wynosić co najmniej 1."
        )

    if not 0 < settings.keypoint_threshold <= 1:
        raise RuntimeError(
            "POSE_KEYPOINT_THRESHOLD musi mieścić się w zakresie 0-1."
        )

    if not 0 < settings.body_presence_threshold <= 1:
        raise RuntimeError(
            "POSE_BODY_PRESENCE_THRESHOLD musi mieścić się "
            "w zakresie 0-1."
        )

    if settings.body_min_keypoints < 3:
        raise RuntimeError(
            "POSE_BODY_MIN_KEYPOINTS musi wynosić co najmniej 3."
        )

    if settings.scan_fps <= 0:
        raise RuntimeError(
            "POSE_SCAN_FPS musi być większe od zera."
        )

    if not 0 < settings.scan_min_quality <= 1:
        raise RuntimeError(
            "POSE_SCAN_MIN_QUALITY musi mieścić się w zakresie 0-1."
        )

    if settings.scan_start_confirm_seconds <= 0:
        raise RuntimeError(
            "POSE_SCAN_START_CONFIRM_SECONDS musi być większe od zera."
        )

    if settings.scan_end_confirm_seconds <= 0:
        raise RuntimeError(
            "POSE_SCAN_END_CONFIRM_SECONDS musi być większe od zera."
        )

    if settings.active_pre_padding_seconds < 0:
        raise RuntimeError(
            "POSE_ACTIVE_PRE_PADDING_SECONDS nie może być ujemne."
        )

    if settings.active_post_padding_seconds < 0:
        raise RuntimeError(
            "POSE_ACTIVE_POST_PADDING_SECONDS nie może być ujemne."
        )

    if settings.min_active_seconds <= 0:
        raise RuntimeError(
            "POSE_MIN_ACTIVE_SECONDS musi być większe od zera."
        )

    if not 0 < settings.min_presence_ratio <= 1:
        raise RuntimeError(
            "POSE_MIN_PRESENCE_RATIO musi mieścić się w zakresie 0-1."
        )

    if not 0 <= settings.track_min_iou <= 1:
        raise RuntimeError(
            "POSE_TRACK_MIN_IOU musi mieścić się w zakresie 0-1."
        )

    if not 0 < settings.track_max_center_jump_ratio <= 1:
        raise RuntimeError(
            "POSE_TRACK_MAX_CENTER_JUMP_RATIO musi mieścić się "
            "w zakresie 0-1."
        )

    if settings.body_reacquire_confirm_frames < 1:
        raise RuntimeError("POSE_BODY_REACQUIRE_CONFIRM_FRAMES musi wynosić co najmniej 1.")
    if settings.body_lost_after_missing_frames < 0:
        raise RuntimeError("POSE_BODY_LOST_AFTER_MISSING_FRAMES nie może być ujemne.")
    if not 0.0 < settings.body_edge_margin_ratio < 0.25:
        raise RuntimeError("POSE_BODY_EDGE_MARGIN_RATIO musi mieścić się w zakresie 0-0.25.")
    if settings.body_max_joint_velocity_bbox_ratio <= 0.0:
        raise RuntimeError("Limit prędkości jointa musi być większy od zera.")
    if settings.body_max_joint_acceleration_bbox_ratio <= 0.0:
        raise RuntimeError("Limit przyspieszenia jointa musi być większy od zera.")
    if settings.body_bone_log_tolerance <= 0.0:
        raise RuntimeError("POSE_BODY_BONE_LOG_TOLERANCE musi być większe od zera.")
    if settings.body_max_interpolation_gap_frames < 0:
        raise RuntimeError("POSE_BODY_MAX_INTERPOLATION_GAP_FRAMES nie może być ujemne.")
    if not 0 <= settings.body_max_prediction_frames <= 5:
        raise RuntimeError("POSE_BODY_MAX_PREDICTION_FRAMES musi mieścić się w zakresie 0-5.")
    if not 0.0 < settings.body_scale_max_change_ratio < 1.0:
        raise RuntimeError("POSE_BODY_SCALE_MAX_CHANGE_RATIO musi mieścić się w zakresie 0-1.")
    RefinementConfig(
        enabled=settings.pose_v5_refinement_enabled,
        maximum_refinement_ratio=settings.pose_v5_max_refinement_ratio,
        padding_seconds=settings.pose_v5_segment_padding_seconds,
        minimum_quality_gain=settings.pose_v5_min_quality_gain,
    ).validate()

    if settings.progress_update_interval_frames < 1:
        raise RuntimeError(
            "POSE_PROGRESS_UPDATE_INTERVAL_FRAMES musi być większe od zera."
        )

    if not 0 <= settings.output_crf <= 51:
        raise RuntimeError(
            "POSE_OUTPUT_CRF musi mieścić się w zakresie 0-51."
        )

    hand_unit_values = {
        "POSE_HAND_DETECTION_CONFIDENCE": settings.hand_detection_confidence,
        "POSE_HAND_PRESENCE_CONFIDENCE": settings.hand_presence_confidence,
        "POSE_HAND_TRACKING_CONFIDENCE": settings.hand_tracking_confidence,
        "POSE_HAND_HANDEDNESS_SOFT_PENALTY": settings.hand_handedness_soft_penalty,
        "POSE_HAND_MIN_SCALE_RATIO": settings.hand_min_scale_ratio,
        "POSE_HAND_MAX_SCALE_CHANGE_RATIO": settings.hand_max_scale_change_ratio,
        "POSE_HAND_SMOOTHING_ALPHA": settings.hand_smoothing_alpha,
        "POSE_HAND_BONE_PROJECTION_STRENGTH": settings.hand_bone_projection_strength,
    }
    for variable_name, value in hand_unit_values.items():
        if not 0.0 <= value <= 1.0:
            raise RuntimeError(
                f"{variable_name} musi mieścić się w zakresie 0-1."
            )

    for variable_name, value in {
        "POSE_HAND_RESCUE_MINIMUM_COVERAGE": settings.hand_rescue_minimum_coverage,
        "POSE_HAND_RESCUE_MAXIMUM_RATIO": settings.hand_rescue_maximum_ratio,
    }.items():
        if not 0.0 <= value <= 1.0:
            raise RuntimeError(f"{variable_name} musi mieścić się w zakresie 0-1.")
    if not 1.0 <= settings.hand_rescue_roi_scale <= 3.0:
        raise RuntimeError("POSE_HAND_RESCUE_ROI_SCALE musi mieścić się w zakresie 1-3.")
    if not 1.0 <= settings.hand_rescue_upscale_factor <= 3.0:
        raise RuntimeError("POSE_HAND_RESCUE_UPSCALE_FACTOR musi mieścić się w zakresie 1-3.")

    if settings.hand_assignment_max_wrist_distance_ratio <= 0:
        raise RuntimeError(
            "POSE_HAND_ASSIGNMENT_MAX_WRIST_DISTANCE_RATIO musi być większe od zera."
        )
    if settings.hand_min_palm_size_pixels <= 0 or settings.hand_min_forearm_pixels <= 0:
        raise RuntimeError(
            "Minimalne rozmiary dłoni i przedramienia muszą być większe od zera."
        )
    if settings.hand_min_lock_frames < 1:
        raise RuntimeError("POSE_HAND_MIN_LOCK_FRAMES musi wynosić co najmniej 1.")
    if settings.hand_max_interpolation_gap_frames < 0:
        raise RuntimeError(
            "POSE_HAND_MAX_INTERPOLATION_GAP_FRAMES nie może być ujemne."
        )
    if not 0 < settings.hand_min_scale_ratio < settings.hand_max_scale_ratio:
        raise RuntimeError("Nieprawidłowy zakres skali dłoni.")
    if settings.hand_max_bone_outliers < 0:
        raise RuntimeError("POSE_HAND_MAX_BONE_OUTLIERS nie może być ujemne.")
    if settings.hand_median_window < 1 or settings.hand_median_window % 2 == 0:
        raise RuntimeError("POSE_HAND_MEDIAN_WINDOW musi być dodatnią liczbą nieparzystą.")
    if settings.hand_reacquire_confirm_frames < 1:
        raise RuntimeError("POSE_HAND_REACQUIRE_CONFIRM_FRAMES musi wynosić co najmniej 1.")
    if settings.holding_min_confirmation_seconds <= 0.0:
        raise RuntimeError("Minimalny czas potwierdzenia holding musi być większy od zera.")
    if settings.holding_release_confirmation_seconds < 0.0:
        raise RuntimeError("Czas potwierdzenia release nie może być ujemny.")
    if settings.holding_max_unknown_gap_seconds < 0.0:
        raise RuntimeError("Maksymalna luka holding nie może być ujemna.")
    holding_thresholds = (
        settings.holding_enter_threshold,
        settings.holding_keep_threshold,
        settings.holding_exit_threshold,
    )
    if any(not 0.0 <= value <= 1.0 for value in holding_thresholds):
        raise RuntimeError("Progi holding V2 muszą mieścić się w zakresie 0-1.")
    if not (
        settings.holding_enter_threshold
        > settings.holding_keep_threshold
        > settings.holding_exit_threshold
    ):
        raise RuntimeError("Progi holding muszą spełniać ENTER > KEEP > EXIT.")
    if settings.holding_min_static_seconds < 0.0:
        raise RuntimeError("POSE_HOLDING_MIN_STATIC_SECONDS nie może być ujemne.")
    if not 0.0 <= settings.render_quality_threshold <= 1.0:
        raise RuntimeError("POSE_RENDER_QUALITY_THRESHOLD musi mieścić się w zakresie 0-1.")
    if not 0 <= settings.render_fade_frames <= 8:
        raise RuntimeError("POSE_RENDER_FADE_FRAMES musi mieścić się w zakresie 0-8.")

    return settings


def create_hand_pipeline_config(
    settings: PoseWorkerSettings,
) -> HandPipelineConfig:
    return HandPipelineConfig(
        model_path=settings.hand_model_path,
        num_hands=2,
        detection_confidence=settings.hand_detection_confidence,
        presence_confidence=settings.hand_presence_confidence,
        tracking_confidence=settings.hand_tracking_confidence,
        assignment_max_wrist_distance_ratio=(
            settings.hand_assignment_max_wrist_distance_ratio
        ),
        handedness_soft_penalty=settings.hand_handedness_soft_penalty,
        min_palm_size_pixels=settings.hand_min_palm_size_pixels,
        min_forearm_pixels=settings.hand_min_forearm_pixels,
        min_lock_frames=settings.hand_min_lock_frames,
        max_interpolation_gap_frames=(
            settings.hand_max_interpolation_gap_frames
        ),
        max_root_wrist_distance_ratio=(
            settings.hand_max_root_wrist_distance_ratio
        ),
        min_scale_ratio=settings.hand_min_scale_ratio,
        max_scale_ratio=settings.hand_max_scale_ratio,
        max_scale_change_ratio=settings.hand_max_scale_change_ratio,
        max_orientation_change_degrees=(
            settings.hand_max_orientation_change_degrees
        ),
        max_joint_velocity_palm_ratio=(
            settings.hand_max_joint_velocity_palm_ratio
        ),
        max_median_joint_velocity_palm_ratio=(
            settings.hand_max_median_joint_velocity_palm_ratio
        ),
        max_world_depth_jump_meters=(
            settings.hand_max_world_depth_jump_meters
        ),
        bone_log_tolerance=settings.hand_bone_log_tolerance,
        max_bone_outliers=settings.hand_max_bone_outliers,
        max_hand_radius_forearm_ratio=(
            settings.hand_max_radius_forearm_ratio
        ),
        max_bone_forearm_ratio=settings.hand_max_bone_forearm_ratio,
        median_window=settings.hand_median_window,
        smoothing_alpha=settings.hand_smoothing_alpha,
        bone_projection_strength=settings.hand_bone_projection_strength,
        edge_margin_ratio=settings.body_edge_margin_ratio,
        reacquire_confirm_frames=settings.hand_reacquire_confirm_frames,
    )


def configure_text_streams() -> None:
    """Use UTF-8 for worker logs when stdout/stderr are redirected to the manager."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass


def configure_logging() -> logging.Logger:
    configure_text_streams()
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ergonomia-ai-pose-worker")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_DIRECTORY / "pose-worker.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def create_supabase_client(settings: PoseWorkerSettings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_secret_key)


def claim_next_pose_analysis(
    supabase: Client,
    worker_id: str,
) -> dict[str, Any] | None:
    response = supabase.rpc(
        "claim_next_pose_analysis",
        {"p_worker_id": worker_id},
    ).execute()

    rows = response.data or []
    return rows[0] if rows else None


def update_progress(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    progress: int,
    stage: str,
) -> None:
    safe_progress = max(1, min(99, int(progress)))

    response = supabase.rpc(
        "update_analysis_progress",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_progress": safe_progress,
            "p_processing_stage": stage,
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Worker utracił blokadę analizy podczas aktualizacji postępu."
        )


def maybe_update_progress(
    supabase: Client | None,
    analysis_id: str,
    worker_id: str,
    progress: int,
    stage: str,
) -> None:
    if supabase is not None:
        update_progress(supabase, analysis_id, worker_id, progress, stage)


def mark_analysis_failed(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    error: Exception,
) -> None:
    response = supabase.rpc(
        "fail_analysis_processing",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_error_code": str(
                getattr(error, "error_code", type(error).__name__.upper())
            )[:100],
            "p_error_message": str(error),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError("Nie udało się oznaczyć analizy jako failed.")


class StrictWholebodyModel:
    """
    Dwustopniowy model bez fallbacku RTMPose do całej klatki.

    1. Wieloklasowy COCO YOLOX-X wykrywa obiekty.
    2. Zachowujemy wyłącznie klasę 0 = person.
    3. RTMW otrzymuje wyłącznie zatwierdzone bounding boxy.
    4. Initial acquisition zawsze wymaga bounding boxa z YOLOX.

    Pose V6 może osobno wywołać ``infer_on_bboxes`` dla krótkotrwałego,
    track-conditioned recovery ROI. Nie jest to inference całej klatki, a jego
    źródło jest zapisywane jako TRACK_PREDICTED zamiast YOLOX_MEASURED.
    """

    def __init__(
        self,
        settings: PoseWorkerSettings,
    ) -> None:
        self.settings = settings

        self.detector = YOLOX(
            onnx_model=COCO_PERSON_DETECTOR_URL,
            model_input_size=(640, 640),
            mode="multiclass",
            nms_thr=settings.detector_nms_threshold,
            score_thr=settings.detector_score_threshold,
            backend="onnxruntime",
            device="cuda",
        )

        self.pose_model = RTMPose(
            onnx_model=RTMW_PERFORMANCE_URL,
            model_input_size=(288, 384),
            to_openpose=False,
            backend="onnxruntime",
            device="cuda",
        )
        self.last_object_detections: list[ObjectDetection] = []
        self.last_timing_seconds: dict[str, float] = {
            "detector": 0.0,
            "pose": 0.0,
        }
        self.last_batch_diagnostics: dict[str, dict[str, object]] = {}

    def __call__(
        self,
        frame: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        frame_height, frame_width = frame.shape[:2]
        self.last_object_detections = []
        self.last_timing_seconds = {"detector": 0.0, "pose": 0.0}
        self.last_batch_diagnostics = {}

        detector_started_at = time.perf_counter()
        detection_result = self.detector(frame)
        self.last_timing_seconds["detector"] = (
            time.perf_counter() - detector_started_at
        )

        if (
            not isinstance(detection_result, tuple)
            or len(detection_result) != 2
        ):
            return self.empty_result()

        bounding_boxes, class_ids = detection_result

        bounding_boxes_array = np.asarray(
            bounding_boxes,
            dtype=np.float32,
        )
        class_ids_array = np.asarray(
            class_ids,
        ).reshape(-1)

        if (
            bounding_boxes_array.size == 0
            or class_ids_array.size == 0
        ):
            return self.empty_result()

        try:
            bounding_boxes_array = bounding_boxes_array.reshape(-1, 4)
        except ValueError:
            return self.empty_result()

        frame_area = max(
            1.0,
            float(frame_width * frame_height),
        )

        accepted_boxes: list[np.ndarray] = []

        for detection_index, (box, class_id) in enumerate(zip(
            bounding_boxes_array,
            class_ids_array,
        )):

            x1 = float(
                np.clip(
                    box[0],
                    0,
                    max(0, frame_width - 1),
                )
            )
            y1 = float(
                np.clip(
                    box[1],
                    0,
                    max(0, frame_height - 1),
                )
            )
            x2 = float(
                np.clip(
                    box[2],
                    0,
                    max(0, frame_width - 1),
                )
            )
            y2 = float(
                np.clip(
                    box[3],
                    0,
                    max(0, frame_height - 1),
                )
            )

            box_width = max(0.0, x2 - x1)
            box_height = max(0.0, y2 - y1)

            if box_width <= 1.0 or box_height <= 1.0:
                continue

            numeric_class_id = int(class_id)
            if numeric_class_id != 0:
                if numeric_class_id in HAND_RELEVANT_COCO_CLASSES:
                    class_name = (
                        COCO_CLASS_NAMES[numeric_class_id]
                        if 0 <= numeric_class_id < len(COCO_CLASS_NAMES)
                        else None
                    )
                    self.last_object_detections.append(
                        ObjectDetection(
                            bbox_xyxy=(x1, y1, x2, y2),
                            class_id=numeric_class_id,
                            class_name=class_name,
                            confidence=None,
                            detection_index=detection_index,
                        )
                    )
                continue

            height_ratio = box_height / max(
                1.0,
                float(frame_height),
            )
            area_ratio = (
                box_width * box_height / frame_area
            )
            aspect_ratio = box_width / box_height

            if (
                height_ratio
                < self.settings.detector_min_height_ratio
            ):
                continue

            if (
                area_ratio
                < self.settings.detector_min_area_ratio
            ):
                continue

            if not (
                self.settings.detector_min_aspect_ratio
                <= aspect_ratio
                <= self.settings.detector_max_aspect_ratio
            ):
                continue

            accepted_boxes.append(
                np.array(
                    [x1, y1, x2, y2],
                    dtype=np.float32,
                )
            )

        if not accepted_boxes:
            return self.empty_result()

        accepted_boxes.sort(
            key=lambda current_box: (
                float(current_box[2] - current_box[0])
                * float(current_box[3] - current_box[1])
            ),
            reverse=True,
        )

        accepted_boxes = accepted_boxes[
            : self.settings.detector_max_people
        ]

        return self.infer_on_bboxes(frame, accepted_boxes)

    def infer_on_bboxes(
        self,
        frame: np.ndarray,
        bounding_boxes: list[np.ndarray],
        *,
        timing_key: str = "pose",
        maximum_batch_size: int = 8,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run RTMW only on explicit, already bounded person ROIs."""

        if not bounding_boxes:
            return self.empty_result()
        height, width = frame.shape[:2]
        safe_boxes: list[np.ndarray] = []
        for box in bounding_boxes:
            values = np.asarray(box, dtype=np.float32).reshape(-1)
            if values.size != 4 or not np.isfinite(values).all():
                continue
            values = values.copy()
            values[[0, 2]] = np.clip(values[[0, 2]], 0.0, max(0, width - 1))
            values[[1, 3]] = np.clip(values[[1, 3]], 0.0, max(0, height - 1))
            if values[2] - values[0] >= 4.0 and values[3] - values[1] >= 4.0:
                safe_boxes.append(values)
        if not safe_boxes:
            return self.empty_result()
        batch_limit = max(1, min(int(maximum_batch_size), 32))
        batch_sizes: list[int] = []
        oom_retry_count = 0

        def infer_batch(
            boxes: list[np.ndarray],
        ) -> list[tuple[np.ndarray, np.ndarray]]:
            nonlocal oom_retry_count
            try:
                raw_points, raw_scores = self.pose_model(frame, bboxes=boxes)
                normalized = normalize_pose_arrays(raw_points, raw_scores)
                batch_sizes.append(len(boxes))
                return [normalized]
            except RuntimeError as error:
                message = str(error).lower()
                out_of_memory = any(token in message for token in (
                    "out of memory", "cuda_error_out_of_memory", "failed to allocate",
                ))
                if not out_of_memory or len(boxes) <= 1:
                    raise
                oom_retry_count += 1
                midpoint = max(1, len(boxes) // 2)
                return [
                    *infer_batch(boxes[:midpoint]),
                    *infer_batch(boxes[midpoint:]),
                ]

        pose_started_at = time.perf_counter()
        chunks: list[tuple[np.ndarray, np.ndarray]] = []
        for start in range(0, len(safe_boxes), batch_limit):
            chunks.extend(infer_batch(safe_boxes[start:start + batch_limit]))
        elapsed = time.perf_counter() - pose_started_at
        self.last_timing_seconds[timing_key] = (
            self.last_timing_seconds.get(timing_key, 0.0) + elapsed
        )
        if timing_key != "pose":
            self.last_timing_seconds["pose"] = (
                self.last_timing_seconds.get("pose", 0.0) + elapsed
            )
        batch_diagnostics = getattr(self, "last_batch_diagnostics", None)
        if not isinstance(batch_diagnostics, dict):
            batch_diagnostics = {}
            self.last_batch_diagnostics = batch_diagnostics
        batch_diagnostics[timing_key] = {
            "requested_bbox_count": len(safe_boxes),
            "configured_maximum_batch_size": batch_limit,
            "executed_batch_sizes": batch_sizes,
            "oom_retry_count": oom_retry_count,
            "quality_profile_reduced": False,
        }
        usable = [item for item in chunks if item[0].shape[0] > 0]
        if not usable:
            return self.empty_result()
        return (
            np.concatenate([item[0] for item in usable], axis=0),
            np.concatenate([item[1] for item in usable], axis=0),
        )

    @staticmethod
    def empty_result() -> tuple[np.ndarray, np.ndarray]:
        return (
            np.empty(
                (0, KEYPOINT_COUNT, 2),
                dtype=np.float32,
            ),
            np.empty(
                (0, KEYPOINT_COUNT),
                dtype=np.float32,
            ),
        )


def initialize_pose_model(
    settings: PoseWorkerSettings,
    logger: logging.Logger,
) -> StrictWholebodyModel:
    providers = ort.get_available_providers()
    logger.info(
        "ONNX Runtime providers: %s",
        providers,
    )

    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(
            "ONNX Runtime nie wykrywa CUDAExecutionProvider."
        )

    if not torch.cuda.is_available():
        raise RuntimeError(
            "PyTorch nie wykrywa karty CUDA."
        )

    logger.info(
        "GPU: %s",
        torch.cuda.get_device_name(0),
    )
    logger.info(
        "Inicjalizacja COCO YOLOX-X + RTMW performance."
    )

    started_at = time.perf_counter()

    model = StrictWholebodyModel(
        settings=settings,
    )

    logger.info(
        "Model wykrywania i pozy gotowy po %.2f s.",
        time.perf_counter() - started_at,
    )

    return model


def get_safe_video_suffix(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    return suffix if suffix in {".mp4", ".mov", ".webm"} else ".mp4"


def download_source_video(
    supabase: Client,
    settings: PoseWorkerSettings,
    analysis: dict[str, Any],
    job_directory: Path,
) -> Path:
    file_name = str(analysis.get("source_file_name") or "source.mp4")
    destination_path = job_directory / f"source{get_safe_video_suffix(file_name)}"

    file_content = (
        supabase.storage.from_(settings.source_bucket)
        .download(str(analysis["source_video_path"]))
    )

    destination_path.write_bytes(file_content)

    if destination_path.stat().st_size <= 0:
        raise RuntimeError("Pobrany film źródłowy jest pusty.")

    return destination_path


def normalize_model_scores(
    scores: np.ndarray,
) -> np.ndarray:
    """
    Sprowadza odpowiedzi RTMW do stabilnej skali 0-1.

    Część modeli zwraca wartości już znormalizowane.
    Wariant performance może zwracać dodatnie odpowiedzi SimCC
    większe niż 1, dlatego wtedy używamy funkcji sigmoid.
    """

    scores_array = np.asarray(
        scores,
        dtype=np.float32,
    )

    if scores_array.size == 0:
        return scores_array

    finite_scores = np.where(
        np.isfinite(scores_array),
        scores_array,
        -20.0,
    ).astype(np.float32)

    minimum = float(finite_scores.min())
    maximum = float(finite_scores.max())

    if minimum >= 0.0 and maximum <= 1.0001:
        return np.clip(
            finite_scores,
            0.0,
            1.0,
        ).astype(np.float32)

    clipped_scores = np.clip(
        finite_scores,
        -20.0,
        20.0,
    )

    normalized_scores = 1.0 / (
        1.0 + np.exp(-clipped_scores)
    )

    return np.clip(
        normalized_scores,
        0.0,
        1.0,
    ).astype(np.float32)


def normalize_pose_arrays(
    keypoints: Any,
    scores: Any,
) -> tuple[np.ndarray, np.ndarray]:
    keypoints_array = np.asarray(
        keypoints,
        dtype=np.float32,
    )
    scores_array = np.asarray(
        scores,
        dtype=np.float32,
    )

    if (
        keypoints_array.ndim == 2
        and keypoints_array.shape[-1] == 2
    ):
        keypoints_array = keypoints_array[
            np.newaxis,
            ...,
        ]

    if scores_array.ndim == 1:
        scores_array = scores_array[
            np.newaxis,
            ...,
        ]

    if (
        keypoints_array.ndim != 3
        or scores_array.ndim != 2
        or keypoints_array.shape[0]
        != scores_array.shape[0]
    ):
        return (
            np.empty(
                (0, KEYPOINT_COUNT, 2),
                dtype=np.float32,
            ),
            np.empty(
                (0, KEYPOINT_COUNT),
                dtype=np.float32,
            ),
        )

    if keypoints_array.shape[-1] != 2:
        return (
            np.empty(
                (0, KEYPOINT_COUNT, 2),
                dtype=np.float32,
            ),
            np.empty(
                (0, KEYPOINT_COUNT),
                dtype=np.float32,
            ),
        )

    scores_array = normalize_model_scores(
        scores_array
    )

    return (
        keypoints_array,
        scores_array,
    )


def bbox_iou(
    first: np.ndarray,
    second: np.ndarray,
) -> float:
    x1 = max(
        float(first[0]),
        float(second[0]),
    )
    y1 = max(
        float(first[1]),
        float(second[1]),
    )
    x2 = min(
        float(first[2]),
        float(second[2]),
    )
    y2 = min(
        float(first[3]),
        float(second[3]),
    )

    intersection = (
        max(0.0, x2 - x1)
        * max(0.0, y2 - y1)
    )

    first_area = (
        max(0.0, float(first[2] - first[0]))
        * max(0.0, float(first[3] - first[1]))
    )
    second_area = (
        max(0.0, float(second[2] - second[0]))
        * max(0.0, float(second[3] - second[1]))
    )

    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def bbox_center_distance_ratio(
    first: np.ndarray,
    second: np.ndarray,
    frame_width: int,
    frame_height: int,
) -> float:
    first_center = np.array(
        [
            (
                float(first[0])
                + float(first[2])
            )
            / 2.0,
            (
                float(first[1])
                + float(first[3])
            )
            / 2.0,
        ],
        dtype=np.float32,
    )

    second_center = np.array(
        [
            (
                float(second[0])
                + float(second[2])
            )
            / 2.0,
            (
                float(second[1])
                + float(second[3])
            )
            / 2.0,
        ],
        dtype=np.float32,
    )

    frame_diagonal = max(
        1.0,
        math.hypot(
            frame_width,
            frame_height,
        ),
    )

    return float(
        np.linalg.norm(
            first_center - second_center
        )
        / frame_diagonal
    )


def get_body_bbox(
    keypoints: np.ndarray,
    scores: np.ndarray,
    threshold: float,
) -> np.ndarray | None:
    usable_count = min(BODY_POINT_COUNT, keypoints.shape[0], scores.shape[0])
    valid_mask = scores[:usable_count] >= threshold

    if int(np.count_nonzero(valid_mask)) < 2:
        return None

    valid_points = keypoints[:usable_count][valid_mask]

    if valid_points.size == 0 or not np.isfinite(valid_points).all():
        return None

    return np.array(
        [
            float(valid_points[:, 0].min()),
            float(valid_points[:, 1].min()),
            float(valid_points[:, 0].max()),
            float(valid_points[:, 1].max()),
        ],
        dtype=np.float32,
    )


def _refinement_body_is_valid(
    points: np.ndarray,
    scores: np.ndarray,
    bbox: np.ndarray,
    settings: PoseWorkerSettings,
) -> bool:
    """Conservative, stateless gate before a Pass 2 candidate can replace V1.

    The accepted candidate is subsequently replayed through the complete
    stateful biomechanical graph. This first gate prevents obviously broken
    crops and impossible bones from entering that replay.
    """

    if bbox.shape != (4,) or not np.isfinite(bbox).all():
        return False
    bbox_height = float(bbox[3] - bbox[1])
    if bbox_height <= 1.0:
        return False
    valid = (
        np.isfinite(points[:BODY_POINT_COUNT]).all(axis=1)
        & np.isfinite(scores[:BODY_POINT_COUNT])
        & (scores[:BODY_POINT_COUNT] >= settings.body_presence_threshold)
    )
    if int(np.count_nonzero(valid)) < settings.body_min_keypoints:
        return False
    for joint_a, joint_b in BODY_BONES.values():
        if not (valid[joint_a] and valid[joint_b]):
            continue
        length_ratio = float(np.linalg.norm(points[joint_b] - points[joint_a])) / bbox_height
        if not 0.003 <= length_ratio <= 0.70:
            return False
    return True


def _timestamp_durations(timestamps: list[float], fps: float) -> list[float]:
    fallback = 1.0 / max(fps, 1e-6)
    if not timestamps:
        return []
    output = []
    for index in range(len(timestamps) - 1):
        delta = timestamps[index + 1] - timestamps[index]
        output.append(delta if math.isfinite(delta) and delta > 0.0 else fallback)
    output.append(output[-1] if output else fallback)
    return output


def _holding_v3_evidence(frame: Any) -> HoldingEvidenceV3:
    proximity = (
        max(0.0, min(1.0, 1.0 - float(frame.object_proximity_ratio)))
        if frame.object_proximity_ratio is not None
        else 0.0
    )
    return HoldingEvidenceV3(
        grip=float(frame.evidence.grip_evidence),
        contact_evidence=max(float(frame.evidence.object_evidence), float(frame.evidence.occlusion_evidence)),
        object_proximity=proximity,
        common_motion=float(frame.common_motion_score),
        temporal_persistence=float(frame.evidence.temporal_evidence),
        occlusion_pattern=float(frame.evidence.occlusion_evidence),
        release=float(frame.evidence.release_evidence),
        quality=max(0.0, min(1.0, 1.0 - float(frame.evidence.quality_penalty))),
        object_track_id=frame.object_track_id,
        object_class=frame.object_class,
    )


def _summarize_holding_v3(frames: list[Any], durations: list[float]) -> dict[str, object]:
    likely = {HoldingStateV3.LIKELY_HOLDING, HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT}
    flags = [frame.state in likely for frame in frames]
    return {
        "likely_holding_seconds": round(sum(duration for duration, flag in zip(durations, flags) if flag), 6),
        "possible_holding_seconds": round(sum(duration for duration, frame in zip(durations, frames) if frame.state is HoldingStateV3.POSSIBLE_HOLDING), 6),
        "unknown_seconds": round(sum(duration for duration, frame in zip(durations, frames) if frame.state is HoldingStateV3.UNKNOWN), 6),
        "holding_episode_count": sum(flag and (index == 0 or not flags[index - 1]) for index, flag in enumerate(flags)),
        "external_load_known": False,
    }


def select_primary_person(
    keypoints: np.ndarray,
    scores: np.ndarray,
    frame_width: int,
    frame_height: int,
    settings: PoseWorkerSettings,
    previous_bbox: np.ndarray | None,
    presence_threshold: float | None = None,
) -> PoseCandidate | None:
    best_candidate: PoseCandidate | None = None
    effective_presence_threshold = (
        float(np.clip(presence_threshold, 0.0, 1.0))
        if presence_threshold is not None
        else settings.body_presence_threshold
    )

    frame_area = max(
        1.0,
        float(frame_width * frame_height),
    )

    people_count = min(
        keypoints.shape[0],
        scores.shape[0],
    )

    for person_index in range(people_count):
        person_keypoints = keypoints[
            person_index
        ]
        person_scores = scores[
            person_index
        ]

        usable_body_count = min(
            BODY_POINT_COUNT,
            person_keypoints.shape[0],
            person_scores.shape[0],
        )

        if usable_body_count <= 0:
            continue

        body_scores = person_scores[
            :usable_body_count
        ]
        body_valid_mask = (
            body_scores
            >= effective_presence_threshold
        )
        body_keypoint_count = int(
            np.count_nonzero(
                body_valid_mask
            )
        )

        if (
            body_keypoint_count
            < settings.body_min_keypoints
        ):
            continue

        shoulder_indices = [
            index
            for index in (5, 6)
            if (
                index < usable_body_count
                and body_scores[index]
                >= effective_presence_threshold
            )
        ]
        hip_indices = [
            index
            for index in (11, 12)
            if (
                index < usable_body_count
                and body_scores[index]
                >= effective_presence_threshold
            )
        ]

        if not shoulder_indices or not hip_indices:
            continue

        bbox = get_body_bbox(
            person_keypoints,
            person_scores,
            effective_presence_threshold,
        )

        if bbox is None:
            continue

        bbox_width = max(
            0.0,
            float(bbox[2] - bbox[0]),
        )
        bbox_height = max(
            0.0,
            float(bbox[3] - bbox[1]),
        )
        bbox_area_ratio = (
            bbox_width * bbox_height / frame_area
        )
        person_height_ratio = (
            bbox_height
            / max(1.0, float(frame_height))
        )

        if (
            bbox_area_ratio
            < settings.detector_min_area_ratio
        ):
            continue

        if (
            person_height_ratio
            < settings.detector_min_height_ratio
        ):
            continue

        shoulder_center = np.mean(
            person_keypoints[shoulder_indices],
            axis=0,
        )
        hip_center = np.mean(
            person_keypoints[hip_indices],
            axis=0,
        )

        if (
            not np.isfinite(shoulder_center).all()
            or not np.isfinite(hip_center).all()
        ):
            continue

        torso_length = float(
            np.linalg.norm(
                shoulder_center - hip_center
            )
        )

        minimum_torso_length = max(
            10.0,
            frame_height * 0.045,
        )

        if (
            not math.isfinite(torso_length)
            or torso_length
            < minimum_torso_length
        ):
            continue

        # Biodra nie powinny leżeć wyraźnie powyżej ramion.
        if (
            float(hip_center[1])
            < float(shoulder_center[1])
            - frame_height * 0.04
        ):
            continue

        current_iou = 0.0
        center_jump = 0.0

        if previous_bbox is not None:
            current_iou = bbox_iou(
                bbox,
                previous_bbox,
            )
            center_jump = (
                bbox_center_distance_ratio(
                    bbox,
                    previous_bbox,
                    frame_width,
                    frame_height,
                )
            )

            # Kandydat daleko od śledzonej osoby nie może
            # przejąć trackingu, nawet gdy ma wysokie score.
            if (
                current_iou
                < settings.track_min_iou
                and center_jump
                > settings.track_max_center_jump_ratio
            ):
                continue

        confident_body_scores = body_scores[
            body_valid_mask
        ]

        average_confidence = (
            float(
                confident_body_scores.mean()
            )
            if confident_body_scores.size > 0
            else 0.0
        )
        average_confidence = float(
            np.clip(
                average_confidence,
                0.0,
                1.0,
            )
        )

        visibility_quality = min(
            1.0,
            body_keypoint_count / 16.0,
        )
        area_quality = min(
            1.0,
            bbox_area_ratio / 0.20,
        )

        if previous_bbox is not None:
            movement_quality = max(
                0.0,
                1.0
                - center_jump
                / max(
                    0.001,
                    settings.track_max_center_jump_ratio,
                ),
            )
            continuity = max(
                current_iou,
                movement_quality,
            )
        else:
            continuity = 0.0

        selection_score = (
            0.25 * average_confidence
            + 0.12 * visibility_quality
            + 0.08 * area_quality
            + 0.55 * continuity
            if previous_bbox is not None
            else 0.58 * average_confidence
            + 0.25 * visibility_quality
            + 0.17 * area_quality
        )
        selection_score = float(
            np.clip(
                selection_score,
                0.0,
                1.0,
            )
        )

        candidate = PoseCandidate(
            keypoints=person_keypoints.copy(),
            scores=person_scores.copy(),
            bbox=bbox,
            body_keypoint_count=body_keypoint_count,
            body_average_confidence=average_confidence,
            selection_score=selection_score,
        )

        if (
            best_candidate is None
            or candidate.selection_score
            > best_candidate.selection_score
        ):
            best_candidate = candidate

    return best_candidate





def scan_active_segment(
    supabase: Client | None,
    settings: PoseWorkerSettings,
    model: StrictWholebodyModel,
    analysis_id: str,
    video_path: Path,
    logger: logging.Logger,
) -> ActiveSegment:
    capture = cv2.VideoCapture(
        str(video_path)
    )

    if not capture.isOpened():
        raise RuntimeError(
            "OpenCV nie może otworzyć filmu "
            "do skanowania obecności."
        )

    try:
        fps = float(
            capture.get(
                cv2.CAP_PROP_FPS
            )
        )
        total_frames = int(
            capture.get(
                cv2.CAP_PROP_FRAME_COUNT
            )
        )
        width = int(
            capture.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )
        )
        height = int(
            capture.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )
        )

        if (
            fps <= 0
            or total_frames <= 0
            or width <= 0
            or height <= 0
        ):
            raise RuntimeError(
                "Film ma nieprawidłowe parametry techniczne."
            )

        scan_stride = max(
            1,
            int(
                round(
                    fps / settings.scan_fps
                )
            ),
        )
        sample_frames = list(
            range(
                0,
                total_frames,
                scan_stride,
            )
        )

        start_confirm_samples = max(
            2,
            int(
                math.ceil(
                    settings.scan_start_confirm_seconds
                    * fps
                    / scan_stride
                )
            ),
        )
        end_confirm_samples = max(
            2,
            int(
                math.ceil(
                    settings.scan_end_confirm_seconds
                    * fps
                    / scan_stride
                )
            ),
        )

        logger.info(
            "Skan obecności V4: %d próbek, "
            "co %d klatek (około %.2f FPS), "
            "start=%d trafienia, koniec=%d braki.",
            len(sample_frames),
            scan_stride,
            fps / scan_stride,
            start_confirm_samples,
            end_confirm_samples,
        )

        previous_bbox: np.ndarray | None = None

        consecutive_hits = 0
        consecutive_misses = 0

        potential_start_sample: int | None = None
        confirmed_start_sample: int | None = None
        last_valid_sample: int | None = None
        confirmed_segments: list[tuple[int, int]] = []

        presence_flags: list[bool] = []
        accepted_qualities: list[float] = []

        for sample_number, frame_index in enumerate(
            sample_frames
        ):
            capture.set(
                cv2.CAP_PROP_POS_FRAMES,
                frame_index,
            )
            success, frame = capture.read()

            candidate: PoseCandidate | None = None

            if (
                success
                and frame is not None
                and frame.size > 0
            ):
                keypoints_array, scores_array = model(
                    frame
                )

                candidate = select_primary_person(
                    keypoints_array,
                    scores_array,
                    width,
                    height,
                    settings,
                    previous_bbox,
                )

            candidate_quality = (
                candidate.selection_score
                if candidate is not None
                else 0.0
            )
            strong_presence = (
                candidate is not None
                and candidate_quality
                >= settings.scan_min_quality
            )

            presence_flags.append(
                strong_presence
            )
            accepted_qualities.append(
                candidate_quality
                if strong_presence
                else 0.0
            )

            if confirmed_start_sample is None:
                if strong_presence:
                    if consecutive_hits == 0:
                        potential_start_sample = (
                            sample_number
                        )

                    consecutive_hits += 1
                    previous_bbox = (
                        candidate.bbox
                        if candidate is not None
                        else None
                    )

                    if (
                        consecutive_hits
                        >= start_confirm_samples
                    ):
                        confirmed_start_sample = (
                            potential_start_sample
                        )
                        last_valid_sample = (
                            sample_number
                        )
                        consecutive_misses = 0

                        logger.info(
                            "Potwierdzono pracownika od %.3f s.",
                            sample_frames[
                                confirmed_start_sample
                            ]
                            / fps,
                        )
                else:
                    consecutive_hits = 0
                    potential_start_sample = None
                    previous_bbox = None
            else:
                if strong_presence:
                    last_valid_sample = (
                        sample_number
                    )
                    consecutive_misses = 0
                    previous_bbox = (
                        candidate.bbox
                        if candidate is not None
                        else previous_bbox
                    )
                else:
                    consecutive_misses += 1

                    if (
                        consecutive_misses
                        >= end_confirm_samples
                    ):
                        logger.info(
                            "Potwierdzono koniec obecności "
                            "po %.3f s.",
                            frame_index / fps,
                        )
                        if confirmed_start_sample is not None and last_valid_sample is not None:
                            confirmed_segments.append((confirmed_start_sample, last_valid_sample))
                        confirmed_start_sample = None
                        last_valid_sample = None
                        consecutive_hits = 0
                        consecutive_misses = 0
                        potential_start_sample = None
                        previous_bbox = None

            if sample_number % 10 == 0:
                progress = (
                    22
                    + int(
                        7
                        * sample_number
                        / max(
                            1,
                            len(sample_frames) - 1,
                        )
                    )
                )

                maybe_update_progress(
                    supabase,
                    analysis_id,
                    settings.worker_id,
                    progress,
                    "detecting-active-segment-v3",
                )

        if confirmed_start_sample is not None and last_valid_sample is not None:
            confirmed_segments.append((confirmed_start_sample, last_valid_sample))

        if not confirmed_segments:
            raise RuntimeError(
                "Nie wykryto stabilnego fragmentu "
                "z prawdziwym pracownikiem."
            )

        confirmed_start_sample = confirmed_segments[0][0]
        last_valid_sample = confirmed_segments[-1][1]
        detected_start_frame = sample_frames[confirmed_start_sample]
        detected_end_frame = min(
            total_frames - 1,
            sample_frames[last_valid_sample]
            + scan_stride
            - 1,
        )

        start_frame = max(
            0,
            detected_start_frame
            - int(
                round(
                    settings.active_pre_padding_seconds
                    * fps
                )
            ),
        )
        end_frame = min(
            total_frames - 1,
            detected_end_frame
            + int(
                round(
                    settings.active_post_padding_seconds
                    * fps
                )
            ),
        )

        if end_frame <= start_frame:
            raise RuntimeError(
                "Wykryty aktywny fragment "
                "ma nieprawidłową długość."
            )

        active_duration = (
            end_frame - start_frame + 1
        ) / fps

        if (
            active_duration
            < settings.min_active_seconds
        ):
            raise RuntimeError(
                "Wykryty fragment z pracownikiem jest zbyt krótki: "
                f"{active_duration:.3f} s."
            )

        selected_flags = presence_flags[
            confirmed_start_sample
            : last_valid_sample + 1
        ]
        selected_qualities = [
            value
            for value in accepted_qualities[
                confirmed_start_sample
                : last_valid_sample + 1
            ]
            if value > 0.0
        ]

        scan_presence_ratio = (
            sum(selected_flags)
            / len(selected_flags)
            if selected_flags
            else 0.0
        )
        average_scan_quality = (
            float(
                np.mean(
                    selected_qualities
                )
            )
            if selected_qualities
            else 0.0
        )
        pre_padding_frames = int(round(settings.active_pre_padding_seconds * fps))
        post_padding_frames = int(round(settings.active_post_padding_seconds * fps))
        segment_parts = tuple(
            ActiveSegmentPart(
                start_frame=max(0, sample_frames[start_sample] - pre_padding_frames),
                end_frame=min(
                    total_frames - 1,
                    sample_frames[end_sample] + scan_stride - 1 + post_padding_frames,
                ),
                start_seconds=round(
                    max(0, sample_frames[start_sample] - pre_padding_frames) / fps,
                    3,
                ),
                end_seconds=round(
                    (
                        min(
                            total_frames - 1,
                            sample_frames[end_sample] + scan_stride - 1 + post_padding_frames,
                        )
                        + 1
                    )
                    / fps,
                    3,
                ),
            )
            for start_sample, end_sample in confirmed_segments
        )

        logger.info(
            "Aktywny zakres V5.1: "
            "%.3f-%.3f s (%d-%d), "
            "długość %.3f s, segmenty=%d, jakość %.3f.",
            start_frame / fps,
            (end_frame + 1) / fps,
            start_frame,
            end_frame,
            active_duration,
            len(segment_parts),
            average_scan_quality,
        )

        return ActiveSegment(
            start_frame=start_frame,
            end_frame=end_frame,
            start_seconds=round(
                start_frame / fps,
                3,
            ),
            end_seconds=round(
                (end_frame + 1) / fps,
                3,
            ),
            duration_seconds=round(
                active_duration,
                3,
            ),
            scan_stride=scan_stride,
            scan_presence_ratio=round(
                scan_presence_ratio,
                6,
            ),
            segments=segment_parts,
        )
    finally:
        capture.release()


def create_video_writer(
    output_path: Path,
    fps: float,
    width: int,
    height: int,
) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError("Nie udało się utworzyć roboczego filmu wynikowego.")

    return writer


def resolve_ffmpeg_binary() -> str:
    configured_path = os.getenv("FFMPEG_PATH", "").strip()
    path_from_system = shutil.which("ffmpeg")
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()

    winget_alias_path = (
        Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if local_app_data
        else None
    )

    candidates = [
        configured_path or None,
        path_from_system,
        str(winget_alias_path) if winget_alias_path is not None else None,
    ]

    for candidate in candidates:
        if not candidate:
            continue

        candidate_path = Path(candidate).expanduser()

        if candidate_path.exists() and candidate_path.is_file():
            return str(candidate_path.resolve())

    raise RuntimeError(
        "Nie znaleziono programu FFmpeg. Ustaw FFMPEG_PATH w worker/.env."
    )


def transcode_video_to_h264(
    source_path: Path,
    destination_path: Path,
    logger: logging.Logger,
    crf: int,
) -> None:
    ffmpeg_binary = resolve_ffmpeg_binary()

    if not source_path.exists() or source_path.stat().st_size <= 0:
        raise RuntimeError("Roboczy film przed konwersją nie istnieje albo jest pusty.")

    destination_path.unlink(missing_ok=True)

    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-movflags",
        "+faststart",
        "-tag:v",
        "avc1",
        str(destination_path),
    ]

    logger.info("Konwersja aktywnego fragmentu do H.264...")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "Nieznany błąd FFmpeg."
        raise RuntimeError(f"Konwersja H.264 nie powiodła się: {details[-2000:]}")

    if not destination_path.exists() or destination_path.stat().st_size <= 0:
        raise RuntimeError("FFmpeg nie utworzył poprawnego filmu H.264.")

    logger.info(
        "Film H.264 gotowy: %.2f MB",
        destination_path.stat().st_size / 1024 / 1024,
    )


def point_is_valid(
    points: np.ndarray,
    scores: np.ndarray,
    index: int,
    threshold: float,
) -> bool:
    return (
        index < points.shape[0]
        and index < scores.shape[0]
        and float(scores[index]) >= threshold
        and np.isfinite(points[index]).all()
    )


def draw_connection(
    image: np.ndarray,
    points: np.ndarray,
    scores: np.ndarray,
    first_index: int,
    second_index: int,
    threshold: float,
    color: tuple[int, int, int],
    thickness: int,
    valid_pairs: set[tuple[int, int]] | None = None,
) -> None:
    if valid_pairs is not None and (first_index, second_index) not in valid_pairs:
        return
    if not (
        point_is_valid(points, scores, first_index, threshold)
        and point_is_valid(points, scores, second_index, threshold)
    ):
        return

    first_point = tuple(np.round(points[first_index]).astype(int))
    second_point = tuple(np.round(points[second_index]).astype(int))
    height, width = image.shape[:2]
    if not (
        0 <= first_point[0] < width
        and 0 <= first_point[1] < height
        and 0 <= second_point[0] < width
        and 0 <= second_point[1] < height
    ):
        return
    if float(np.linalg.norm(points[first_index] - points[second_index])) > 0.65 * math.hypot(width, height):
        return

    cv2.line(
        image,
        first_point,
        second_point,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_virtual_connection(
    image: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    if not np.isfinite(first).all() or not np.isfinite(second).all():
        return
    height, width = image.shape[:2]
    first_point = tuple(np.round(first).astype(int))
    second_point = tuple(np.round(second).astype(int))
    if not (
        0 <= first_point[0] < width
        and 0 <= first_point[1] < height
        and 0 <= second_point[0] < width
        and 0 <= second_point[1] < height
    ):
        return
    if float(np.linalg.norm(first - second)) > 0.65 * math.hypot(width, height):
        return
    cv2.line(
        image,
        first_point,
        second_point,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_precise_pose(
    frame: np.ndarray,
    points: np.ndarray,
    scores: np.ndarray,
    settings: PoseWorkerSettings,
    bone_validity: dict[str, bool] | None = None,
) -> np.ndarray:
    output = frame.copy()
    height, width = output.shape[:2]
    thickness = max(2, int(round(min(width, height) / 280)))
    joint_radius = max(3, thickness + 1)

    torso_color = (245, 245, 245)
    left_color = (255, 210, 40)
    right_color = (80, 225, 120)
    hand_color = (60, 180, 255)
    threshold = settings.keypoint_threshold
    if bone_validity is not None:
        known_pairs = {pair: name for name, pair in BODY_BONES.items()}
        valid_pairs = {
            pair
            for pair in (*TORSO_EDGES, *LEFT_BODY_EDGES, *RIGHT_BODY_EDGES)
            if pair not in known_pairs or bone_validity.get(known_pairs[pair], False)
        }
    else:
        valid_pairs = None

    for first_index, second_index in TORSO_EDGES:
        draw_connection(
            output,
            points,
            scores,
            first_index,
            second_index,
            threshold,
            torso_color,
            thickness,
            valid_pairs,
        )

    for first_index, second_index in LEFT_BODY_EDGES:
        draw_connection(
            output,
            points,
            scores,
            first_index,
            second_index,
            threshold,
            left_color,
            thickness,
            valid_pairs,
        )

    for first_index, second_index in RIGHT_BODY_EDGES:
        draw_connection(
            output,
            points,
            scores,
            first_index,
            second_index,
            threshold,
            right_color,
            thickness,
            valid_pairs,
        )

    # Wirtualna linia kark-tułów: stabilniejsza i czytelniejsza
    # niż gęsta siatka twarzy.
    if (
        point_is_valid(points, scores, 5, threshold)
        and point_is_valid(points, scores, 6, threshold)
        and (
            bone_validity is None
            or bone_validity.get("shoulders", False)
        )
    ):
        neck = (points[5] + points[6]) / 2.0
        neck_score = min(float(scores[5]), float(scores[6]))

        if (
            point_is_valid(points, scores, 11, threshold)
            and point_is_valid(points, scores, 12, threshold)
            and (
                bone_validity is None
                or all(
                    bone_validity.get(name, False)
                    for name in ("hips", "left_torso", "right_torso")
                )
            )
        ):
            pelvis = (points[11] + points[12]) / 2.0
            draw_virtual_connection(
                output,
                neck,
                pelvis,
                torso_color,
                thickness + 1,
            )

        if point_is_valid(points, scores, 0, threshold) and neck_score >= threshold:
            draw_virtual_connection(
                output,
                points[0],
                neck,
                torso_color,
                thickness,
            )

    if settings.draw_face:
        face_indices = range(23, min(91, points.shape[0]))

        for index in face_indices:
            if point_is_valid(points, scores, index, threshold):
                cv2.circle(
                    output,
                    tuple(np.round(points[index]).astype(int)),
                    max(1, joint_radius - 2),
                    (180, 180, 180),
                    -1,
                    cv2.LINE_AA,
                )

    for index in range(min(BODY_POINT_COUNT, points.shape[0])):
        if point_is_valid(points, scores, index, threshold):
            color = left_color if index in {5, 7, 9, 11, 13, 15, 17, 18, 19} else right_color

            if index in {0, 1, 2, 3, 4}:
                color = torso_color

            cv2.circle(
                output,
                tuple(np.round(points[index]).astype(int)),
                joint_radius,
                color,
                -1,
                cv2.LINE_AA,
            )

    return output


def serialize_coordinates(
    points: np.ndarray,
    scores: np.ndarray,
) -> list[list[float | None]]:
    serialized: list[list[float | None]] = []

    for index in range(KEYPOINT_COUNT):
        if (
            index < points.shape[0]
            and index < scores.shape[0]
            and float(scores[index]) > 0
            and np.isfinite(points[index]).all()
        ):
            serialized.append(
                [
                    round(float(points[index, 0]), 2),
                    round(float(points[index, 1]), 2),
                ]
            )
        else:
            serialized.append([None, None])

    return serialized


def serialize_scores(scores: np.ndarray) -> list[float]:
    output = [0.0] * KEYPOINT_COUNT

    for index in range(min(KEYPOINT_COUNT, scores.shape[0])):
        value = float(scores[index])
        output[index] = round(value, 4) if math.isfinite(value) else 0.0

    return output


def summarize_overlay_movement(
    metric_frames: list[dict[str, dict[str, object]]],
    timestamps: list[float],
) -> dict[str, object]:
    """Summarize measured metric movement without inventing missing samples."""

    names = sorted({name for frame in metric_frames for name in frame})
    result: dict[str, object] = {}
    for name in names:
        samples: list[tuple[int, float, float]] = []
        for index, frame in enumerate(metric_frames):
            metric = frame.get(name, {})
            value = metric.get("value")
            if (
                metric.get("valid") is True
                and isinstance(value, (int, float))
                and math.isfinite(float(value))
                and index < len(timestamps)
                and math.isfinite(timestamps[index])
            ):
                samples.append((index, float(timestamps[index]), float(value)))
        velocities: list[float] = []
        for previous, current in zip(samples, samples[1:]):
            if current[0] != previous[0] + 1:
                continue
            delta = current[1] - previous[1]
            if delta > 1e-6:
                velocities.append(abs(current[2] - previous[2]) / delta)
        values = np.asarray([sample[2] for sample in samples], dtype=float)
        velocity_values = np.asarray(velocities, dtype=float)
        result[name] = {
            "valid_frames": len(samples),
            "invalid_frames": max(0, len(metric_frames) - len(samples)),
            "valid_ratio": round(len(samples) / max(1, len(metric_frames)), 6),
            "movement_range": round(float(np.ptp(values)), 6) if values.size else None,
            "median_absolute_velocity": (
                round(float(np.median(velocity_values)), 6)
                if velocity_values.size
                else None
            ),
            "percentile_95_absolute_velocity": (
                round(float(np.percentile(velocity_values, 95)), 6)
                if velocity_values.size
                else None
            ),
            "derivative_unit": "metric-units-per-second",
        }
    return {
        "version": "movement-summary-v2",
        "metric_count": len(result),
        "metrics": result,
        "missing_samples_interpolated": False,
    }



def run_hand_rescue_pass(
    settings: PoseWorkerSettings,
    video_path: Path,
    body_records: list[dict[str, Any]],
    raw_hand_frames: dict[str, list[RawHandFrame]],
    hand_rois: dict[str, list[tuple[int, int, int, int] | None]],
    *,
    frame_width: int,
    frame_height: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Retry sparse hand observations without bypassing temporal validation."""

    relevant = {
        side: [
            bool(record.get("detected")) and hand_rois[side][index] is not None
            for index, record in enumerate(body_records)
        ]
        for side in ("left", "right")
    }
    before = {
        side: observation_coverage(
            [frame.observation is not None for frame in raw_hand_frames[side]],
            relevant[side],
        )
        for side in ("left", "right")
    }
    summary: dict[str, Any] = {
        "enabled": settings.hand_rescue_enabled,
        "minimum_coverage": settings.hand_rescue_minimum_coverage,
        "coverage_before": {side: round(value, 6) for side, value in before.items()},
        "coverage_after_raw_rescue": {side: round(value, 6) for side, value in before.items()},
        "attempted_frames": 0,
        "eligible_frames": {side: sum(relevant[side]) for side in ("left", "right")},
        "rescued_observations": {"left": 0, "right": 0},
        "rejected_rescue_observations": {"left": 0, "right": 0},
        "_rescued_frame_indexes": {"left": [], "right": []},
        "accepted_only_after_standard_validation": True,
    }
    if not settings.hand_rescue_enabled or not settings.draw_hands or not body_records:
        return summary

    indexes_by_side = {
        side: set(
            rescue_frame_indexes(
                [frame.observation is not None for frame in raw_hand_frames[side]],
                relevant[side],
                minimum_coverage=settings.hand_rescue_minimum_coverage,
                maximum_ratio=settings.hand_rescue_maximum_ratio,
            )
        )
        for side in ("left", "right")
    }
    rescue_indexes = sorted(indexes_by_side["left"] | indexes_by_side["right"])
    if not rescue_indexes:
        return summary

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        summary["error"] = "rescue_video_unavailable"
        return summary
    rescue_engine: MediaPipeHandEngine | None = None
    try:
        rescue_engine = MediaPipeHandEngine(create_hand_pipeline_config(settings))
        memory = HandAssignmentMemory()
        for index in rescue_indexes:
            record = body_records[index]
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(record["source_frame_index"]))
            success, frame = capture.read()
            if not success or frame is None or frame.size == 0:
                continue
            # Rescue may be requested for only one side on a given frame.
            # Do not put ``None`` into the union when the opposite hand has no
            # predicted ROI.  This was the source of:
            # TypeError: 'NoneType' object is not subscriptable.
            expanded: dict[str, tuple[int, int, int, int] | None] = {}
            for side in ("left", "right"):
                if index not in indexes_by_side[side]:
                    continue

                source_roi = hand_rois[side][index]
                if source_roi is None:
                    continue

                expanded_roi = enlarge_roi(
                    source_roi,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    scale=settings.hand_rescue_roi_scale,
                )
                if expanded_roi is not None:
                    expanded[side] = expanded_roi

            roi = union_hand_roi(
                expanded,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            if roi is None:
                continue

            try:
                candidates = rescue_engine.detect(
                    frame,
                    int(round(float(record["source_timestamp_seconds"]) * 1000.0)),
                    roi,
                    upscale_factor=settings.hand_rescue_upscale_factor,
                )
            except (RuntimeError, ValueError, cv2.error):
                continue
            assigned = assign_hands_to_body_v2(
                candidates=candidates,
                body_points=record["smoothed_points"],
                body_scores=record["smoothed_scores"],
                body_threshold=0.01,
                config=rescue_engine.config,
                graph_config=HandGraphConfig(),
                timestamp_seconds=float(record["source_timestamp_seconds"]),
                memory=memory,
            )
            for side in ("left", "right"):
                if index in indexes_by_side[side] and assigned[side].observation is not None:
                    raw_hand_frames[side][index] = assigned[side]
                    summary["rescued_observations"][side] += 1
                    summary["_rescued_frame_indexes"][side].append(index)
            summary["attempted_frames"] += 1
    except (
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        IndexError,
        OverflowError,
        cv2.error,
    ) as error:
        # Hand Rescue is an optional quality-improvement pass.  Its failure
        # must not invalidate a body/hand result already collected in Pass 1.
        logger.exception(
            "Hand Rescue pominięty po błędzie %s; zachowuję wynik Pass 1.",
            type(error).__name__,
        )
        summary["error"] = type(error).__name__
    finally:
        capture.release()
        if rescue_engine is not None:
            rescue_engine.close()

    after = {
        side: observation_coverage(
            [frame.observation is not None for frame in raw_hand_frames[side]],
            relevant[side],
        )
        for side in ("left", "right")
    }
    summary["coverage_after_raw_rescue"] = {
        side: round(value, 6) for side, value in after.items()
    }
    return summary


def _apply_pose_v6_optical_flow(
    video_path: Path,
    active_segment: ActiveSegment,
    records: list[dict[str, Any]],
    temporal_frames: list[TemporalFrame],
    config: PoseV6Config,
    *,
    frame_width: int,
    frame_height: int,
) -> list[TemporalFrame]:
    """Stream frames once and fill only still-missing, short analytical gaps."""

    if not config.optical_flow.enabled or not records or not temporal_frames:
        return temporal_frames
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("OpenCV cannot open source for Pose V6 optical flow")
    capture.set(cv2.CAP_PROP_POS_FRAMES, active_segment.start_frame)
    output = list(temporal_frames)
    previous_gray: np.ndarray | None = None
    previous_frame: TemporalFrame | None = None
    last_anchor_timestamps = np.full((BODY_POINT_COUNT,), np.nan, dtype=np.float64)
    try:
        for index, record in enumerate(records):
            success, image = capture.read()
            if not success or image is None or image.size == 0:
                raise RuntimeError(f"Cannot read optical-flow frame {record['source_frame_index']}")
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            timestamp = float(record["source_timestamp_seconds"])
            scene_cut = bool(
                record["camera_motion"] is not None
                and record["camera_motion"].scene_cut
            )
            current = output[index]
            if scene_cut:
                previous_gray = None
                previous_frame = None
                last_anchor_timestamps[:] = np.nan
            for joint in range(min(BODY_POINT_COUNT, len(current.sources))):
                if current.analysis_scores[joint] > 0.0:
                    if current.sources[joint] != PointSource.FLOW_TRACKED:
                        last_anchor_timestamps[joint] = timestamp
                    continue
                if previous_gray is None or previous_frame is None or previous_frame.analysis_scores[joint] <= 0.0:
                    continue
                anchor_timestamp = last_anchor_timestamps[joint]
                age = timestamp - anchor_timestamp if np.isfinite(anchor_timestamp) else math.inf
                if age > config.optical_flow.maximum_age_seconds:
                    continue
                bbox = record.get("bbox_array")
                graph = record["pose_graph"]
                flow = track_point_forward_backward(
                    previous_gray,
                    gray,
                    tuple(float(value) for value in previous_frame.analysis_points[joint]),
                    config=config.optical_flow,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    body_bbox=bbox if isinstance(bbox, np.ndarray) else None,
                    body_scale=float(graph.body_scale),
                )
                if flow.valid and flow.point is not None and flow.forward_backward_error is not None:
                    current = merge_flow_result(
                        current,
                        joint,
                        flow.point,
                        flow.flow_quality,
                        flow.forward_backward_error,
                        age,
                    )
            output[index] = current
            previous_gray = gray
            previous_frame = current
    finally:
        capture.release()
    return output


def _run_high_motion_recovery_pass(
    video_path: Path,
    records: list[dict[str, Any]],
    model: StrictWholebodyModel,
    settings: PoseWorkerSettings,
    config: PoseV6Config,
    *,
    frame_width: int,
    frame_height: int,
    critical_frame_indexes: set[int],
    logger: logging.Logger,
) -> dict[str, object]:
    """Run batched limb-context RTMW only where motion evidence warrants it."""

    summary: dict[str, object] = {
        "enabled": config.high_motion.enabled,
        "profile": config.profile,
        "temporal_supersampling_factor": config.high_motion.temporal_supersampling_factor,
        "high_motion_frame_count": 0,
        "specialist_frame_count": 0,
        "attempted_chain_count": 0,
        "accepted_chain_count": 0,
        "rejected_chain_count": 0,
        "high_motion_joint_error_count": 0,
        "limb_crop_candidate_count": 0,
        "coordinate_space_reject_count": 0,
        "motion_blur_frame_count": 0,
        "temporal_supersample_usage_ratio": 0.0,
        "temporal_support_chain_use_count": 0,
        "rtmw_oom_retry_count": 0,
        "rtmw_executed_batch_sizes": [],
        "temporal_support": {},
        "backend": "RTMW-primary-limb-context-multiscale",
        "expert_pose_used": False,
    }
    if not config.high_motion.enabled or not records:
        return summary

    points = [np.asarray(record["raw_points"], dtype=np.float32) for record in records]
    scores = [np.asarray(record["raw_scores"], dtype=np.float32) for record in records]
    timestamps = [float(record["source_timestamp_seconds"]) for record in records]
    high_motion_indexes = {
        index for index, record in enumerate(records)
        if str(record["motion_v6"]["state"]) in {
            MotionState.FAST_MOTION.value,
            MotionState.EXTREME_MOTION.value,
        }
    }
    specialist_indexes = high_motion_indexes | critical_frame_indexes
    summary["high_motion_frame_count"] = len(high_motion_indexes)
    summary["specialist_frame_count"] = len(specialist_indexes)
    if not specialist_indexes:
        return summary

    eligible_intervals = {
        index for index in range(max(0, len(records) - 1))
        if index in specialist_indexes or index + 1 in specialist_indexes
    }
    try:
        supersampling = HighMotionTemporalSupersampling(
            config.high_motion.temporal_supersampling_factor,
        ).generate(
            points,
            scores,
            timestamps,
            eligible_intervals=eligible_intervals,
        )
        summary["temporal_support"] = supersampling.to_dict()
        summary["temporal_supersample_usage_ratio"] = round(
            len(specialist_indexes) / len(records), 6,
        ) if supersampling.support_sample_count else 0.0
    except ValueError as error:
        supersampling = None
        summary["temporal_support"] = {
            "available": False,
            "reason": type(error).__name__,
            "support_is_measurement": False,
        }

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        summary["available"] = False
        summary["reason"] = "VIDEO_OPEN_FAILED"
        return summary
    try:
        for frame_index in sorted(specialist_indexes):
            record = records[frame_index]
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(record["source_frame_index"]))
            success, frame = capture.read()
            if not success or frame is None or frame.size == 0:
                continue
            blur = estimate_motion_blur(frame, record.get("render_bbox_array"))
            error_causes = record.setdefault("high_motion_error_causes_v66", [])
            if blur.strongly_blurred:
                error_causes.append("MOTION_BLUR")
            summary["motion_blur_frame_count"] = int(
                summary["motion_blur_frame_count"]
            ) + int(blur.strongly_blurred)
            predicted = bidirectional_native_prediction(
                points, scores, timestamps, frame_index,
            )
            predicted_points = predicted[0] if predicted is not None else None
            previous_points = points[frame_index - 1] if frame_index > 0 else None
            body_scale = max(float(record["pose_graph"].body_scale), 1.0)
            is_extreme = str(record["motion_v6"]["state"]) == MotionState.EXTREME_MOTION.value
            affected_chains = _affected_high_motion_chains(
                records,
                frame_index,
                body_scale=body_scale,
                minimum_score=settings.body_presence_threshold,
                force_all=(frame_index in critical_frame_indexes or is_extreme or blur.strongly_blurred),
            )
            if not affected_chains:
                continue
            all_crops = []
            for chain_name in affected_chains:
                support_velocity = (
                    supersampling.motion_vector_at_native(
                        frame_index, CORE_LIMB_CHAINS[chain_name],
                    )
                    if supersampling is not None else None
                )
                if support_velocity is not None:
                    summary["temporal_support_chain_use_count"] = int(
                        summary["temporal_support_chain_use_count"]
                    ) + 1
                all_crops.extend(build_limb_crops(
                    chain_name,
                    record["raw_points"],
                    record["raw_scores"],
                    previous_points=previous_points,
                    body_scale=body_scale,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    scales=config.high_motion.limb_crop_scales,
                    support_velocity=support_velocity,
                ))
            if not all_crops:
                continue
            summary["attempted_chain_count"] = int(
                summary["attempted_chain_count"]
            ) + len(affected_chains)
            candidate_points, candidate_scores = model.infer_on_bboxes(
                frame,
                [crop.bbox_xyxy for crop in all_crops],
                timing_key="pose_high_motion",
                maximum_batch_size=config.high_motion.maximum_rtmw_batch_size,
            )
            batch_diagnostics = model.last_batch_diagnostics.get(
                "pose_high_motion", {}
            )
            summary["rtmw_batch_diagnostics"] = batch_diagnostics
            summary["rtmw_oom_retry_count"] = int(
                summary["rtmw_oom_retry_count"]
            ) + int(batch_diagnostics.get("oom_retry_count", 0))
            executed_sizes = summary["rtmw_executed_batch_sizes"]
            if isinstance(executed_sizes, list):
                executed_sizes.extend(batch_diagnostics.get("executed_batch_sizes", []))
            candidate_count = min(len(candidate_points), len(candidate_scores), len(all_crops))
            summary["limb_crop_candidate_count"] = int(
                summary["limb_crop_candidate_count"]
            ) + candidate_count
            accepted_in_frame: set[str] = set()
            for chain_name in affected_chains:
                chain_indexes = tuple(
                    index for index in range(len(all_crops))
                    if all_crops[index].chain_name == chain_name and index < candidate_count
                )
                expected = _record_expected_chain_lengths(record, chain_name, body_scale)
                baseline_valid, _, baseline_quality = validate_chain_candidate(
                    chain_name,
                    record["raw_points"],
                    record["raw_scores"],
                    expected_lengths=expected,
                    predicted_points=predicted_points,
                    previous_points=previous_points,
                    body_scale=body_scale,
                    fast_motion=True,
                    minimum_score=0.01,
                )
                best: tuple[float, np.ndarray, np.ndarray, dict[str, object]] | None = None
                for candidate_index in chain_indexes:
                    chain = CORE_LIMB_CHAINS[chain_name]
                    full_chain = (
                        (5, 7, 9)
                        if chain_name == "left_arm"
                        else (6, 8, 10)
                        if chain_name == "right_arm"
                        else (11, 13, 15, 17, 18, 19)
                        if chain_name == "left_leg"
                        else (12, 14, 16, 20, 21, 22)
                    )
                    filtered_scores = np.zeros_like(candidate_scores[candidate_index], dtype=np.float32)
                    filtered_points = np.zeros_like(candidate_points[candidate_index], dtype=np.float32)
                    for joint in full_chain:
                        if joint < len(filtered_scores):
                            filtered_scores[joint] = candidate_scores[candidate_index, joint]
                            filtered_points[joint] = candidate_points[candidate_index, joint]
                    try:
                        packet = original_pixel_candidate(
                            filtered_points,
                            filtered_scores,
                            source=f"high-motion-{chain_name}",
                            frame_width=frame_width,
                            frame_height=frame_height,
                        )
                    except CoordinateSpaceError:
                        summary["coordinate_space_reject_count"] = int(
                            summary["coordinate_space_reject_count"]
                        ) + 1
                        error_causes.append("COORDINATE_SPACE_MISMATCH")
                        continue
                    adjusted_points = packet.points.copy()
                    root = chain[0]
                    if (
                        float(record["raw_scores"][root]) > 0.0
                        and float(packet.scores[root]) > 0.0
                    ):
                        root_offset = record["raw_points"][root] - packet.points[root]
                        if float(np.linalg.norm(root_offset)) > body_scale * 0.18:
                            continue
                        adjusted_points[list(full_chain)] += root_offset
                    valid, decisions, candidate_quality = validate_chain_candidate(
                        chain_name,
                        adjusted_points,
                        packet.scores,
                        expected_lengths=expected,
                        predicted_points=predicted_points,
                        previous_points=previous_points,
                        body_scale=body_scale,
                        fast_motion=True,
                    )
                    if not valid:
                        summary["high_motion_joint_error_count"] = int(
                            summary["high_motion_joint_error_count"]
                        ) + sum(not decision.accepted for decision in decisions)
                        error_causes.extend(
                            decision.reason
                            for decision in decisions
                            if decision.reason is not None
                        )
                        continue
                    support_agreement = _chain_support_agreement(
                        adjusted_points,
                        predicted_points,
                        chain,
                        body_scale,
                    )
                    evidence_quality = max(
                        config.high_motion.minimum_image_evidence_quality,
                        blur.image_evidence_quality,
                    )
                    trust = candidate_quality * (0.62 + 0.38 * evidence_quality) * support_agreement
                    diagnostics = {
                        "crop_scale": all_crops[candidate_index].scale,
                        "candidate_quality": round(candidate_quality, 6),
                        "image_evidence_quality": round(blur.image_evidence_quality, 6),
                        "support_agreement": round(support_agreement, 6),
                        "trust": round(trust, 6),
                        "coordinate_space": "ORIGINAL_PIXELS",
                        "conversion_count": packet.conversion_count,
                    }
                    if best is None or trust > best[0]:
                        best = trust, adjusted_points, packet.scores, diagnostics
                if best is None:
                    error_causes.append(f"{chain_name}:LIMB_CROP_DISAGREEMENT")
                    continue
                required_gain = config.iterative.minimum_quality_gain
                should_accept = (
                    not baseline_valid
                    or best[0] >= baseline_quality + required_gain
                    or (
                        blur.strongly_blurred
                        and best[0] >= baseline_quality - 0.02
                        and float(best[3]["support_agreement"]) >= 0.72
                    )
                )
                if not should_accept:
                    error_causes.append(f"{chain_name}:LIMB_CROP_DISAGREEMENT")
                    continue
                _, selected_points, selected_scores, candidate_diagnostics = best
                chain = CORE_LIMB_CHAINS[chain_name]
                full_chain = (
                    chain
                    if "arm" in chain_name
                    else (11, 13, 15, 17, 18, 19)
                    if chain_name == "left_leg"
                    else (12, 14, 16, 20, 21, 22)
                )
                accepted_joint_indexes: set[int] = set()
                for joint in full_chain:
                    if joint >= len(selected_scores) or selected_scores[joint] <= 0.0:
                        continue
                    if joint == chain[0] and record["raw_scores"][joint] > 0.0:
                        continue
                    record["raw_points"][joint] = selected_points[joint]
                    record["raw_scores"][joint] = min(
                        1.0,
                        float(selected_scores[joint])
                        * (0.70 + 0.30 * blur.image_evidence_quality),
                    )
                    accepted_joint_indexes.add(joint)
                if not accepted_joint_indexes:
                    continue
                record["refined_measurement"] = True
                record["refined_joint_indexes"] = frozenset({
                    *record["refined_joint_indexes"], *accepted_joint_indexes,
                })
                accepted_in_frame.add(chain_name)
                record.setdefault("high_motion_recovery_v66", {})[chain_name] = {
                    "accepted": True,
                    "source": "HIGH_MOTION_LIMB_CROP_CONSENSUS",
                    "selected_pass": 4,
                    "accepted_joint_indexes": sorted(accepted_joint_indexes),
                    **candidate_diagnostics,
                }
            accepted_count = len(accepted_in_frame)
            summary["accepted_chain_count"] = int(
                summary["accepted_chain_count"]
            ) + accepted_count
            summary["rejected_chain_count"] = int(
                summary["rejected_chain_count"]
            ) + max(0, len(affected_chains) - accepted_count)
    except (cv2.error, RuntimeError, ValueError, TypeError, IndexError) as error:
        logger.warning(
            "Pose V6.6 high-motion recovery degraded: %s", type(error).__name__,
        )
        summary["degraded"] = True
        summary["degraded_reason"] = type(error).__name__
    finally:
        capture.release()
    attempts = int(summary["attempted_chain_count"])
    summary["high_motion_repair_count"] = int(summary["accepted_chain_count"])
    summary["high_motion_repair_success_ratio"] = round(
        int(summary["accepted_chain_count"]) / attempts, 6,
    ) if attempts else 0.0
    return summary


def _affected_high_motion_chains(
    records: list[dict[str, Any]],
    frame_index: int,
    *,
    body_scale: float,
    minimum_score: float,
    force_all: bool,
) -> tuple[str, ...]:
    if force_all:
        return tuple(CORE_LIMB_CHAINS)
    record = records[frame_index]
    previous = records[frame_index - 1] if frame_index > 0 else None
    selected: list[str] = []
    for name, chain in CORE_LIMB_CHAINS.items():
        weak = any(float(record["raw_scores"][joint]) < minimum_score for joint in chain)
        displacement = 0.0
        if previous is not None:
            valid = [
                joint for joint in chain
                if float(record["raw_scores"][joint]) > 0.0
                and float(previous["raw_scores"][joint]) > 0.0
            ]
            displacement = max((
                float(np.linalg.norm(
                    record["raw_points"][joint] - previous["raw_points"][joint]
                )) / body_scale
                for joint in valid
            ), default=0.0)
        jerk_outlier = _chain_has_isolated_jerk(
            records, frame_index, chain, body_scale=body_scale,
        )
        if weak or displacement >= 0.035 or jerk_outlier:
            selected.append(name)
            causes = record.setdefault("high_motion_error_causes_v66", [])
            if weak:
                causes.append(f"{name}:LOW_CHAIN_QUALITY")
            if displacement >= 0.035:
                causes.append(f"{name}:LARGE_DISPLACEMENT")
            if jerk_outlier:
                causes.append(f"{name}:ISOLATED_JERK")
    return tuple(selected)


def _chain_has_isolated_jerk(
    records: list[dict[str, Any]],
    frame_index: int,
    chain: tuple[int, int, int],
    *,
    body_scale: float,
) -> bool:
    """Flag an isolated direction/acceleration discontinuity, not raw speed."""

    start = max(0, frame_index - 2)
    end = min(len(records), frame_index + 3)
    if end - start < 4 or body_scale <= 1.0:
        return False
    timestamps = [
        float(records[index]["source_timestamp_seconds"])
        for index in range(start, end)
    ]
    deltas = np.diff(np.asarray(timestamps, dtype=np.float64))
    if not np.isfinite(deltas).all() or np.any(deltas <= 0.0):
        return False
    characteristic_dt = float(np.median(deltas))
    local_index = frame_index - start
    for joint in chain[1:]:
        if any(
            float(records[index]["raw_scores"][joint]) <= 0.0
            or not np.isfinite(records[index]["raw_points"][joint]).all()
            for index in range(start, end)
        ):
            continue
        kinematics = compute_joint_kinematics(
            [records[index]["raw_points"][joint] for index in range(start, end)],
            timestamps,
        )
        impulse = (
            kinematics[local_index].jerk_magnitude
            * characteristic_dt ** 3
            / body_scale
        )
        if math.isfinite(impulse) and impulse >= 0.10:
            return True
    return False


def _record_expected_chain_lengths(
    record: dict[str, Any],
    chain_name: str,
    body_scale: float,
) -> tuple[float, float]:
    learned: dict[str, float | None] = {}
    for name, bone in record["pose_graph"].bones.items():
        learned[name] = (
            float(bone.reference_length) * body_scale
            if bone.reference_length is not None else None
        )
    return expected_chain_lengths(chain_name, body_scale, learned)


def _chain_support_agreement(
    candidate: np.ndarray,
    support: np.ndarray | None,
    chain: tuple[int, int, int],
    body_scale: float,
) -> float:
    if support is None:
        return 0.78
    residuals = [
        float(np.linalg.norm(candidate[joint] - support[joint])) / body_scale
        for joint in chain[1:]
        if np.isfinite(support[joint]).all()
    ]
    if not residuals:
        return 0.78
    return float(np.clip(1.0 - np.median(residuals) / 0.32, 0.15, 1.0))


def process_pose_video(
    supabase: Client | None,
    settings: PoseWorkerSettings,
    model: StrictWholebodyModel,
    hand_engine: MediaPipeHandEngine,
    analysis: dict[str, Any],
    video_path: Path,
    job_directory: Path,
    active_segment: ActiveSegment,
    logger: logging.Logger,
) -> PoseProcessingResult:
    """
    Pose Pipeline V6.6 działa wieloprzebiegowo i rozdziela RAW, ANALYSIS oraz RENDER.

    Przebieg 1:
    - RTMW wyznacza ciało,
    - MediaPipe zbiera 21 punktów każdej dłoni,
    - zapisujemy surowe trajektorie bez generowania filmu.

    Przebieg 2:
    - odrzucamy anatomicznie i czasowo nienaturalne dłonie,
    - interpolujemy najwyżej pojedyncze bezpieczne braki,
    - wygładzamy trajektorie w przód i wstecz,
    - dopiero wtedy generujemy film wynikowy.
    """

    processing_started_at = time.perf_counter()
    analysis_id = str(analysis["id"])
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("OpenCV nie może otworzyć filmu źródłowego.")

    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Film ma nieprawidłowe parametry techniczne.")
    timeline = probe_native_frame_timeline(
        video_path,
        fallback_fps=fps,
        expected_frame_count=max(
            source_frame_count,
            int(analysis.get("source_frame_count") or 0),
            active_segment.end_frame + 1,
        ),
    )
    logger.info(
        "Pose V6.6 timeline: source=%s fallback=%s gaps=%s frames=%s",
        timeline.source,
        timeline.fallback_used,
        timeline.frame_gap_count,
        len(timeline.timestamps),
    )

    raw_output_video_path = job_directory / "pose-overlay-raw.mp4"
    output_video_path = job_directory / "pose-overlay.mp4"
    output_json_path = job_directory / "pose-keypoints.json"
    diagnostics_path = job_directory / "pose-diagnostics.json"
    thumbnail_path = job_directory / "pose-thumbnail.jpg"

    pose_v6_config = load_pose_v6_config()
    tracker = PersonTrackingStateMachine(
        # V6 derives continuity windows from seconds and the real video FPS.
        TrackingConfig(
            keypoint_threshold=settings.body_presence_threshold,
            reacquire_confirm_frames=frames_for_seconds(0.10, fps, minimum=2),
            lost_after_missing_frames=frames_for_seconds(
                pose_v6_config.temporal.hard_lost_seconds,
                fps,
            ),
            maximum_center_jump_ratio=settings.track_max_center_jump_ratio,
            edge_margin_ratio=settings.body_edge_margin_ratio,
        )
    )
    pose_graph = BiomechanicalPoseGraph(
        PoseGraphConfig(
            body_validation=BodyValidationConfig(
                keypoint_threshold=settings.keypoint_threshold,
                edge_margin_ratio=settings.body_edge_margin_ratio,
                maximum_joint_velocity_bbox_ratio=(
                    settings.body_max_joint_velocity_bbox_ratio
                ),
                maximum_joint_acceleration_bbox_ratio=(
                    settings.body_max_joint_acceleration_bbox_ratio
                ),
                bone_log_tolerance=settings.body_bone_log_tolerance,
            ),
            maximum_prediction_frames=frames_for_seconds(
                pose_v6_config.temporal.track_recovery_seconds,
                fps,
            ),
            maximum_scale_change_ratio=settings.body_scale_max_change_ratio,
        )
    )
    hand_graph_config = HandGraphConfig()
    hand_assignment_memory = HandAssignmentMemory()
    pose_v5_config = PoseV5Config(
        camera=CameraMotionConfig(enabled=settings.pose_v5_camera_motion_enabled),
        refinement=RefinementConfig(
            enabled=settings.pose_v5_refinement_enabled,
            maximum_refinement_ratio=(
                pose_v6_config.iterative.pass2_maximum_ratio
                if pose_v6_config.iterative.enabled
                else settings.pose_v5_max_refinement_ratio
            ),
            padding_seconds=(
                pose_v6_config.iterative.segment_padding_seconds
                if pose_v6_config.iterative.enabled
                else settings.pose_v5_segment_padding_seconds
            ),
            minimum_quality_gain=(
                pose_v6_config.iterative.minimum_quality_gain
                if pose_v6_config.iterative.enabled
                else settings.pose_v5_min_quality_gain
            ),
        ),
    )
    camera_motion_estimator = CameraMotionEstimator(pose_v5_config.camera)
    bbox_motion_estimator = BBoxMotionEstimator()
    motion_analyzer = MotionAnalyzer(pose_v6_config.motion)
    previous_motion = MotionObservation(
        MotionState.NORMAL_MOTION,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    scene_cut_count = 0

    body_records: list[dict[str, Any]] = []
    raw_hand_frames: dict[str, list[RawHandFrame]] = {
        "left": [],
        "right": [],
    }
    object_detection_frames: list[list[ObjectDetection]] = []
    hand_rois: dict[str, list[tuple[int, int, int, int] | None]] = {
        "left": [],
        "right": [],
    }
    hand_failure_count = 0
    hand_failure_types: dict[str, int] = {}
    validation_seconds = 0.0

    processed_frames = 0
    detected_frames = 0
    confidence_sum = 0.0
    confidence_count = 0
    previous_bbox: np.ndarray | None = None
    track_started = False

    capture.set(cv2.CAP_PROP_POS_FRAMES, active_segment.start_frame)

    try:
        for source_frame_index in range(
            active_segment.start_frame,
            active_segment.end_frame + 1,
        ):
            success, frame = capture.read()
            if not success or frame is None or frame.size == 0:
                raise RuntimeError(
                    f"Nie udało się odczytać klatki {source_frame_index}."
                )

            camera_motion = (
                camera_motion_estimator.update(
                    frame,
                    tuple(int(round(float(value))) for value in previous_bbox)
                    if previous_bbox is not None
                    else None,
                )
                if settings.pose_v5_camera_motion_enabled
                else None
            )
            if camera_motion is not None and camera_motion.scene_cut:
                tracker = PersonTrackingStateMachine(tracker.config)
                pose_graph = BiomechanicalPoseGraph(pose_graph.config)
                hand_assignment_memory = HandAssignmentMemory()
                previous_bbox = None
                bbox_motion_estimator.reset()
                motion_analyzer.reset()
                previous_motion = MotionObservation(
                    MotionState.NORMAL_MOTION,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                )
                scene_cut_count += 1

            inference_started_at = time.perf_counter()
            source_timestamp = timeline.timestamp(source_frame_index, fps)
            keypoints_array, scores_array = model(frame)
            selection_bbox = (
                previous_bbox
                if tracker.state != TrackingState.LOST
                else None
            )
            candidate = select_primary_person(
                keypoints_array,
                scores_array,
                width,
                height,
                settings,
                selection_bbox,
                (
                    settings.body_presence_threshold * 0.90
                    if tracker.state
                    in {
                        TrackingState.TRACKED,
                        TrackingState.PARTIAL,
                        TrackingState.OCCLUDED,
                    }
                    else None
                ),
            )
            yolox_candidate_detected = candidate is not None
            bbox_source = (
                BBoxSource.YOLOX_MEASURED
                if yolox_candidate_detected
                else BBoxSource.MISSING
            )
            predicted_bbox = None
            recovery_attempted = False
            camera_translation = (
                (
                    float(camera_motion.translation_x),
                    float(camera_motion.translation_y),
                )
                if camera_motion is not None
                else (0.0, 0.0)
            )
            if candidate is not None:
                bbox_motion_estimator.observe(
                    candidate.bbox,
                    source_timestamp,
                    camera_translation=camera_translation,
                )
            else:
                roi_multiplier = (
                    1.16
                    if previous_motion.state == MotionState.EXTREME_MOTION
                    else 1.08
                    if previous_motion.state == MotionState.FAST_MOTION
                    else 1.0
                )
                predicted_bbox = bbox_motion_estimator.predict(
                    source_timestamp,
                    frame_width=width,
                    frame_height=height,
                    roi_scale=pose_v6_config.recovery_roi_scale * roi_multiplier,
                    camera_translation=camera_translation,
                )
                if recovery_allowed(
                    predicted_bbox,
                    tracking_state=tracker.state.value,
                    scene_cut=bool(camera_motion is not None and camera_motion.scene_cut),
                    maximum_age_seconds=pose_v6_config.temporal.track_recovery_seconds,
                ) and predicted_bbox is not None:
                    recovery_attempted = True
                    recovery_keypoints, recovery_scores = model.infer_on_bboxes(
                        frame,
                        [predicted_bbox.bbox_xyxy],
                        timing_key="pose_recovery",
                    )
                    candidate = select_primary_person(
                        recovery_keypoints,
                        recovery_scores,
                        width,
                        height,
                        settings,
                        predicted_bbox.bbox_xyxy,
                        settings.body_presence_threshold * 0.86,
                    )
                    if candidate is not None:
                        bbox_source = BBoxSource.TRACK_PREDICTED
            object_detection_frames.append(list(model.last_object_detections))

            raw_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
            raw_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
            candidate_detected = candidate is not None

            if candidate is not None:
                usable_point_count = min(KEYPOINT_COUNT, candidate.keypoints.shape[0])
                usable_score_count = min(KEYPOINT_COUNT, candidate.scores.shape[0])
                raw_points[:usable_point_count] = candidate.keypoints[:usable_point_count]
                raw_scores[:usable_score_count] = candidate.scores[:usable_score_count]

            prevalidation_image_quality = analyze_image_quality_v2(
                frame,
                body_roi=(
                    tuple(int(round(float(value))) for value in candidate.bbox)
                    if candidate is not None
                    else None
                ),
                left_hand_roi=None,
                right_hand_roi=None,
            )
            motion_blur_v66 = estimate_motion_blur(
                frame,
                candidate.bbox if candidate is not None else previous_bbox,
            )

            current_motion = (
                motion_analyzer.update(
                    raw_points,
                    raw_scores,
                    candidate.bbox,
                    source_timestamp,
                    camera_translation=camera_translation,
                )
                if candidate is not None
                else previous_motion
            )
            previous_motion = current_motion
            if (
                tracker.state != TrackingState.LOST
                and (
                    prevalidation_image_quality.global_quality.motion_blur
                    or prevalidation_image_quality.body_quality.motion_blur
                    or motion_blur_v66.strongly_blurred
                )
            ):
                current_motion = MotionObservation(
                    current_motion.state,
                    current_motion.median_joint_speed_scale_per_second,
                    current_motion.endpoint_speed_scale_per_second,
                    current_motion.bbox_speed_scale_per_second,
                    min(2.30, current_motion.gate_multiplier * 1.18),
                )
                previous_motion = current_motion

            tracking = tracker.update(
                detected=candidate_detected,
                bbox=candidate.bbox if candidate is not None else None,
                points=raw_points,
                scores=raw_scores,
                frame_width=width,
                frame_height=height,
                candidate_quality=(candidate.selection_score if candidate is not None else 0.0),
                motion_gate_multiplier=current_motion.gate_multiplier,
            )
            if tracker.last_bbox is not None:
                previous_bbox = tracker.last_bbox.copy()
            validation_started_at = time.perf_counter()
            graph_frame = pose_graph.update(
                raw_points=raw_points,
                raw_scores=raw_scores,
                bbox=candidate.bbox if candidate is not None else None,
                tracking=tracking,
                frame_width=width,
                frame_height=height,
                timestamp_seconds=source_timestamp,
                relative_depth=None,
                motion_gate_multiplier=current_motion.gate_multiplier,
            )
            validation_seconds += time.perf_counter() - validation_started_at
            validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
            validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
            body_count = min(BODY_POINT_COUNT, graph_frame.analysis_points.shape[0])
            validated_points[:body_count] = graph_frame.analysis_points[:body_count]
            validated_scores[:body_count] = graph_frame.analysis_scores[:body_count]

            # Preserve the optional RTMW face landmarks for backward
            # compatibility, but only inside an accepted track and only when
            # each coordinate independently passes confidence/bounds checks.
            if tracking.accept_pose:
                for point_index in range(23, min(91, KEYPOINT_COUNT)):
                    if (
                        raw_scores[point_index] >= settings.keypoint_threshold
                        and np.isfinite(raw_points[point_index]).all()
                        and 0.0 <= raw_points[point_index, 0] < width
                        and 0.0 <= raw_points[point_index, 1] < height
                    ):
                        validated_points[point_index] = raw_points[point_index]
                        validated_scores[point_index] = raw_scores[point_index]

            if tracking.accept_pose and candidate is not None:
                track_started = True
                detected_frames += 1
                valid_body_scores = raw_scores[:BODY_POINT_COUNT][
                    raw_scores[:BODY_POINT_COUNT] >= settings.body_presence_threshold
                ]
                if valid_body_scores.size > 0:
                    confidence_sum += float(valid_body_scores.sum())
                    confidence_count += int(valid_body_scores.size)

                timestamp_ms = int(round(source_timestamp * 1000.0))
                predicted_rois = predict_hand_rois(
                    validated_points,
                    validated_scores,
                    body_threshold=0.01,
                    frame_width=width,
                    frame_height=height,
                    timestamp_seconds=source_timestamp,
                    memory=hand_assignment_memory,
                    config=hand_graph_config,
                )
                combined_hand_roi = (
                    union_hand_roi(
                        predicted_rois,
                        frame_width=width,
                        frame_height=height,
                    )
                    if settings.hand_use_adaptive_roi
                    else None
                )
                hand_started_at = time.perf_counter()
                try:
                    hand_candidates = (
                        hand_engine.detect(frame, timestamp_ms, combined_hand_roi)
                        if settings.draw_hands
                        else []
                    )
                    hand_error = None
                except Exception as error:  # hand failure is isolated from body inference
                    # A hand subsystem failure must not invalidate body pose.
                    hand_candidates = []
                    hand_error = type(error).__name__
                    hand_failure_count += 1
                    hand_failure_types[hand_error] = (
                        hand_failure_types.get(hand_error, 0) + 1
                    )
                hand_seconds = time.perf_counter() - hand_started_at
                assignments = assign_hands_to_body_v2(
                    candidates=hand_candidates,
                    body_points=validated_points,
                    body_scores=validated_scores,
                    body_threshold=0.01,
                    config=hand_engine.config,
                    graph_config=hand_graph_config,
                    timestamp_seconds=source_timestamp,
                    memory=hand_assignment_memory,
                )
            else:
                hand_seconds = 0.0
                hand_error = None
                predicted_rois = {}
                combined_hand_roi = None
                assignments = {
                    "left": RawHandFrame(
                        observation=None,
                        timestamp_seconds=source_timestamp,
                        detector_found=False,
                        assignment_reasons=[tracking.state.value.lower()],
                    ),
                    "right": RawHandFrame(
                        observation=None,
                        timestamp_seconds=source_timestamp,
                        detector_found=False,
                        assignment_reasons=[tracking.state.value.lower()],
                    ),
                }

            raw_hand_frames["left"].append(assignments["left"])
            raw_hand_frames["right"].append(assignments["right"])
            hand_rois["left"].append(predicted_rois.get("left"))
            hand_rois["right"].append(predicted_rois.get("right"))

            body_records.append(
                {
                    "source_frame_index": source_frame_index,
                    "output_frame_index": processed_frames,
                    "analysis_frame_index": processed_frames,
                    "source_timestamp_seconds": source_timestamp,
                    "output_timestamp_seconds": processed_frames / fps,
                    "detected": tracking.accept_pose,
                    "raw_person_detected": yolox_candidate_detected,
                    "bbox_source": bbox_source.value,
                    "motion_v6": current_motion.to_dict(),
                    "refined_measurement": False,
                    "refined_joint_indexes": frozenset(),
                    "recovery_attempted": recovery_attempted,
                    "track_started": track_started,
                    "track_ended": tracking.state == TrackingState.LOST,
                    "tracking_state": tracking.state.value,
                    "tracking_reasons": list(tracking.reasons),
                    "tracking_identity_score": tracking.identity_score,
                    "tracking_decision": tracking,
                    "selection_score": (
                        float(candidate.selection_score)
                        if candidate is not None
                        else 0.0
                    ),
                    "body_keypoint_count": (
                        int(candidate.body_keypoint_count)
                        if candidate is not None
                        else 0
                    ),
                    "bbox_xyxy": (
                        [round(float(value), 2) for value in candidate.bbox]
                        if candidate is not None
                        else None
                    ),
                    "bbox_array": candidate.bbox.copy() if candidate is not None else None,
                    "render_bbox_array": (
                        candidate.bbox.copy()
                        if candidate is not None
                        else predicted_bbox.bbox_xyxy.copy()
                        if predicted_bbox is not None
                        else None
                    ),
                    "image_quality_v2": analyze_image_quality_v2(
                        frame,
                        body_roi=(
                            tuple(int(round(float(value))) for value in candidate.bbox)
                            if candidate is not None
                            else None
                        ),
                        left_hand_roi=predicted_rois.get("left"),
                        right_hand_roi=predicted_rois.get("right"),
                    ),
                    "prevalidation_motion_blur": bool(
                        prevalidation_image_quality.global_quality.motion_blur
                        or prevalidation_image_quality.body_quality.motion_blur
                        or motion_blur_v66.strongly_blurred
                    ),
                    "motion_blur_v66": motion_blur_v66.to_dict(),
                    "camera_motion": camera_motion,
                    "pose_graph": graph_frame,
                    "hand_union_roi": combined_hand_roi,
                    "inference_seconds": time.perf_counter() - inference_started_at,
                    "timing_seconds": {
                        "detector": model.last_timing_seconds.get("detector", 0.0),
                        "pose": model.last_timing_seconds.get("pose", 0.0),
                        "pose_recovery": model.last_timing_seconds.get(
                            "pose_recovery", 0.0
                        ),
                        "hands": hand_seconds,
                    },
                    "hand_error": hand_error,
                    "raw_points": raw_points.copy(),
                    "raw_scores": raw_scores.copy(),
                    "smoothed_points": validated_points.copy(),
                    "smoothed_scores": validated_scores.copy(),
                }
            )

            processed_frames += 1
            if (
                processed_frames
                % settings.progress_update_interval_frames
                == 0
            ):
                frame_ratio = processed_frames / max(
                    1,
                    active_segment.frame_count,
                )
                progress = 30 + int(min(1.0, frame_ratio) * 40)
                maybe_update_progress(
                    supabase,
                    analysis_id,
                    settings.worker_id,
                    min(progress, 70),
                    "pose-v6-collecting-body-and-hands",
                )
    finally:
        capture.release()

    refinement_results: list[RefinementResult] = []
    hand_rescue_summary = run_hand_rescue_pass(
        settings,
        video_path,
        body_records,
        raw_hand_frames,
        hand_rois,
        frame_width=width,
        frame_height=height,
        logger=logger,
    )
    pass1_seconds = time.perf_counter() - processing_started_at
    scene_cut_flags = [
        bool(record["camera_motion"] is not None and record["camera_motion"].scene_cut)
        for record in body_records
    ]

    def audit_current_pose(
        grip_states: dict[str, list[str]] | None = None,
    ) -> Any:
        model_disagreements: dict[int, list[int]] = {}
        for frame_index, record in enumerate(body_records):
            for field, key in (
                ("refinement_fusion", "rejected_disagreement_indexes"),
                ("pass3_fusion", "model_disagreement_joint_indexes"),
            ):
                diagnostic = record.get(field)
                if isinstance(diagnostic, dict) and diagnostic.get(key):
                    model_disagreements.setdefault(frame_index, []).extend(
                        int(value) for value in diagnostic[key]
                    )
        return audit_pose_sequence(
            [record["raw_points"] for record in body_records],
            [record["raw_scores"] for record in body_records],
            [float(record["pose_graph"].body_scale) for record in body_records],
            [float(record["source_timestamp_seconds"]) for record in body_records],
            [str(record["tracking_state"]) for record in body_records],
            [str(record["motion_v6"]["state"]) for record in body_records],
            scene_cut_flags,
            config=pose_v6_config.iterative,
            hand_visible={
                side: [frame.observation is not None for frame in raw_hand_frames[side]]
                for side in ("left", "right")
            },
            hand_quality_values={
                side: [
                    max(0.0, min(1.0, 1.0 - frame.observation.assignment_score))
                    if frame.observation is not None else 0.0
                    for frame in raw_hand_frames[side]
                ]
                for side in ("left", "right")
            },
            grip_states=grip_states,
            motion_blur=[bool(record["prevalidation_motion_blur"]) for record in body_records],
            model_disagreements=model_disagreements,
            body_joint_count=BODY_POINT_COUNT,
        )

    pass1_audit = audit_current_pose()
    pass2_audit = pass1_audit
    pass3_audit = pass1_audit
    pass1_snapshots = [
        (record["raw_points"].copy(), record["raw_scores"].copy())
        for record in body_records
    ]
    pass1_bbox_snapshots = [
        record["bbox_array"].copy()
        if isinstance(record.get("bbox_array"), np.ndarray) else None
        for record in body_records
    ]
    pass1_hand_snapshots = {
        side: list(raw_hand_frames[side]) for side in ("left", "right")
    }
    pass1_bbox_sources = [str(record["bbox_source"]) for record in body_records]
    pass2_seconds = 0.0
    pass3_seconds = 0.0
    expert_pass_seconds = 0.0
    pass2_rollback_count = 0
    pass3_rollback_count = 0
    frames_improved_by_pass2 = 0
    frames_improved_by_pass3 = 0
    pass3_results: list[dict[str, object]] = []
    pass2_started_at = time.perf_counter()
    if pose_v5_config.refinement.enabled and body_records:
        refinement_source = []
        for index, record in enumerate(body_records):
            raw_hands = (raw_hand_frames["left"][index], raw_hand_frames["right"][index])
            hand_qualities = [
                max(0.0, min(1.0, 1.0 - hand.observation.assignment_score))
                for hand in raw_hands
                if hand.observation is not None
            ]
            hand_assignment_failed = any(hand.detector_found and hand.observation is None for hand in raw_hands)
            critical_joint_indexes = (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
            weak_limb_joint_count = sum(
                float(record["raw_scores"][joint]) < settings.body_presence_threshold
                for joint in critical_joint_indexes
            )
            temporal_joint_discontinuity = False
            if 0 < index < len(body_records) - 1:
                previous_record = body_records[index - 1]
                following_record = body_records[index + 1]
                scale = max(float(record["pose_graph"].body_scale), 1.0)
                for joint in critical_joint_indexes:
                    if all(
                        float(candidate["raw_scores"][joint]) > 0.0
                        for candidate in (previous_record, record, following_record)
                    ):
                        expected = (
                            previous_record["raw_points"][joint]
                            + following_record["raw_points"][joint]
                        ) * 0.5
                        if float(np.linalg.norm(record["raw_points"][joint] - expected) / scale) > 0.18:
                            temporal_joint_discontinuity = True
                            break
            refinement_source.append({
                "timestamp_seconds": record["output_timestamp_seconds"],
                "quality": min(
                    float(record["pose_graph"].quality),
                    min(hand_qualities) if hand_qualities else 1.0,
                    0.70 if index in pass1_audit.angle_glitch_frames else 1.0,
                ),
                "tracking_state": record["tracking_state"],
                "camera_shake": bool(
                    record["camera_motion"] is not None
                    and record["camera_motion"].camera_shake
                ),
                "reasons": [
                    *[
                        error.code.value
                        for error in pass1_audit.frames[index].errors
                    ],
                    *(
                        ["METRIC_SPIKE"]
                        if index in pass1_audit.angle_glitch_frames else []
                    ),
                    *(
                        ["HAND_DROPOUT"]
                        if index in pass1_audit.grip_flicker_frames else []
                    ),
                    *list(record["tracking_reasons"]),
                    *(
                        ["PERSON_DETECTOR_MISS"]
                        if record["bbox_source"] == BBoxSource.TRACK_PREDICTED.value
                        else []
                    ),
                    *(
                        ["FAST_MOTION_DROPOUT"]
                        if pose_v6_config.refinement_fast_motion_enabled
                        and record["motion_v6"]["state"]
                        in {
                            MotionState.FAST_MOTION.value,
                            MotionState.EXTREME_MOTION.value,
                        }
                        and float(record["pose_graph"].quality) < 0.72
                        else []
                    ),
                    *(
                        ["MOTION_BLUR"]
                        if record["prevalidation_motion_blur"]
                        else []
                    ),
                    *(
                        ["BONE_OUTLIER", "BONE_REJECTION_BURST"]
                        if any(
                            not bone.valid
                            for bone in record["pose_graph"].bones.values()
                        )
                        else []
                    ),
                    *(
                        ["LIMB_DROPOUT"]
                        if weak_limb_joint_count >= 2
                        else []
                    ),
                    *(
                        ["TEMPORAL_DISCONTINUITY"]
                        if temporal_joint_discontinuity
                        else []
                    ),
                    *(
                        ["LOW_HAND_QUALITY", "HAND_DROPOUT"]
                        if record["hand_error"] or hand_assignment_failed
                        else []
                    ),
                ],
            })
        difficult_segments, _ = detect_difficult_segments(
            refinement_source,
            fps=fps,
            config=pose_v5_config.refinement,
        )
        refinement_capture = cv2.VideoCapture(str(video_path))
        refinement_hand_engine: MediaPipeHandEngine | None = None
        refinement_hand_memory = HandAssignmentMemory()
        try:
            refinement_hand_engine = MediaPipeHandEngine(create_hand_pipeline_config(settings))
        except (RuntimeError, OSError, ValueError) as error:
            logger.warning("Pose V6 hand refinement niedostępny dla %s: %s.", analysis_id, type(error).__name__)
        if refinement_capture.isOpened():
            try:
                def refine_body_frame(
                    frame_index: int,
                    before: dict[str, Any],
                ) -> dict[str, Any] | None:
                    record = body_records[frame_index]
                    refinement_capture.set(
                        cv2.CAP_PROP_POS_FRAMES,
                        int(record["source_frame_index"]),
                    )
                    success, refinement_frame = refinement_capture.read()
                    if not success or refinement_frame is None or refinement_frame.size == 0:
                        return None
                    refined_keypoints, refined_scores = model(refinement_frame)
                    previous = record.get("bbox_array")
                    refined_candidates: list[PoseCandidate] = []
                    detector_refined = select_primary_person(
                        refined_keypoints,
                        refined_scores,
                        width,
                        height,
                        settings,
                        previous if isinstance(previous, np.ndarray) else None,
                        settings.body_presence_threshold * 0.90,
                    )
                    if detector_refined is not None:
                        refined_candidates.append(detector_refined)
                    motion_box = record.get("render_bbox_array")
                    if isinstance(motion_box, np.ndarray):
                        center = (motion_box[:2] + motion_box[2:]) * 0.5
                        size = motion_box[2:] - motion_box[:2]
                        pass2_crops = [
                            np.concatenate(
                                (center - size * 0.5 * scale, center + size * 0.5 * scale)
                            ).astype(np.float32)
                            for scale in pose_v6_config.iterative.pass2_roi_scales
                        ]
                        recovery_points, recovery_scores = model.infer_on_bboxes(
                            refinement_frame,
                            pass2_crops,
                            timing_key="pose_recovery",
                        )
                        recovery_count = min(len(recovery_points), len(recovery_scores))
                        for crop_index in range(recovery_count):
                            recovery_candidate = select_primary_person(
                                recovery_points[crop_index:crop_index + 1],
                                recovery_scores[crop_index:crop_index + 1],
                                width,
                                height,
                                settings,
                                motion_box,
                                settings.body_presence_threshold * 0.86,
                            )
                            if recovery_candidate is not None:
                                refined_candidates.append(recovery_candidate)
                    if not refined_candidates:
                        return None
                    hypotheses = [
                        PoseHypothesis(
                            record["raw_points"], record["raw_scores"],
                            "pass1-primary", 1, 1.0,
                        )
                    ]
                    for candidate_index, refined_candidate in enumerate(refined_candidates):
                        candidate_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                        candidate_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                        point_count = min(KEYPOINT_COUNT, refined_candidate.keypoints.shape[0])
                        score_count = min(KEYPOINT_COUNT, refined_candidate.scores.shape[0])
                        candidate_points[:point_count] = refined_candidate.keypoints[:point_count]
                        candidate_scores[:score_count] = refined_candidate.scores[:score_count]
                        hypotheses.append(PoseHypothesis(
                            candidate_points,
                            candidate_scores,
                            f"pass2-multiscale-{candidate_index + 1}",
                            2,
                            0.90,
                        ))
                    consensus = fuse_pose_hypotheses(
                        hypotheses,
                        body_scale=float(record["pose_graph"].body_scale),
                        previous_points=(
                            body_records[frame_index - 1]["raw_points"]
                            if frame_index > 0 else None
                        ),
                        following_points=(
                            body_records[frame_index + 1]["raw_points"]
                            if frame_index + 1 < len(body_records) else None
                        ),
                        minimum_quality_gain=pose_v6_config.iterative.minimum_quality_gain,
                    )
                    raw_points = consensus.points
                    raw_scores = consensus.scores
                    refined = max(refined_candidates, key=lambda item: item.selection_score)
                    valid_scores = raw_scores[:BODY_POINT_COUNT][
                        raw_scores[:BODY_POINT_COUNT] >= settings.body_presence_threshold
                    ]
                    confidence_quality = (
                        float(np.mean(valid_scores)) if valid_scores.size else 0.0
                    )
                    quality = min(
                        float(refined.selection_score),
                        confidence_quality,
                    )
                    refined_hands: dict[str, RawHandFrame] | None = None
                    if refinement_hand_engine is not None:
                        candidates = refinement_hand_engine.detect(
                            refinement_frame,
                            int(round(float(record["source_timestamp_seconds"]) * 1000.0)),
                            record.get("hand_union_roi"),
                        )
                        refined_hands = assign_hands_to_body_v2(
                            candidates,
                            raw_points,
                            raw_scores,
                            settings.body_presence_threshold,
                            refinement_hand_engine.config,
                            hand_graph_config,
                            float(record["source_timestamp_seconds"]),
                            refinement_hand_memory,
                        )
                        hand_quality = [
                            max(0.0, min(1.0, 1.0 - hand.observation.assignment_score))
                            for hand in refined_hands.values()
                            if hand.observation is not None
                        ]
                        if hand_quality:
                            quality = min(quality, min(hand_quality))
                    return {
                        "quality": quality,
                        "biomechanical_valid": _refinement_body_is_valid(
                            raw_points,
                            raw_scores,
                            refined.bbox,
                            settings,
                        ),
                        "raw_points": raw_points,
                        "raw_scores": raw_scores,
                        "bbox": refined.bbox.copy(),
                        "raw_hands": refined_hands,
                        "iterative_fusion": {
                            "selected_joint_metadata": list(consensus.selected_joint_metadata),
                            "corrected_joint_indexes": sorted(consensus.corrected_joint_indexes),
                            "model_disagreement_joint_indexes": sorted(consensus.disagreement_joint_indexes),
                            "candidate_count": len(hypotheses),
                            "selected_pass": 2,
                        },
                    }

                for segment in difficult_segments:
                    refinement_results.extend(
                        refine_frames(
                            segment,
                            refinement_source,
                            refine_body_frame,
                            config=pose_v5_config.refinement,
                        )
                    )
            except (cv2.error, ValueError, TypeError, RuntimeError) as error:
                logger.warning(
                    "Pose V6 Pass 2 pominięty dla analizy %s; Pass 1 zachowany: %s.",
                    analysis_id,
                    type(error).__name__,
                )
                refinement_results = []
            finally:
                refinement_capture.release()
                if refinement_hand_engine is not None:
                    refinement_hand_engine.close()
        else:
            if refinement_hand_engine is not None:
                refinement_hand_engine.close()
            logger.warning(
                "Pose V6 Pass 2 nie otworzył filmu dla analizy %s; Pass 1 zachowany.",
                analysis_id,
            )

        accepted_refinements = [item for item in refinement_results if item.accepted]
        if accepted_refinements:
            for item in accepted_refinements:
                replacement = item.replacement
                if not isinstance(replacement, dict):
                    continue
                record = body_records[item.frame_index]
                iterative_fusion = replacement.get("iterative_fusion")
                corrected_indexes = frozenset(
                    int(value)
                    for value in (
                        iterative_fusion.get("corrected_joint_indexes", [])
                        if isinstance(iterative_fusion, dict) else []
                    )
                )
                record["raw_points"] = replacement["raw_points"].copy()
                record["raw_scores"] = replacement["raw_scores"].copy()
                record["refined_measurement"] = bool(corrected_indexes)
                record["refined_joint_indexes"] = corrected_indexes
                if corrected_indexes:
                    record["bbox_array"] = replacement["bbox"]
                    record["render_bbox_array"] = replacement["bbox"].copy()
                    record["bbox_xyxy"] = [
                        round(float(value), 2) for value in replacement["bbox"]
                    ]
                    record["bbox_source"] = BBoxSource.TEMPORAL_REFINED.value
                record["refinement_fusion"] = {
                    "accepted_joint_count": len(corrected_indexes),
                    "accepted_joint_indexes": sorted(corrected_indexes),
                    "rejected_disagreement_count": len(
                        iterative_fusion.get("model_disagreement_joint_indexes", [])
                        if isinstance(iterative_fusion, dict) else []
                    ),
                    "rejected_disagreement_indexes": (
                        iterative_fusion.get("model_disagreement_joint_indexes", [])
                        if isinstance(iterative_fusion, dict) else []
                    ),
                    "joint_diagnostics": (
                        iterative_fusion.get("selected_joint_metadata", [])
                        if isinstance(iterative_fusion, dict) else []
                    ),
                    "candidate_count": (
                        iterative_fusion.get("candidate_count", 1)
                        if isinstance(iterative_fusion, dict) else 1
                    ),
                    "fusion_policy": "multi-hypothesis-per-joint-consensus-v1",
                }
                refined_hands = replacement.get("raw_hands")
                if isinstance(refined_hands, dict):
                    for side in ("left", "right"):
                        if isinstance(refined_hands.get(side), RawHandFrame):
                            raw_hand_frames[side][item.frame_index] = refined_hands[side]

            # Replay the full temporal graph once so accepted observations are
            # validated in their original context before analysis smoothing.
            replay_graph = BiomechanicalPoseGraph(pose_graph.config)
            for record in body_records:
                replayed = replay_graph.update(
                    raw_points=record["raw_points"],
                    raw_scores=record["raw_scores"],
                    bbox=record["bbox_array"],
                    tracking=record["tracking_decision"],
                    frame_width=width,
                    frame_height=height,
                    timestamp_seconds=float(record["source_timestamp_seconds"]),
                    relative_depth=None,
                    motion_gate_multiplier=float(
                        record["motion_v6"].get("gate_multiplier", 1.0)
                    ),
                )
                record["pose_graph"] = replayed
                validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
                validated_points[:count] = replayed.analysis_points[:count]
                validated_scores[:count] = replayed.analysis_scores[:count]
                record["smoothed_points"] = validated_points
                record["smoothed_scores"] = validated_scores
            pose_graph = replay_graph

    pass2_seconds = time.perf_counter() - pass2_started_at
    pass2_audit = audit_current_pose()
    pass3_audit = pass2_audit
    rolled_back_pass2_indexes: list[int] = []
    for item in refinement_results:
        if not item.accepted or not 0 <= item.frame_index < len(body_records):
            continue
        decision = compare_iteration_quality(
            pass1_audit.frame_quality(item.frame_index),
            pass2_audit.frame_quality(item.frame_index),
            iteration=2,
            config=pose_v6_config.iterative,
        )
        if not decision.accepted:
            points_before, scores_before = pass1_snapshots[item.frame_index]
            body_records[item.frame_index]["raw_points"] = points_before.copy()
            body_records[item.frame_index]["raw_scores"] = scores_before.copy()
            body_records[item.frame_index]["refined_measurement"] = False
            body_records[item.frame_index]["refined_joint_indexes"] = frozenset()
            body_records[item.frame_index]["bbox_source"] = pass1_bbox_sources[item.frame_index]
            body_records[item.frame_index]["bbox_array"] = pass1_bbox_snapshots[item.frame_index]
            body_records[item.frame_index]["render_bbox_array"] = (
                pass1_bbox_snapshots[item.frame_index].copy()
                if isinstance(pass1_bbox_snapshots[item.frame_index], np.ndarray) else None
            )
            for side in ("left", "right"):
                raw_hand_frames[side][item.frame_index] = pass1_hand_snapshots[side][item.frame_index]
            body_records[item.frame_index]["refinement_fusion"]["pass2_regression"] = (
                decision.rolled_back
            )
            body_records[item.frame_index]["refinement_fusion"]["converged"] = (
                decision.converged
            )
            body_records[item.frame_index]["refinement_fusion"]["accepted_joint_count"] = 0
            body_records[item.frame_index]["refinement_fusion"]["accepted_joint_indexes"] = []
            rolled_back_pass2_indexes.append(item.frame_index)
        elif decision.accepted:
            frames_improved_by_pass2 += 1
    pass2_rollback_count = len(rolled_back_pass2_indexes)
    if rolled_back_pass2_indexes:
        replay_graph = BiomechanicalPoseGraph(pose_graph.config)
        for record in body_records:
            replayed = replay_graph.update(
                raw_points=record["raw_points"], raw_scores=record["raw_scores"],
                bbox=record["bbox_array"], tracking=record["tracking_decision"],
                frame_width=width, frame_height=height,
                timestamp_seconds=float(record["source_timestamp_seconds"]),
                relative_depth=None,
                motion_gate_multiplier=float(record["motion_v6"].get("gate_multiplier", 1.0)),
            )
            record["pose_graph"] = replayed
            validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
            validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
            count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
            validated_points[:count] = replayed.analysis_points[:count]
            validated_scores[:count] = replayed.analysis_scores[:count]
            record["smoothed_points"] = validated_points
            record["smoothed_scores"] = validated_scores
        pose_graph = replay_graph
        pass2_audit = audit_current_pose()
    if pass2_audit.quality_score < pass1_audit.quality_score:
        pass2_applied_indexes = [
            index for index, record in enumerate(body_records)
            if isinstance(record.get("refinement_fusion"), dict)
            and int(record["refinement_fusion"].get("accepted_joint_count", 0)) > 0
        ]
        for frame_index in pass2_applied_indexes:
            points_before, scores_before = pass1_snapshots[frame_index]
            record = body_records[frame_index]
            record["raw_points"] = points_before.copy()
            record["raw_scores"] = scores_before.copy()
            record["refined_measurement"] = False
            record["refined_joint_indexes"] = frozenset()
            record["bbox_source"] = pass1_bbox_sources[frame_index]
            record["bbox_array"] = pass1_bbox_snapshots[frame_index]
            record["render_bbox_array"] = (
                pass1_bbox_snapshots[frame_index].copy()
                if isinstance(pass1_bbox_snapshots[frame_index], np.ndarray) else None
            )
            record["refinement_fusion"]["global_pass_rollback"] = True
            record["refinement_fusion"]["accepted_joint_count"] = 0
            record["refinement_fusion"]["accepted_joint_indexes"] = []
            for side in ("left", "right"):
                raw_hand_frames[side][frame_index] = pass1_hand_snapshots[side][frame_index]
        if pass2_applied_indexes:
            pass2_rollback_count += len(pass2_applied_indexes)
            frames_improved_by_pass2 = 0
            replay_graph = BiomechanicalPoseGraph(pose_graph.config)
            for record in body_records:
                replayed = replay_graph.update(
                    raw_points=record["raw_points"], raw_scores=record["raw_scores"],
                    bbox=record["bbox_array"], tracking=record["tracking_decision"],
                    frame_width=width, frame_height=height,
                    timestamp_seconds=float(record["source_timestamp_seconds"]),
                    relative_depth=None,
                    motion_gate_multiplier=float(record["motion_v6"].get("gate_multiplier", 1.0)),
                )
                record["pose_graph"] = replayed
                validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
                validated_points[:count] = replayed.analysis_points[:count]
                validated_scores[:count] = replayed.analysis_scores[:count]
                record["smoothed_points"] = validated_points
                record["smoothed_scores"] = validated_scores
            pose_graph = replay_graph
            pass2_audit = audit_current_pose()
            pass3_audit = pass2_audit

    # Pass 3 spends the expensive multi-scale budget only on the worst 1-5%
    # left by the Pass 2 audit.  Candidate selection remains per joint and the
    # full pre/post temporal context participates in consensus.
    pass2_converged = abs(
        pass2_audit.quality_score - pass1_audit.quality_score
    ) < pose_v6_config.iterative.convergence_epsilon
    critical_segments = select_critical_segments(
        pass2_audit,
        maximum_ratio=pose_v6_config.iterative.pass3_critical_ratio,
    ) if pose_v6_config.iterative.enabled and not pass2_converged else []
    if critical_segments:
        pass3_started_at = time.perf_counter()
        pass2_snapshots = [
            (record["raw_points"].copy(), record["raw_scores"].copy())
            for record in body_records
        ]
        pass2_refined_indexes = [record["refined_joint_indexes"] for record in body_records]
        pass2_refined_measurements = [bool(record["refined_measurement"]) for record in body_records]
        pass2_bbox_sources = [str(record["bbox_source"]) for record in body_records]
        pass2_bbox_snapshots = [
            record["bbox_array"].copy()
            if isinstance(record.get("bbox_array"), np.ndarray) else None
            for record in body_records
        ]
        pass2_hand_snapshots = {
            side: list(raw_hand_frames[side]) for side in ("left", "right")
        }
        pass3_capture = cv2.VideoCapture(str(video_path))
        pass3_hand_memory = HandAssignmentMemory()
        try:
            if pass3_capture.isOpened():
                critical_indexes = sorted({
                    index
                    for segment in critical_segments
                    for index in range(segment.start_frame, segment.end_frame + 1)
                })
                for frame_index in critical_indexes:
                    record = body_records[frame_index]
                    if record["tracking_state"] in {TrackingState.LOST.value, TrackingState.REACQUIRING.value}:
                        continue
                    pass3_capture.set(cv2.CAP_PROP_POS_FRAMES, int(record["source_frame_index"]))
                    success, pass3_frame = pass3_capture.read()
                    if not success or pass3_frame is None or pass3_frame.size == 0:
                        continue
                    motion_box = record.get("render_bbox_array")
                    if not isinstance(motion_box, np.ndarray):
                        continue
                    center = (motion_box[:2] + motion_box[2:]) * 0.5
                    size = motion_box[2:] - motion_box[:2]
                    hypotheses = [PoseHypothesis(
                        record["raw_points"], record["raw_scores"],
                        "best-pass2-state", 2, 1.0,
                    )]
                    best_bbox = motion_box.copy()
                    best_selection = -math.inf
                    pass3_crops = [
                        np.concatenate((
                            center - size * 0.5 * scale,
                            center + size * 0.5 * scale,
                        )).astype(np.float32)
                        for scale in pose_v6_config.iterative.pass3_roi_scales
                    ]
                    candidate_points, candidate_scores = model.infer_on_bboxes(
                        pass3_frame, pass3_crops, timing_key="pose_recovery",
                    )
                    candidate_count = min(len(candidate_points), len(candidate_scores))
                    for candidate_index in range(candidate_count):
                        selected = select_primary_person(
                            candidate_points[candidate_index:candidate_index + 1],
                            candidate_scores[candidate_index:candidate_index + 1],
                            width, height,
                            settings, motion_box,
                            settings.body_presence_threshold * 0.84,
                        )
                        if selected is None:
                            continue
                        expanded_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                        expanded_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                        point_count = min(KEYPOINT_COUNT, selected.keypoints.shape[0])
                        score_count = min(KEYPOINT_COUNT, selected.scores.shape[0])
                        expanded_points[:point_count] = selected.keypoints[:point_count]
                        expanded_scores[:score_count] = selected.scores[:score_count]
                        hypotheses.append(PoseHypothesis(
                            expanded_points, expanded_scores,
                            f"pass3-deep-scale-{candidate_index + 1}", 3, 0.92,
                        ))
                        if selected.selection_score > best_selection:
                            best_selection = selected.selection_score
                            best_bbox = selected.bbox.copy()
                    if len(hypotheses) <= 1:
                        continue
                    consensus = fuse_pose_hypotheses(
                        hypotheses,
                        body_scale=float(record["pose_graph"].body_scale),
                        previous_points=(body_records[frame_index - 1]["raw_points"] if frame_index > 0 else None),
                        following_points=(body_records[frame_index + 1]["raw_points"] if frame_index + 1 < len(body_records) else None),
                        minimum_quality_gain=pose_v6_config.iterative.minimum_quality_gain,
                    )
                    if not consensus.corrected_joint_indexes or not _refinement_body_is_valid(
                        consensus.points, consensus.scores, best_bbox, settings,
                    ):
                        continue
                    record["raw_points"] = consensus.points
                    record["raw_scores"] = consensus.scores
                    record["refined_measurement"] = True
                    record["refined_joint_indexes"] = frozenset({
                        *record["refined_joint_indexes"], *consensus.corrected_joint_indexes,
                    })
                    record["bbox_array"] = best_bbox
                    record["render_bbox_array"] = best_bbox.copy()
                    record["bbox_source"] = BBoxSource.TEMPORAL_REFINED.value
                    record["pass3_fusion"] = {
                        "accepted_joint_indexes": sorted(consensus.corrected_joint_indexes),
                        "model_disagreement_joint_indexes": sorted(consensus.disagreement_joint_indexes),
                        "joint_diagnostics": list(consensus.selected_joint_metadata),
                        "candidate_count": len(hypotheses),
                    }
                    expanded_hand_rois = {
                        side: enlarge_roi(
                            hand_rois[side][frame_index],
                            frame_width=width,
                            frame_height=height,
                            scale=1.55,
                        )
                        for side in ("left", "right")
                    }
                    pass3_hand_roi = union_hand_roi(
                        expanded_hand_rois,
                        frame_width=width,
                        frame_height=height,
                    )
                    if pass3_hand_roi is not None:
                        pass3_hand_candidates = hand_engine.detect(
                            pass3_frame,
                            int(round(float(record["source_timestamp_seconds"]) * 1000.0)),
                            pass3_hand_roi,
                        )
                        pass3_assignments = assign_hands_to_body_v2(
                            pass3_hand_candidates,
                            consensus.points,
                            consensus.scores,
                            settings.body_presence_threshold,
                            hand_engine.config,
                            hand_graph_config,
                            float(record["source_timestamp_seconds"]),
                            pass3_hand_memory,
                        )
                        for side in ("left", "right"):
                            if pass3_assignments[side].observation is not None:
                                raw_hand_frames[side][frame_index] = pass3_assignments[side]
            replay_graph = BiomechanicalPoseGraph(pose_graph.config)
            for record in body_records:
                replayed = replay_graph.update(
                    raw_points=record["raw_points"], raw_scores=record["raw_scores"],
                    bbox=record["bbox_array"], tracking=record["tracking_decision"],
                    frame_width=width, frame_height=height,
                    timestamp_seconds=float(record["source_timestamp_seconds"]),
                    relative_depth=None,
                    motion_gate_multiplier=float(record["motion_v6"].get("gate_multiplier", 1.0)),
                )
                record["pose_graph"] = replayed
                validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
                validated_points[:count] = replayed.analysis_points[:count]
                validated_scores[:count] = replayed.analysis_scores[:count]
                record["smoothed_points"] = validated_points
                record["smoothed_scores"] = validated_scores
            pose_graph = replay_graph
            tentative_pass3_audit = audit_current_pose()
            pass3_indexes = [
                index for index, record in enumerate(body_records)
                if isinstance(record.get("pass3_fusion"), dict)
            ]
            for frame_index in pass3_indexes:
                decision = compare_iteration_quality(
                    pass2_audit.frame_quality(frame_index),
                    tentative_pass3_audit.frame_quality(frame_index),
                    iteration=3,
                    config=pose_v6_config.iterative,
                )
                if decision.accepted:
                    frames_improved_by_pass3 += 1
                else:
                    points_before, scores_before = pass2_snapshots[frame_index]
                    body_records[frame_index]["raw_points"] = points_before.copy()
                    body_records[frame_index]["raw_scores"] = scores_before.copy()
                    body_records[frame_index]["refined_joint_indexes"] = pass2_refined_indexes[frame_index]
                    body_records[frame_index]["refined_measurement"] = pass2_refined_measurements[frame_index]
                    body_records[frame_index]["bbox_source"] = pass2_bbox_sources[frame_index]
                    body_records[frame_index]["bbox_array"] = pass2_bbox_snapshots[frame_index]
                    body_records[frame_index]["render_bbox_array"] = (
                        pass2_bbox_snapshots[frame_index].copy()
                        if isinstance(pass2_bbox_snapshots[frame_index], np.ndarray) else None
                    )
                    for side in ("left", "right"):
                        raw_hand_frames[side][frame_index] = pass2_hand_snapshots[side][frame_index]
                    body_records[frame_index].pop("pass3_fusion", None)
                    pass3_rollback_count += 1
                pass3_results.append({"frame_index": frame_index, **decision.to_dict()})
            if pass3_rollback_count:
                replay_graph = BiomechanicalPoseGraph(pose_graph.config)
                for record in body_records:
                    replayed = replay_graph.update(
                        raw_points=record["raw_points"], raw_scores=record["raw_scores"],
                        bbox=record["bbox_array"], tracking=record["tracking_decision"],
                        frame_width=width, frame_height=height,
                        timestamp_seconds=float(record["source_timestamp_seconds"]),
                        relative_depth=None,
                        motion_gate_multiplier=float(record["motion_v6"].get("gate_multiplier", 1.0)),
                    )
                    record["pose_graph"] = replayed
                    validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                    validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                    count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
                    validated_points[:count] = replayed.analysis_points[:count]
                    validated_scores[:count] = replayed.analysis_scores[:count]
                    record["smoothed_points"] = validated_points
                    record["smoothed_scores"] = validated_scores
                pose_graph = replay_graph
            pass3_audit = audit_current_pose()
            if pass3_audit.quality_score < pass2_audit.quality_score:
                globally_rolled_back = [
                    index for index, record in enumerate(body_records)
                    if isinstance(record.get("pass3_fusion"), dict)
                ]
                for frame_index in globally_rolled_back:
                    points_before, scores_before = pass2_snapshots[frame_index]
                    record = body_records[frame_index]
                    record["raw_points"] = points_before.copy()
                    record["raw_scores"] = scores_before.copy()
                    record["refined_joint_indexes"] = pass2_refined_indexes[frame_index]
                    record["refined_measurement"] = pass2_refined_measurements[frame_index]
                    record["bbox_source"] = pass2_bbox_sources[frame_index]
                    record["bbox_array"] = pass2_bbox_snapshots[frame_index]
                    record["render_bbox_array"] = (
                        pass2_bbox_snapshots[frame_index].copy()
                        if isinstance(pass2_bbox_snapshots[frame_index], np.ndarray) else None
                    )
                    for side in ("left", "right"):
                        raw_hand_frames[side][frame_index] = pass2_hand_snapshots[side][frame_index]
                    record.pop("pass3_fusion", None)
                if globally_rolled_back:
                    pass3_rollback_count += len(globally_rolled_back)
                    frames_improved_by_pass3 = 0
                    pass3_results.append({
                        "scope": "whole-pass",
                        "rolled_back": True,
                        "quality_score_before": round(pass2_audit.quality_score, 6),
                        "quality_score_after": round(pass3_audit.quality_score, 6),
                        "reason": "PASS3_REGRESSION",
                    })
                    replay_graph = BiomechanicalPoseGraph(pose_graph.config)
                    for record in body_records:
                        replayed = replay_graph.update(
                            raw_points=record["raw_points"], raw_scores=record["raw_scores"],
                            bbox=record["bbox_array"], tracking=record["tracking_decision"],
                            frame_width=width, frame_height=height,
                            timestamp_seconds=float(record["source_timestamp_seconds"]),
                            relative_depth=None,
                            motion_gate_multiplier=float(record["motion_v6"].get("gate_multiplier", 1.0)),
                        )
                        record["pose_graph"] = replayed
                        validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                        validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                        count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
                        validated_points[:count] = replayed.analysis_points[:count]
                        validated_scores[:count] = replayed.analysis_scores[:count]
                        record["smoothed_points"] = validated_points
                        record["smoothed_scores"] = validated_scores
                    pose_graph = replay_graph
                    pass3_audit = audit_current_pose()
        except (cv2.error, ValueError, TypeError, RuntimeError) as error:
            logger.warning(
                "Pose V6.6 Pass 3 unavailable for %s; best Pass 2 state retained: %s.",
                analysis_id, type(error).__name__,
            )
            for index, (points_before, scores_before) in enumerate(pass2_snapshots):
                body_records[index]["raw_points"] = points_before
                body_records[index]["raw_scores"] = scores_before
                body_records[index]["refined_joint_indexes"] = pass2_refined_indexes[index]
                body_records[index]["refined_measurement"] = pass2_refined_measurements[index]
                body_records[index]["bbox_source"] = pass2_bbox_sources[index]
                body_records[index]["bbox_array"] = pass2_bbox_snapshots[index]
                body_records[index]["render_bbox_array"] = (
                    pass2_bbox_snapshots[index].copy()
                    if isinstance(pass2_bbox_snapshots[index], np.ndarray) else None
                )
                for side in ("left", "right"):
                    raw_hand_frames[side][index] = pass2_hand_snapshots[side][index]
                body_records[index].pop("pass3_fusion", None)
            replay_graph = BiomechanicalPoseGraph(pose_graph.config)
            for record in body_records:
                replayed = replay_graph.update(
                    raw_points=record["raw_points"], raw_scores=record["raw_scores"],
                    bbox=record["bbox_array"], tracking=record["tracking_decision"],
                    frame_width=width, frame_height=height,
                    timestamp_seconds=float(record["source_timestamp_seconds"]),
                    relative_depth=None,
                    motion_gate_multiplier=float(record["motion_v6"].get("gate_multiplier", 1.0)),
                )
                record["pose_graph"] = replayed
                validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
                validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
                count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
                validated_points[:count] = replayed.analysis_points[:count]
                validated_scores[:count] = replayed.analysis_scores[:count]
                record["smoothed_points"] = validated_points
                record["smoothed_scores"] = validated_scores
            pose_graph = replay_graph
            pass3_audit = pass2_audit
            pass3_rollback_count += 1
        finally:
            pass3_capture.release()
            pass3_seconds = time.perf_counter() - pass3_started_at

    high_motion_started_at = time.perf_counter()
    critical_frame_indexes = {
        frame_index
        for segment in critical_segments
        for frame_index in range(segment.start_frame, segment.end_frame + 1)
    }
    high_motion_summary = _run_high_motion_recovery_pass(
        video_path,
        body_records,
        model,
        settings,
        pose_v6_config,
        frame_width=width,
        frame_height=height,
        critical_frame_indexes=critical_frame_indexes,
        logger=logger,
    )
    high_motion_seconds = time.perf_counter() - high_motion_started_at
    if int(high_motion_summary.get("accepted_chain_count", 0)) > 0:
        replay_graph = BiomechanicalPoseGraph(pose_graph.config)
        for record in body_records:
            replayed = replay_graph.update(
                raw_points=record["raw_points"],
                raw_scores=record["raw_scores"],
                bbox=record["bbox_array"],
                tracking=record["tracking_decision"],
                frame_width=width,
                frame_height=height,
                timestamp_seconds=float(record["source_timestamp_seconds"]),
                relative_depth=None,
                motion_gate_multiplier=float(
                    record["motion_v6"].get("gate_multiplier", 1.0)
                ),
            )
            record["pose_graph"] = replayed
            validated_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
            validated_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
            body_count = min(BODY_POINT_COUNT, replayed.analysis_points.shape[0])
            validated_points[:body_count] = replayed.analysis_points[:body_count]
            validated_scores[:body_count] = replayed.analysis_scores[:body_count]
            record["smoothed_points"] = validated_points
            record["smoothed_scores"] = validated_scores
        pose_graph = replay_graph
        pass3_audit = audit_current_pose()

    expert_candidates = assess_local_expert_candidates()
    expert_model_evaluation = pose_model_evaluation_table(expert_candidates)
    expert_segments = select_critical_segments(
        pass3_audit,
        maximum_ratio=pose_v6_config.iterative.expert_resolution_ratio,
    ) if pose_v6_config.iterative.enabled else []
    expert_resolution_summary: dict[str, object] = {
        "enabled_by_profile": pose_v6_config.iterative.expert_resolution_ratio > 0.0,
        "maximum_frame_ratio": pose_v6_config.iterative.expert_resolution_ratio,
        "candidate_segment_count": len(expert_segments),
        "candidate_frame_count": sum(segment.frame_count for segment in expert_segments),
        "executed_frame_count": 0,
        "usage_ratio": 0.0,
        "backend_executed": False,
        "source_if_executed": "EXPERT_REFINED_MODEL",
        "reason": (
            "no repository-configured expert weights, validated canonical mapping, "
            "or same-video quality benchmark"
        ),
        "candidates": [candidate.to_dict() for candidate in expert_candidates],
    }

    smoothing_started_at = time.perf_counter()
    smoothed_points, smoothed_scores, interpolation_masks = smooth_body_sequence(
        [record["smoothed_points"] for record in body_records],
        [record["smoothed_scores"] for record in body_records],
        [record["tracking_state"] for record in body_records],
        frame_width=width,
        frame_height=height,
        # V6 owns gap filling and provenance.  This legacy helper now performs
        # only its robust bidirectional smoothing over actual measurements.
        maximum_gap_frames=0,
        interpolation_allowed=[
            record["pose_graph"].interpolation_allowed()
            for record in body_records
        ],
    )
    temporal_frames = reconstruct_temporal_sequence(
        smoothed_points,
        smoothed_scores,
        [record["raw_scores"] for record in body_records],
        [float(record["source_timestamp_seconds"]) for record in body_records],
        [str(record["tracking_state"]) for record in body_records],
        [
            bool(
                record["camera_motion"] is not None
                and record["camera_motion"].scene_cut
            )
            for record in body_records
        ],
        maximum_interpolation_seconds=(
            pose_v6_config.temporal.analysis_interpolation_seconds
        ),
        maximum_prediction_seconds=(
            pose_v6_config.temporal.render_persistence_seconds
        ),
        refined_joints={
            index: record["refined_joint_indexes"]
            for index, record in enumerate(body_records)
            if record["refined_joint_indexes"]
        },
        body_joint_count=BODY_POINT_COUNT,
    )
    try:
        temporal_frames = _apply_pose_v6_optical_flow(
            video_path,
            active_segment,
            body_records,
            temporal_frames,
            pose_v6_config,
            frame_width=width,
            frame_height=height,
        )
    except (cv2.error, RuntimeError, ValueError, TypeError) as error:
        logger.warning(
            "Pose V6 optical flow unavailable for %s; Hermite reconstruction retained: %s.",
            analysis_id,
            type(error).__name__,
        )
    trajectory_result = refine_fixed_lag_sequence(
        temporal_frames,
        [float(record["pose_graph"].body_scale) for record in body_records],
        [float(record["source_timestamp_seconds"]) for record in body_records],
        [str(record["motion_v6"]["state"]) for record in body_records],
        [str(record["tracking_state"]) for record in body_records],
        [
            bool(record["camera_motion"] is not None and record["camera_motion"].scene_cut)
            for record in body_records
        ],
        lag_frames=2,
    )
    temporal_frames = trajectory_result.frames
    global_optimization_started_at = time.perf_counter()
    global_optimization_result = optimize_global_trajectories(
        temporal_frames,
        [float(record["pose_graph"].body_scale) for record in body_records],
        [str(record["motion_v6"]["state"]) for record in body_records],
        [str(record["tracking_state"]) for record in body_records],
        scene_cut_flags,
        config=pose_v6_config.iterative,
        body_joint_count=BODY_POINT_COUNT,
        timestamps=[
            float(record["source_timestamp_seconds"]) for record in body_records
        ],
    )
    temporal_frames = global_optimization_result.frames
    post_global_optimization_audit = audit_pose_sequence(
        [frame.analysis_points for frame in temporal_frames],
        [frame.analysis_scores for frame in temporal_frames],
        [float(record["pose_graph"].body_scale) for record in body_records],
        [float(record["source_timestamp_seconds"]) for record in body_records],
        [str(record["tracking_state"]) for record in body_records],
        [str(record["motion_v6"]["state"]) for record in body_records],
        scene_cut_flags,
        config=pose_v6_config.iterative,
        prediction_ages=[frame.prediction_age_seconds for frame in temporal_frames],
        flow_errors=[frame.flow_errors for frame in temporal_frames],
        point_sources=[frame.sources for frame in temporal_frames],
        body_joint_count=BODY_POINT_COUNT,
    )
    anatomical_result = project_anatomical_sequence(
        temporal_frames,
        [float(record["pose_graph"].body_scale) for record in body_records],
        [float(record["source_timestamp_seconds"]) for record in body_records],
        [str(record["tracking_state"]) for record in body_records],
        [
            bool(record["camera_motion"] is not None and record["camera_motion"].scene_cut)
            for record in body_records
        ],
        maximum_prediction_seconds=pose_v6_config.temporal.render_persistence_seconds,
    )
    temporal_frames = anatomical_result.frames
    post_anatomical_audit = audit_pose_sequence(
        [frame.analysis_points for frame in temporal_frames],
        [frame.analysis_scores for frame in temporal_frames],
        [float(record["pose_graph"].body_scale) for record in body_records],
        [float(record["source_timestamp_seconds"]) for record in body_records],
        [str(record["tracking_state"]) for record in body_records],
        [str(record["motion_v6"]["state"]) for record in body_records],
        scene_cut_flags,
        config=pose_v6_config.iterative,
        point_sources=[frame.sources for frame in temporal_frames],
        body_joint_count=BODY_POINT_COUNT,
    )
    final_repair_codes = {
        PoseErrorCode.JOINT_JUMP,
        PoseErrorCode.TEMPORAL_DISCONTINUITY,
        PoseErrorCode.BONE_LENGTH_ERROR,
        PoseErrorCode.ANGLE_OUTLIER,
        PoseErrorCode.LEFT_RIGHT_AMBIGUITY,
    }
    final_repair_requested = any(
        error.repairable
        and error.error_confidence >= pose_v6_config.iterative.minimum_repair_error_confidence
        and error.code in final_repair_codes
        for error in post_anatomical_audit.errors
    )
    local_repair_summary: dict[str, object] = {
        "triggered": final_repair_requested,
        "accepted": False,
        "trigger_error_count": sum(
            error.code in final_repair_codes for error in post_anatomical_audit.errors
        ),
    }
    if final_repair_requested and pose_v6_config.iterative.enabled:
        local_repair_frame_indexes = {
            frame_index
            for segment in post_anatomical_audit.hard_segments
            if any(code in final_repair_codes for code in segment.error_codes)
            for frame_index in range(segment.start_frame, segment.end_frame + 1)
        }
        local_repair_result = optimize_global_trajectories(
            temporal_frames,
            [float(record["pose_graph"].body_scale) for record in body_records],
            [str(record["motion_v6"]["state"]) for record in body_records],
            [str(record["tracking_state"]) for record in body_records],
            scene_cut_flags,
            config=pose_v6_config.iterative,
            body_joint_count=BODY_POINT_COUNT,
            allowed_frame_indexes=local_repair_frame_indexes,
            timestamps=[
                float(record["source_timestamp_seconds"]) for record in body_records
            ],
        )
        local_repair_summary["segments"] = [
            segment.to_dict()
            for segment in post_anatomical_audit.hard_segments
            if any(code in final_repair_codes for code in segment.error_codes)
        ]
        local_repair_summary.update(local_repair_result.summary)
        if int(local_repair_result.summary.get("correction_count", 0)) > 0:
            temporal_frames = local_repair_result.frames
            anatomical_result = project_anatomical_sequence(
                temporal_frames,
                [float(record["pose_graph"].body_scale) for record in body_records],
                [float(record["source_timestamp_seconds"]) for record in body_records],
                [str(record["tracking_state"]) for record in body_records],
                scene_cut_flags,
                maximum_prediction_seconds=pose_v6_config.temporal.render_persistence_seconds,
            )
            temporal_frames = anatomical_result.frames
            local_repair_summary["accepted"] = True
            for initial, repaired in zip(
                global_optimization_result.frame_diagnostics,
                local_repair_result.frame_diagnostics,
            ):
                indexes = sorted({
                    *initial.get("corrected_joint_indexes", []),
                    *repaired.get("corrected_joint_indexes", []),
                })
                initial["corrected_joint_indexes"] = indexes
                initial["correction_count"] = int(initial.get("correction_count", 0)) + int(
                    repaired.get("correction_count", 0)
                )
                initial_iterations = initial.get("repair_iterations_by_joint", {})
                repaired_iterations = repaired.get("repair_iterations_by_joint", {})
                if isinstance(initial_iterations, dict) and isinstance(repaired_iterations, dict):
                    initial["repair_iterations_by_joint"] = {
                        key: int(initial_iterations.get(key, 0))
                        + int(repaired_iterations.get(key, 0))
                        for key in {*initial_iterations, *repaired_iterations}
                    }
            global_optimization_result.summary["correction_count"] = int(
                global_optimization_result.summary.get("correction_count", 0)
            ) + int(local_repair_result.summary.get("correction_count", 0))
            global_optimization_result.summary["repaired_frames_count"] = min(
                len(body_records),
                int(global_optimization_result.summary.get("repaired_frames_count", 0))
                + int(local_repair_result.summary.get("repaired_frames_count", 0)),
            )
            global_optimization_result.summary["rollback_count"] = int(
                global_optimization_result.summary.get("rollback_count", 0)
            ) + int(local_repair_result.summary.get("rollback_count", 0))
    global_optimization_result.summary["final_local_repair"] = local_repair_summary
    global_optimization_seconds = time.perf_counter() - global_optimization_started_at
    final_expected_lengths: list[dict[str, float | None]] = []
    track_ids: list[str] = []
    track_epoch = 0
    previous_track_active = False
    for record in body_records:
        current_track_active = str(record["tracking_state"]) not in {
            TrackingState.LOST.value,
            TrackingState.REACQUIRING.value,
        }
        scene_cut = bool(
            record["camera_motion"] is not None
            and record["camera_motion"].scene_cut
        )
        if current_track_active and (not previous_track_active or scene_cut):
            track_epoch += 1
        track_ids.append(f"{analysis_id}:track-{track_epoch}")
        previous_track_active = current_track_active

    for index, (record, temporal) in enumerate(zip(body_records, temporal_frames)):
        pass3_indexes = set(
            record.get("pass3_fusion", {}).get("accepted_joint_indexes", [])
            if isinstance(record.get("pass3_fusion"), dict) else []
        )
        high_motion_indexes: set[int] = set()
        high_motion_record = record.get("high_motion_recovery_v66")
        if isinstance(high_motion_record, dict):
            for value in high_motion_record.values():
                if isinstance(value, dict) and value.get("accepted") is True:
                    high_motion_indexes.update(value.get("accepted_joint_indexes", []))
        source_passes: list[str] = []
        for joint_index, source in enumerate(temporal.sources):
            if source not in {PointSource.MEASURED, PointSource.REFINED_MEASUREMENT}:
                source_passes.append(f"temporal-{source.value.lower()}")
            elif joint_index in high_motion_indexes:
                source_passes.append("pass4-high-motion-limb")
            elif joint_index in pass3_indexes:
                source_passes.append("pass3-critical")
            elif joint_index in record["refined_joint_indexes"]:
                source_passes.append("pass2-refinement")
            else:
                source_passes.append("pass1-primary")
        temporal_frames[index] = attach_temporal_metadata(
            temporal,
            timestamp_seconds=float(record["source_timestamp_seconds"]),
            source_passes=source_passes,
            track_id=track_ids[index],
        )
        graph = record["pose_graph"]
        expected: dict[str, float | None] = {}
        for name, bone in graph.bones.items():
            canonical = anatomical_result.profile.expected_pixels(
                {
                    "left_lower_leg": "left_shin",
                    "right_lower_leg": "right_shin",
                }.get(name, name),
                float(graph.body_scale),
            )
            expected[name] = canonical if canonical is not None else (
                bone.reference_length * float(graph.body_scale)
                if bone.reference_length is not None else None
            )
        final_expected_lengths.append(expected)

    limb_chain_result = enforce_limb_chain_consistency(
        temporal_frames,
        [float(record["source_timestamp_seconds"]) for record in body_records],
        [float(record["pose_graph"].body_scale) for record in body_records],
        BODY_BONES,
        final_expected_lengths,
        maximum_endpoint_age_delta=(
            pose_v6_config.high_motion.maximum_endpoint_age_delta_seconds
        ),
    )
    temporal_frames = list(limb_chain_result.frames)
    for index, record in enumerate(body_records):
        record["trajectory_refinement"] = trajectory_result.frame_diagnostics[index]
        record["global_trajectory_optimization"] = (
            global_optimization_result.frame_diagnostics[index]
        )
        temporal = temporal_frames[index]
        graph = record["pose_graph"]
        canonical_names = {
            "left_lower_leg": "left_shin",
            "right_lower_leg": "right_shin",
        }
        expected_bone_lengths = {}
        for name, bone in graph.bones.items():
            canonical = anatomical_result.profile.expected_pixels(
                canonical_names.get(name, name),
                float(graph.body_scale),
            )
            expected_bone_lengths[name] = canonical if canonical is not None else (
                bone.reference_length * float(graph.body_scale)
                if bone.reference_length is not None
                else None
            )
        temporal_bones = validate_analysis_bones(
            temporal,
            BODY_BONES,
            expected_bone_lengths,
            body_scale=float(graph.body_scale),
        )
        unsafe_reconstructed_joints = {
            endpoint
            for name, diagnostic in temporal_bones.items()
            if diagnostic["valid"] is False
            for endpoint in BODY_BONES[name]
            if temporal.sources[endpoint]
            in {
                PointSource.INTERPOLATED,
                PointSource.FLOW_TRACKED,
                PointSource.KINEMATIC_RECONSTRUCTED,
            }
        }
        if unsafe_reconstructed_joints:
            temporal = reject_reconstructed_analysis_joints(
                temporal,
                unsafe_reconstructed_joints,
            )
            temporal_frames[index] = temporal
            temporal_bones = validate_analysis_bones(
                temporal,
                BODY_BONES,
                expected_bone_lengths,
                body_scale=float(graph.body_scale),
            )
        record["smoothed_points"] = temporal.analysis_points
        record["smoothed_scores"] = temporal.analysis_scores
        record["body_interpolated"] = np.asarray(
            [source == PointSource.INTERPOLATED for source in temporal.sources],
            dtype=bool,
        )
        record["temporal_v6"] = temporal
        record["final_track_id_v66"] = track_ids[index]
        record["limb_chain_v66"] = limb_chain_result.frame_diagnostics[index]
        record["high_motion_error_causes_v66"] = sorted(set([
            *record.get("high_motion_error_causes_v66", []),
            *record["limb_chain_v66"].get("rejection_reasons", []),
        ]))
        record["atomic_bones_v66"] = limb_chain_result.bone_decisions[index]
        record["temporal_joints_v6"] = temporal.joint_metadata(JOINT_NAMES)
        pass2_joint_diagnostics = (
            record["refinement_fusion"].get("joint_diagnostics", [])
            if isinstance(record.get("refinement_fusion"), dict) else []
        )
        pass3_joint_diagnostics = (
            record["pass3_fusion"].get("joint_diagnostics", [])
            if isinstance(record.get("pass3_fusion"), dict) else []
        )
        global_corrections = set(
            record["global_trajectory_optimization"].get("corrected_joint_indexes", [])
        )
        repair_iterations_by_joint = record["global_trajectory_optimization"].get(
            "repair_iterations_by_joint", {}
        )
        for joint_index, joint_name in enumerate(JOINT_NAMES):
            if joint_name not in record["temporal_joints_v6"]:
                continue
            selected = (
                pass3_joint_diagnostics[joint_index]
                if joint_index < len(pass3_joint_diagnostics)
                and pass3_joint_diagnostics[joint_index].get("selected_pass") == 3
                else pass2_joint_diagnostics[joint_index]
                if joint_index < len(pass2_joint_diagnostics)
                else {
                    "selected_pass": 1,
                    "selected_source": "pass1-primary",
                    "consensus_score": round(float(temporal.render_scores[joint_index]), 6),
                    "correction_count": 0,
                }
            )
            record["temporal_joints_v6"][joint_name].update({
                "selected_pass": int(selected.get("selected_pass", 1)),
                "selected_source": str(selected.get("selected_source", "pass1-primary")),
                "consensus_score": float(selected.get("consensus_score", 0.0)),
                "correction_count": int(selected.get("correction_count", 0))
                + int(joint_index in global_corrections),
                "repair_iteration": int(
                    repair_iterations_by_joint.get(str(joint_index), 0)
                    if isinstance(repair_iterations_by_joint, dict) else 0
                ),
            })
        record["temporal_bones_v6"] = temporal_bones
        record["anatomical_v62"] = anatomical_result.frame_diagnostics[index]
    smoothing_seconds = time.perf_counter() - smoothing_started_at

    if processed_frames <= 0:
        raise RuntimeError(
            "Nie przetworzono żadnej klatki aktywnego fragmentu."
        )
    if detected_frames <= 0:
        raise RuntimeError("Nie wykryto pracownika w aktywnym fragmencie.")

    presence_ratio = detected_frames / processed_frames
    if presence_ratio < settings.min_presence_ratio:
        raise RuntimeError(
            "Jakość nagrania jest zbyt niska: pracownik został poprawnie "
            f"wykryty tylko w {presence_ratio * 100:.1f}% aktywnego fragmentu."
        )

    maybe_update_progress(
        supabase,
        analysis_id,
        settings.worker_id,
        72,
        "pose-v6-temporal-reconstruction",
    )

    hand_validation_started_at = time.perf_counter()
    hand_temporal_config = replace(
        hand_engine.config,
        max_interpolation_gap_frames=frames_for_seconds(
            min(0.12, pose_v6_config.temporal.analysis_interpolation_seconds),
            fps,
        ),
    )
    left_hand_result = stabilize_hand_track(
        "left",
        raw_hand_frames["left"],
        hand_temporal_config,
    )
    right_hand_result = stabilize_hand_track(
        "right",
        raw_hand_frames["right"],
        hand_temporal_config,
    )
    left_hand_result = enhance_hand_track(
        left_hand_result,
        frame_width=width,
        frame_height=height,
        config=hand_engine.config,
    )
    right_hand_result = enhance_hand_track(
        right_hand_result,
        frame_width=width,
        frame_height=height,
        config=hand_engine.config,
    )
    relevant_hand_frames = {
        side: [
            bool(record.get("detected")) and hand_rois[side][index] is not None
            for index, record in enumerate(body_records)
        ]
        for side in ("left", "right")
    }
    validated_hand_frames = {
        "left": left_hand_result.frames,
        "right": right_hand_result.frames,
    }
    hand_rescue_summary["coverage_after_validation"] = {
        side: round(
            observation_coverage(
                [frame.visible for frame in validated_hand_frames[side]],
                relevant_hand_frames[side],
            ),
            6,
        )
        for side in ("left", "right")
    }
    rescued_indexes = hand_rescue_summary.pop("_rescued_frame_indexes", {})
    hand_rescue_summary["rejected_rescue_observations"] = {
        side: sum(
            not validated_hand_frames[side][index].visible
            for index in rescued_indexes.get(side, [])
            if 0 <= index < len(validated_hand_frames[side])
        )
        for side in ("left", "right")
    }
    hand_validation_seconds = time.perf_counter() - hand_validation_started_at

    hand_object_started_at = time.perf_counter()
    # Source time remains authoritative even when gaps exist between active
    # segments. This prevents exposure and key moments from being compressed.
    output_timestamps = [
        float(record["source_timestamp_seconds"]) for record in body_records
    ]
    object_association_available = True
    try:
        tracked_object_frames = track_object_sequence(
            object_detection_frames,
            output_timestamps,
            frame_width=width,
            frame_height=height,
        )
    except (ValueError, TypeError, OverflowError, FloatingPointError) as error:
        object_association_available = False
        tracked_object_frames = [[] for _ in body_records]
        logger.warning(
            "Object association V2 wyłączone dla analizy %s: %s.",
            analysis_id,
            type(error).__name__,
        )
    pose_graph_frames = [record["pose_graph"] for record in body_records]
    left_hand_graph = analyze_hand_graph_sequence(
        "left",
        left_hand_result.frames,
        pose_graph_frames,
        tracked_object_frames,
        hand_rois["left"],
        config=hand_graph_config,
    )
    right_hand_graph = analyze_hand_graph_sequence(
        "right",
        right_hand_result.frames,
        pose_graph_frames,
        tracked_object_frames,
        hand_rois["right"],
        config=hand_graph_config,
    )
    left_grip_v4 = analyze_grip_v4(
        "left",
        left_hand_graph,
        output_timestamps,
        temporal_frames,
        confirmation_seconds=0.12,
        release_seconds=0.12,
        maximum_unknown_gap_seconds=0.25,
        fallback_fps=fps,
    )
    right_grip_v4 = analyze_grip_v4(
        "right",
        right_hand_graph,
        output_timestamps,
        temporal_frames,
        confirmation_seconds=0.12,
        release_seconds=0.12,
        maximum_unknown_gap_seconds=0.25,
        fallback_fps=fps,
    )
    grip_reanalysis_started_at = time.perf_counter()
    grip_reanalysis_summary: dict[str, object] = {
        "triggered_frames": [],
        "accepted": False,
        "rollback_count": 0,
        "flicker_count_before": 0,
        "flicker_count_after": 0,
    }
    grip_flicker_seed_indexes = sorted({
        *detect_grip_flicker(
            [frame.state.value for frame in left_grip_v4.frames],
            scene_cuts=scene_cut_flags,
        ),
        *detect_grip_flicker(
            [frame.state.value for frame in right_grip_v4.frames],
            scene_cuts=scene_cut_flags,
        ),
    })
    grip_flicker_indexes = list(grip_flicker_seed_indexes)
    if grip_flicker_seed_indexes and pose_v6_config.profile == "ULTRA":
        hand_context_frames = frames_for_seconds(
            min(0.15, pose_v6_config.iterative.critical_temporal_context_seconds),
            fps,
        )
        expanded_indexes: set[int] = set()
        for seed in grip_flicker_seed_indexes:
            for candidate in range(
                max(0, seed - hand_context_frames),
                min(processed_frames, seed + hand_context_frames + 1),
            ):
                start, end = sorted((seed, candidate))
                if not any(scene_cut_flags[start + 1:end + 1]):
                    expanded_indexes.add(candidate)
        grip_flicker_indexes = sorted(expanded_indexes)
    flicker_before = int(left_grip_v4.summary["single_frame_grip_flicker_count"]) + int(
        right_grip_v4.summary["single_frame_grip_flicker_count"]
    )
    def grip_pair_quality(left: Any, right: Any) -> float:
        frames = [*left.frames, *right.frames]
        if not frames:
            return 0.0
        valid_ratio = sum(frame.state.value != "UNKNOWN" for frame in frames) / len(frames)
        mean_confidence = float(np.mean([frame.confidence for frame in frames]))
        mean_geometry = float(np.mean([
            min(frame.palm_quality, frame.finger_quality) for frame in frames
        ]))
        flicker_count = int(left.summary["single_frame_grip_flicker_count"]) + int(
            right.summary["single_frame_grip_flicker_count"]
        )
        return float(np.clip(
            0.35 * valid_ratio + 0.35 * mean_confidence + 0.30 * mean_geometry
            - min(0.25, 0.06 * flicker_count),
            0.0, 1.0,
        ))

    grip_quality_before = grip_pair_quality(left_grip_v4, right_grip_v4)
    grip_reanalysis_summary["flicker_count_before"] = flicker_before
    grip_reanalysis_summary["seed_flicker_frames"] = grip_flicker_seed_indexes
    grip_reanalysis_summary["profile"] = pose_v6_config.profile
    grip_reanalysis_summary["roi_scale"] = (
        1.65 if pose_v6_config.profile == "ULTRA" else 1.45
    )
    grip_reanalysis_summary["quality_score_before"] = round(grip_quality_before, 6)
    grip_reanalysis_summary["quality_score_after"] = round(grip_quality_before, 6)
    if grip_flicker_indexes and pose_v6_config.iterative.enabled:
        hand_snapshots = {
            side: list(raw_hand_frames[side]) for side in ("left", "right")
        }
        hand_repass_capture = cv2.VideoCapture(str(video_path))
        hand_repass_memory = HandAssignmentMemory()
        try:
            if hand_repass_capture.isOpened():
                for frame_index in grip_flicker_indexes:
                    record = body_records[frame_index]
                    hand_repass_capture.set(
                        cv2.CAP_PROP_POS_FRAMES,
                        int(record["source_frame_index"]),
                    )
                    success, hand_frame = hand_repass_capture.read()
                    if not success or hand_frame is None or hand_frame.size == 0:
                        continue
                    expanded_rois = {
                        side: enlarge_roi(
                            hand_rois[side][frame_index],
                            frame_width=width,
                            frame_height=height,
                            scale=(
                                1.65 if pose_v6_config.profile == "ULTRA" else 1.45
                            ),
                        )
                        for side in ("left", "right")
                    }
                    combined_roi = union_hand_roi(
                        {side: roi for side, roi in expanded_rois.items() if roi is not None},
                        frame_width=width,
                        frame_height=height,
                    )
                    candidates = hand_engine.detect(
                        hand_frame,
                        int(round(float(record["source_timestamp_seconds"]) * 1000.0)),
                        combined_roi,
                    )
                    assignments = assign_hands_to_body_v2(
                        candidates,
                        record["smoothed_points"],
                        record["smoothed_scores"],
                        0.01,
                        hand_engine.config,
                        hand_graph_config,
                        float(record["source_timestamp_seconds"]),
                        hand_repass_memory,
                    )
                    for side in ("left", "right"):
                        if assignments[side].observation is not None:
                            raw_hand_frames[side][frame_index] = assignments[side]

                left_hand_result = enhance_hand_track(
                    stabilize_hand_track("left", raw_hand_frames["left"], hand_temporal_config),
                    frame_width=width, frame_height=height, config=hand_engine.config,
                )
                right_hand_result = enhance_hand_track(
                    stabilize_hand_track("right", raw_hand_frames["right"], hand_temporal_config),
                    frame_width=width, frame_height=height, config=hand_engine.config,
                )
                left_hand_graph = analyze_hand_graph_sequence(
                    "left", left_hand_result.frames, pose_graph_frames,
                    tracked_object_frames, hand_rois["left"], config=hand_graph_config,
                )
                right_hand_graph = analyze_hand_graph_sequence(
                    "right", right_hand_result.frames, pose_graph_frames,
                    tracked_object_frames, hand_rois["right"], config=hand_graph_config,
                )
                candidate_left_grip = analyze_grip_v4(
                    "left", left_hand_graph, output_timestamps, temporal_frames,
                    confirmation_seconds=0.12, release_seconds=0.12,
                    maximum_unknown_gap_seconds=0.25, fallback_fps=fps,
                )
                candidate_right_grip = analyze_grip_v4(
                    "right", right_hand_graph, output_timestamps, temporal_frames,
                    confirmation_seconds=0.12, release_seconds=0.12,
                    maximum_unknown_gap_seconds=0.25, fallback_fps=fps,
                )
                flicker_after = int(candidate_left_grip.summary["single_frame_grip_flicker_count"]) + int(
                    candidate_right_grip.summary["single_frame_grip_flicker_count"]
                )
                grip_reanalysis_summary["flicker_count_after"] = flicker_after
                grip_quality_after = grip_pair_quality(
                    candidate_left_grip, candidate_right_grip,
                )
                grip_reanalysis_summary["quality_score_after"] = round(
                    grip_quality_after, 6,
                )
                grip_improved = (
                    flicker_after < flicker_before
                    and grip_quality_after >= grip_quality_before - 0.02
                ) or (
                    flicker_after == flicker_before
                    and grip_quality_after - grip_quality_before
                    >= pose_v6_config.iterative.minimum_quality_gain
                )
                if grip_improved:
                    left_grip_v4 = candidate_left_grip
                    right_grip_v4 = candidate_right_grip
                    grip_reanalysis_summary["accepted"] = True
                    grip_reanalysis_summary["triggered_frames"] = grip_flicker_indexes
                else:
                    raw_hand_frames = hand_snapshots
                    grip_reanalysis_summary["rollback_count"] = 1
            else:
                grip_reanalysis_summary["rollback_count"] = 1
        except (cv2.error, RuntimeError, ValueError, TypeError) as error:
            raw_hand_frames = hand_snapshots
            grip_reanalysis_summary["rollback_count"] = 1
            logger.warning(
                "Pose V6.6 hand re-pass unavailable for %s; previous grip state retained: %s.",
                analysis_id, type(error).__name__,
            )
        finally:
            hand_repass_capture.release()
        if not bool(grip_reanalysis_summary["accepted"]):
            left_hand_result = enhance_hand_track(
                stabilize_hand_track("left", raw_hand_frames["left"], hand_temporal_config),
                frame_width=width, frame_height=height, config=hand_engine.config,
            )
            right_hand_result = enhance_hand_track(
                stabilize_hand_track("right", raw_hand_frames["right"], hand_temporal_config),
                frame_width=width, frame_height=height, config=hand_engine.config,
            )
            left_hand_graph = analyze_hand_graph_sequence(
                "left", left_hand_result.frames, pose_graph_frames,
                tracked_object_frames, hand_rois["left"], config=hand_graph_config,
            )
            right_hand_graph = analyze_hand_graph_sequence(
                "right", right_hand_result.frames, pose_graph_frames,
                tracked_object_frames, hand_rois["right"], config=hand_graph_config,
            )
            left_grip_v4 = analyze_grip_v4(
                "left", left_hand_graph, output_timestamps, temporal_frames,
                confirmation_seconds=0.12, release_seconds=0.12,
                maximum_unknown_gap_seconds=0.25, fallback_fps=fps,
            )
            right_grip_v4 = analyze_grip_v4(
                "right", right_hand_graph, output_timestamps, temporal_frames,
                confirmation_seconds=0.12, release_seconds=0.12,
                maximum_unknown_gap_seconds=0.25, fallback_fps=fps,
            )
    grip_reanalysis_seconds = time.perf_counter() - grip_reanalysis_started_at
    holding_config = HoldingV2Config(
        enabled=settings.holding_enabled,
        minimum_confirmation_seconds=settings.holding_min_confirmation_seconds,
        release_confirmation_seconds=settings.holding_release_confirmation_seconds,
        maximum_unknown_gap_seconds=settings.holding_max_unknown_gap_seconds,
        enter_threshold=settings.holding_enter_threshold,
        keep_threshold=settings.holding_keep_threshold,
        exit_threshold=settings.holding_exit_threshold,
        minimum_static_seconds=settings.holding_min_static_seconds,
    )
    left_holding_frames, left_holding_summary = analyze_holding_v2(
        "left",
        left_hand_graph,
        output_timestamps,
        fps=fps,
        config=holding_config,
    )
    right_holding_frames, right_holding_summary = analyze_holding_v2(
        "right",
        right_hand_graph,
        output_timestamps,
        fps=fps,
        config=holding_config,
    )
    bimanual_holding = analyze_bimanual_holding_v2(
        left_holding_frames,
        right_holding_frames,
        output_timestamps,
        fps=fps,
        minimum_confirmation_seconds=settings.holding_min_confirmation_seconds,
    )
    holding_durations = _timestamp_durations(output_timestamps, fps)
    bimanual_observation_seconds = sum(
        duration
        for duration, left_frame, right_frame in zip(
            holding_durations,
            left_hand_result.frames,
            right_hand_result.frames,
        )
        if left_frame.visible and right_frame.visible
    )
    left_holding_v3 = analyze_holding_v3(
        [_holding_v3_evidence(frame) for frame in left_holding_frames],
        holding_durations,
        confirmation_seconds=settings.holding_min_confirmation_seconds,
        release_seconds=settings.holding_release_confirmation_seconds,
        unknown_gap_seconds=settings.holding_max_unknown_gap_seconds,
    )
    right_holding_v3 = analyze_holding_v3(
        [_holding_v3_evidence(frame) for frame in right_holding_frames],
        holding_durations,
        confirmation_seconds=settings.holding_min_confirmation_seconds,
        release_seconds=settings.holding_release_confirmation_seconds,
        unknown_gap_seconds=settings.holding_max_unknown_gap_seconds,
    )
    bimanual_holding_v3_flags = bimanual_holding_v3(
        left_holding_v3,
        right_holding_v3,
    )
    hand_object_seconds = time.perf_counter() - hand_object_started_at

    frame_quality_objects = []
    frame_quality_records: list[dict[str, object]] = []
    for index, record in enumerate(body_records):
        quality = build_frame_quality_v2(
            record["image_quality_v2"],
            body=record["pose_graph"],
            left_hand=left_hand_graph[index],
            right_hand=right_hand_graph[index],
            tracking_identity_score=float(record["tracking_identity_score"]),
        )
        frame_quality_objects.append(quality)
        frame_quality_records.append(quality.to_dict())

    raw_overlay_metric_frames: list[dict[str, dict[str, object]]] = []
    for index, body_record in enumerate(body_records):
        metric_input_frame = {
            "detected": body_record["detected"],
            "smoothed_keypoints": serialize_coordinates(
                body_record["smoothed_points"],
                body_record["smoothed_scores"],
            ),
            "scores": serialize_scores(body_record["smoothed_scores"]),
            "body_quality": body_record["pose_graph"].to_dict(),
            "temporal_v6": {
                "joints": body_record["temporal_joints_v6"],
                "analysis_bones": body_record["temporal_bones_v6"],
            },
            "left_hand": serialize_hand_frame(left_hand_result.frames[index]),
            "right_hand": serialize_hand_frame(right_hand_result.frames[index]),
        }
        raw_overlay_metric_frames.append(compute_overlay_metrics_from_frame(
            metric_input_frame,
            quality_threshold=settings.keypoint_threshold,
        ))
    angle_v2 = stabilize_angle_sequence(
        raw_overlay_metric_frames,
        temporal_frames,
        output_timestamps,
        [str(record["motion_v6"]["state"]) for record in body_records],
    )

    temporal_frames = list(freeze_temporal_frames(temporal_frames))
    for record, temporal in zip(body_records, temporal_frames):
        record["temporal_v6"] = temporal
    pre_render_skeleton_contract = validate_final_skeleton_contract(
        temporal_frames,
        expected_frame_count=processed_frames,
        body_joint_count=BODY_POINT_COUNT,
        identity_scores=[
            float(record["tracking_identity_score"]) for record in body_records
        ],
        require_immutable=True,
        require_v66_metadata=True,
    )

    writer = create_video_writer(
        raw_output_video_path,
        fps,
        width,
        height,
    )
    render_capture = cv2.VideoCapture(str(video_path))
    if not render_capture.isOpened():
        writer.release()
        raise RuntimeError(
            "OpenCV nie może ponownie otworzyć filmu do renderingu V4."
        )

    render_capture.set(
        cv2.CAP_PROP_POS_FRAMES,
        active_segment.start_frame,
    )

    frames_data: list[dict[str, Any]] = []
    best_quality = -1.0
    best_thumbnail: np.ndarray | None = None
    drawing_seconds = 0.0
    overlay_config = OverlayConfig(
        render_quality_threshold=settings.render_quality_threshold,
        fade_frames=settings.render_fade_frames,
        draw_angles=settings.draw_angles,
        draw_objects=settings.draw_objects,
        debug=settings.debug_overlay,
    )
    render_controller = BoneRenderController(overlay_config)
    persistent_renderer = PersistentBoneRenderer(
        persistence_seconds=pose_v6_config.temporal.render_persistence_seconds,
        minimum_quality=min(settings.render_quality_threshold, 0.35),
    )
    color_hysteresis = MetricColorHysteresis()
    overlay_palette = OverlayPalette()
    overlay_diagnostics_records: list[dict[str, object]] = []
    overlay_metric_frames = angle_v2.metric_frames
    render_v6_frames: list[dict[str, PersistentBone]] = []

    try:
        for frame_offset, body_record in enumerate(body_records):
            success, frame = render_capture.read()
            if not success or frame is None or frame.size == 0:
                raise RuntimeError(
                    "Nie udało się odczytać klatki podczas renderingu V4: "
                    f"{body_record['source_frame_index']}."
                )

            drawing_started_at = time.perf_counter()
            left_frame = left_hand_result.frames[frame_offset]
            right_frame = right_hand_result.frames[frame_offset]
            overlay_metrics = overlay_metric_frames[frame_offset]
            bbox_value = body_record.get("bbox_xyxy")
            bbox_array = (
                np.asarray(bbox_value, dtype=np.float32)
                if isinstance(bbox_value, list) and len(bbox_value) == 4
                else None
            )
            render_bbox_value = body_record.get("render_bbox_array")
            render_bbox_array = (
                np.asarray(render_bbox_value, dtype=np.float32)
                if render_bbox_value is not None
                and np.asarray(render_bbox_value).size == 4
                else bbox_array
            )
            temporal: TemporalFrame = body_record["temporal_v6"]
            camera = body_record["camera_motion"]
            scene_cut = bool(camera is not None and camera.scene_cut)
            if scene_cut:
                persistent_renderer.reset()
            bone_overrides: dict[str, PersistentBone] = {}
            for bone_name, (first_index, second_index) in BODY_BONES.items():
                graph_bone = body_record["pose_graph"].bones[bone_name]
                first_point = (
                    temporal.render_points[first_index]
                    if temporal.render_scores[first_index] > 0.0
                    else None
                )
                second_point = (
                    temporal.render_points[second_index]
                    if temporal.render_scores[second_index] > 0.0
                    else None
                )
                expected_length = (
                    anatomical_result.profile.expected_pixels(
                        {
                            "left_lower_leg": "left_shin",
                            "right_lower_leg": "right_shin",
                        }.get(bone_name, bone_name),
                        float(body_record["pose_graph"].body_scale),
                    )
                    or (
                        graph_bone.reference_length
                        * float(body_record["pose_graph"].body_scale)
                        if graph_bone.reference_length is not None
                        else None
                    )
                )
                bone_overrides[bone_name] = persistent_renderer.update(
                    bone_name,
                    first_point,
                    second_point,
                    first_source=temporal.sources[first_index].value,
                    second_source=temporal.sources[second_index].value,
                    confidence=min(
                        float(temporal.render_scores[first_index]),
                        float(temporal.render_scores[second_index]),
                    ),
                    timestamp_seconds=float(body_record["source_timestamp_seconds"]),
                    bbox=render_bbox_array,
                    expected_length=expected_length,
                    frame_width=width,
                    frame_height=height,
                    hard_lost=body_record["tracking_state"] == TrackingState.LOST.value,
                    scene_cut=False,
                    atomic_accepted=body_record["atomic_bones_v66"][bone_name].accepted,
                    atomic_reason=body_record["atomic_bones_v66"][bone_name].reason,
                    endpoint_age_delta=(
                        body_record["atomic_bones_v66"][bone_name].endpoint_age_delta
                    ),
                    bone_length_ratio_to_canonical=(
                        body_record["atomic_bones_v66"][bone_name]
                        .bone_length_ratio_to_canonical
                    ),
                    track_id=str(body_record["final_track_id_v66"]),
                )
            render_v6_frames.append(bone_overrides)
            layer_contract = build_frame_layer_contract(
                temporal,
                raw_scores=body_record["raw_scores"],
                rendered_bones=bone_overrides,
                left_hand_visible=left_frame.visible,
                left_hand_quality=left_frame.quality,
                right_hand_visible=right_frame.visible,
                right_hand_quality=right_frame.quality,
                tracking_state=str(body_record["tracking_state"]),
            )
            left_grip_frame = left_grip_v4.frames[frame_offset]
            right_grip_frame = right_grip_v4.frames[frame_offset]
            left_offset_value = left_grip_frame.wrist_alignment.get("overlay_translation_px")
            right_offset_value = right_grip_frame.wrist_alignment.get("overlay_translation_px")
            left_hand_offset = (
                tuple(float(value) for value in left_offset_value)
                if isinstance(left_offset_value, list) and len(left_offset_value) == 2
                else None
            )
            right_hand_offset = (
                tuple(float(value) for value in right_offset_value)
                if isinstance(right_offset_value, list) and len(right_offset_value) == 2
                else None
            )
            rendered_frame, overlay_diagnostics = draw_pose_overlay_v4(
                frame,
                body_record["pose_graph"],
                overlay_metrics,
                left_hand_graph[frame_offset],
                right_hand_graph[frame_offset],
                left_holding_frames[frame_offset],
                right_holding_frames[frame_offset],
                tracked_object_frames[frame_offset],
                render_controller=render_controller,
                color_hysteresis=color_hysteresis,
                config=overlay_config,
                palette=overlay_palette,
                bbox=bbox_array,
                render_bone_overrides=bone_overrides,
                render_joint_points=temporal.render_points,
                render_joint_scores=temporal.render_scores,
                render_joint_sources=[source.value for source in temporal.sources],
                left_hand_offset=left_hand_offset,
                right_hand_offset=right_hand_offset,
                left_grip_state=left_grip_frame.state.value,
                right_grip_state=right_grip_frame.state.value,
            )
            if settings.debug_overlay:
                render_source_counts = Counter(
                    item.source.value for item in bone_overrides.values()
                )
                cv2.putText(
                    rendered_frame,
                    (
                        f"V6 bbox={body_record['bbox_source']} "
                        f"motion={body_record['motion_v6']['state']} "
                        f"measured={render_source_counts.get('MEASURED', 0)} "
                        f"predicted={render_source_counts.get('HELD', 0) + render_source_counts.get('KINEMATIC_PREDICTED', 0)}"
                    ),
                    (18, 58),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.46,
                    (190, 235, 255),
                    1,
                    cv2.LINE_AA,
                )
                rejected_bones = sum(
                    not item.accepted
                    for item in body_record["atomic_bones_v66"].values()
                )
                cv2.putText(
                    rendered_frame,
                    (
                        f"blur={body_record['motion_blur_v66']['motion_blur_score']:.2f} "
                        f"max_age={float(np.max(temporal.prediction_age_seconds)):.3f}s "
                        f"atomic_reject={rejected_bones} "
                        f"track={body_record['final_track_id_v66'].rsplit('-', 1)[-1]}"
                    ),
                    (18, 98),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    (125, 205, 245),
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    rendered_frame,
                    (
                        f"angles={sum(item.get('analysis_usable') is True for item in angle_v2.diagnostics[frame_offset].values())} "
                        f"grip L={left_grip_v4.frames[frame_offset].state.value} "
                        f"R={right_grip_v4.frames[frame_offset].state.value}"
                    ),
                    (18, 78),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (170, 225, 245),
                    1,
                    cv2.LINE_AA,
                )
            overlay_diagnostics_records.append(
                {
                    "rendered_bones": overlay_diagnostics.rendered_bones,
                    "hidden_bones": overlay_diagnostics.hidden_bones,
                    "safety_rejections": overlay_diagnostics.safety_rejections,
                    "maximum_rendered_length": round(overlay_diagnostics.maximum_rendered_length, 3),
                    "severities": overlay_diagnostics.severities,
                    "render_sources": overlay_diagnostics.render_sources,
                    "overlay_label_overlap_count": overlay_diagnostics.overlay_label_overlap_count,
                    "overlay_label_readability_score": overlay_diagnostics.overlay_label_readability_score,
                    "overlay_main_metric_visibility_ratio": overlay_diagnostics.overlay_main_metric_visibility_ratio,
                    "overlay_label_count": overlay_diagnostics.label_count,
                    "bone_sources": {
                        name: item.source.value for name, item in bone_overrides.items()
                    },
                    "bone_visibility_states": {
                        name: item.visibility_state for name, item in bone_overrides.items()
                    },
                    "bone_prediction_age_seconds": {
                        name: round(item.age_seconds, 6)
                        for name, item in bone_overrides.items()
                    },
                    "bone_endpoint_age_delta": {
                        name: round(item.endpoint_age_delta, 6)
                        for name, item in bone_overrides.items()
                    },
                    "bone_length_ratio_to_canonical": {
                        name: (
                            round(item.bone_length_ratio_to_canonical, 6)
                            if item.bone_length_ratio_to_canonical is not None else None
                        )
                        for name, item in bone_overrides.items()
                    },
                    "bone_rejection_reasons": {
                        name: item.rejection_reason
                        for name, item in bone_overrides.items()
                        if item.rejection_reason is not None
                    },
                }
            )

            output_timestamp = body_record["output_timestamp_seconds"]
            cv2.putText(
                rendered_frame,
                (
                    "Ergonomia AI Pose V6 | aktywny fragment "
                    f"{output_timestamp:05.2f}s / "
                    f"{active_segment.duration_seconds:05.2f}s"
                ),
                (18, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            writer.write(rendered_frame)
            drawing_seconds += time.perf_counter() - drawing_started_at

            hand_bonus = (
                (left_frame.quality if left_frame.visible else 0.0)
                + (right_frame.quality if right_frame.visible else 0.0)
            )
            thumbnail_quality = float(frame_quality_records[frame_offset]["score"]) + hand_bonus
            if body_record["detected"] and thumbnail_quality > best_quality:
                best_quality = thumbnail_quality
                best_thumbnail = rendered_frame.copy()

            frames_data.append(
                {
                    "source_frame_index": body_record["source_frame_index"],
                    "output_frame_index": body_record["output_frame_index"],
                    "analysis_frame_index": body_record["analysis_frame_index"],
                    "source_timestamp_seconds": round(
                        body_record["source_timestamp_seconds"],
                        4,
                    ),
                    "output_timestamp_seconds": round(
                        body_record["output_timestamp_seconds"],
                        4,
                    ),
                    "detected": body_record["detected"],
                    "raw_person_detected": body_record["raw_person_detected"],
                    "bbox_source": body_record["bbox_source"],
                    "refinement_fusion": body_record.get("refinement_fusion"),
                    "pass3_fusion": body_record.get("pass3_fusion"),
                    "high_motion_recovery_v66": body_record.get(
                        "high_motion_recovery_v66"
                    ),
                    "trajectory_refinement": body_record.get("trajectory_refinement"),
                    "global_trajectory_optimization": body_record.get(
                        "global_trajectory_optimization"
                    ),
                    "motion_v6": body_record["motion_v6"],
                    "motion_blur_v66": body_record["motion_blur_v66"],
                    "high_motion_error_causes_v66": body_record[
                        "high_motion_error_causes_v66"
                    ],
                    "track_started": body_record["track_started"],
                    "track_ended": body_record["track_ended"],
                    "tracking_state": body_record["tracking_state"],
                    "tracking_reasons": body_record["tracking_reasons"],
                    "tracking_identity_score": round(
                        body_record["tracking_identity_score"], 6
                    ),
                    "selection_score": round(
                        body_record["selection_score"],
                        6,
                    ),
                    "body_keypoint_count": body_record["body_keypoint_count"],
                    "bbox_xyxy": body_record["bbox_xyxy"],
                    "inference_seconds": round(
                        body_record["inference_seconds"],
                        4,
                    ),
                    "raw_keypoints": serialize_coordinates(
                        body_record["raw_points"],
                        body_record["raw_scores"],
                    ),
                    "smoothed_keypoints": serialize_coordinates(
                        body_record["smoothed_points"],
                        body_record["smoothed_scores"],
                    ),
                    "scores": serialize_scores(
                        body_record["smoothed_scores"],
                    ),
                    "body_interpolated": body_record["body_interpolated"].astype(bool).tolist(),
                    "temporal_v6": {
                        "analysis_render_separated": True,
                        "coordinate_space": "ORIGINAL_PIXELS",
                        "track_id": body_record["final_track_id_v66"],
                        "joints": body_record["temporal_joints_v6"],
                        "analysis_bones": body_record["temporal_bones_v6"],
                        "atomic_bones_v66": {
                            name: decision.to_dict()
                            for name, decision in body_record[
                                "atomic_bones_v66"
                            ].items()
                        },
                        "limb_chain_consistency_v66": body_record[
                            "limb_chain_v66"
                        ],
                        "analysis_source_counts": dict(
                            Counter(
                                source.value
                                for source in body_record["temporal_v6"].sources[:BODY_POINT_COUNT]
                            )
                        ),
                    },
                    "anatomical_v62": body_record["anatomical_v62"],
                    "angles_v2": angle_v2.diagnostics[frame_offset],
                    "angles_v3": angle_v2.diagnostics[frame_offset],
                    "timeline_v6": {
                        "contract_version": "pose-timeline-coverage-v1",
                        "layers": layer_contract,
                    },
                    "camera_motion": (
                        body_record["camera_motion"].to_dict()
                        if body_record["camera_motion"] is not None
                        else {
                            "translation": [0.0, 0.0],
                            "magnitude_pixels": 0.0,
                            "track_count": 0,
                            "quality": 0.0,
                            "camera_shake": False,
                            "scene_cut": False,
                            "available": False,
                        }
                    ),
                    "body_quality": body_record["pose_graph"].to_dict(),
                    "tracking": {
                        "state": body_record["tracking_state"],
                        "identity_score": round(
                            body_record["tracking_identity_score"], 6
                        ),
                        "reasons": body_record["tracking_reasons"],
                        "prediction_is_measurement": False,
                    },
                    "body": {
                        "scale": round(body_record["pose_graph"].body_scale, 6),
                        "scale_quality": round(
                            body_record["pose_graph"].body_scale_quality, 6
                        ),
                        "coverage_ratio": round(
                            body_record["pose_graph"].body_coverage_ratio, 6
                        ),
                        "quality": round(body_record["pose_graph"].quality, 6),
                        "anchors": body_record["pose_graph"].to_dict()["anchors"],
                        "limbs": body_record["pose_graph"].to_dict()["limbs"],
                    },
                    "frame_quality": frame_quality_records[frame_offset],
                    "left_hand": {
                        **serialize_hand_frame(left_frame),
                        "pipeline_available": body_record["hand_error"] is None,
                        "graph_v2": left_hand_graph[frame_offset].to_dict(),
                        "grip": serialize_holding_frame_v2(
                            left_holding_frames[frame_offset]
                        ),
                        "grip_v4": left_grip_v4.frames[frame_offset].to_dict(),
                        "grip_v5": left_grip_v4.frames[frame_offset].to_dict(),
                    },
                    "right_hand": {
                        **serialize_hand_frame(right_frame),
                        "pipeline_available": body_record["hand_error"] is None,
                        "graph_v2": right_hand_graph[frame_offset].to_dict(),
                        "grip": serialize_holding_frame_v2(
                            right_holding_frames[frame_offset]
                        ),
                        "grip_v4": right_grip_v4.frames[frame_offset].to_dict(),
                        "grip_v5": right_grip_v4.frames[frame_offset].to_dict(),
                    },
                    "holding": {
                        "left": {
                            **serialize_holding_frame_v2(left_holding_frames[frame_offset]),
                            **left_holding_v3[frame_offset].to_dict(),
                            "legacy_v2_state": left_holding_frames[frame_offset].state.value,
                        },
                        "right": {
                            **serialize_holding_frame_v2(right_holding_frames[frame_offset]),
                            **right_holding_v3[frame_offset].to_dict(),
                            "legacy_v2_state": right_holding_frames[frame_offset].state.value,
                        },
                        "bimanual_candidate": bool(
                            bimanual_holding["frame_flags"][frame_offset]
                        ),
                        "bimanual_association_mode": (
                            bimanual_holding["association_modes"][frame_offset]
                        ),
                        "v3": {
                            "left": left_holding_v3[frame_offset].to_dict(),
                            "right": right_holding_v3[frame_offset].to_dict(),
                            "bimanual_confirmed": bimanual_holding_v3_flags[frame_offset],
                        },
                    },
                    "nearby_objects": [
                        {
                            "track_id": tracked.track_id,
                            "class_id": tracked.class_id,
                            "class_name": tracked.class_name,
                            "confidence": (
                                round(tracked.confidence, 6)
                                if tracked.confidence is not None
                                else None
                            ),
                            "bbox_xyxy": [
                                round(value, 2) for value in tracked.bbox_xyxy
                            ],
                            "center": [round(value, 3) for value in tracked.center],
                            "velocity": [round(value, 3) for value in tracked.velocity],
                            "age_frames": tracked.age_frames,
                        }
                        for tracked in tracked_object_frames[frame_offset]
                    ],
                    "metrics_for_overlay": overlay_metrics,
                    "render": overlay_diagnostics_records[frame_offset],
                }
            )

            rendered_count = frame_offset + 1
            if (
                rendered_count
                % settings.progress_update_interval_frames
                == 0
            ):
                render_ratio = rendered_count / max(1, processed_frames)
                progress = 73 + int(min(1.0, render_ratio) * 15)
                maybe_update_progress(
                    supabase,
                    analysis_id,
                    settings.worker_id,
                    min(progress, 88),
                    "pose-v6-rendering-persistent-skeleton",
                )
    finally:
        render_capture.release()
        writer.release()

    if best_thumbnail is None:
        raise RuntimeError(
            "Nie udało się wybrać miniatury z pracownikiem."
        )
    if not cv2.imwrite(str(thumbnail_path), best_thumbnail):
        raise RuntimeError("Nie udało się zapisać miniatury.")

    average_confidence = (
        confidence_sum / confidence_count
        if confidence_count > 0
        else 0.0
    )
    average_confidence = float(
        np.clip(average_confidence, 0.0, 1.0)
    )

    encoding_started_at = time.perf_counter()
    transcode_video_to_h264(
        raw_output_video_path,
        output_video_path,
        logger,
        settings.output_crf,
    )
    encoding_seconds = time.perf_counter() - encoding_started_at
    raw_output_video_path.unlink(missing_ok=True)

    finger_rejections = sum(
        len(finger.rejection_reasons)
        for hand in (*left_hand_graph, *right_hand_graph)
        for finger in hand.fingers.values()
    )
    holding_uncertain_seconds = (
        left_holding_summary.uncertain_seconds
        + right_holding_summary.uncertain_seconds
    )
    quality_summary = summarize_quality_v2(
        frame_quality_objects,
        track_losses=tracker.track_loss_count,
        hand_assignment_switches=hand_assignment_memory.assignment_switches,
        finger_rejections=finger_rejections,
        holding_uncertain_seconds=holding_uncertain_seconds,
    )
    warning_codes = quality_summary.get("warning_codes")
    if (
        isinstance(warning_codes, list)
        and (
            left_hand_result.summary.valid_ratio < 0.50
            or right_hand_result.summary.valid_ratio < 0.50
        )
        and "HIGH_FINGER_REJECTION" not in warning_codes
    ):
        warning_codes.append("HIGH_FINGER_REJECTION")
    pose_graph_summary = summarize_pose_graph(pose_graph_frames)
    pose_graph_summary["body_proportion_profile"] = (
        pose_graph.bone_profile.to_dict()
    )
    invalid_bone_count = int(pose_graph_summary["invalid_bone_count"])
    out_of_frame_frames = sum(
        any(limb.state.value == "OUT_OF_FRAME" for limb in frame.limbs.values())
        for frame in pose_graph_frames
    )
    partial_frames = sum(
        1 for record in body_records
        if record["tracking_state"] == TrackingState.PARTIAL.value
    )
    occluded_frames = sum(
        any(limb.state.value == "OCCLUDED" for limb in frame.limbs.values())
        for frame in pose_graph_frames
    )
    mean_pose_quality = float(np.mean([frame.quality for frame in pose_graph_frames]))
    movement_summary = summarize_overlay_movement(
        overlay_metric_frames,
        output_timestamps,
    )
    final_skeleton_contract = pre_render_skeleton_contract
    final_audit_degraded: dict[str, object] | None = None
    try:
        final_audit = audit_pose_sequence(
            [frame.analysis_points for frame in temporal_frames],
            [frame.analysis_scores for frame in temporal_frames],
            [float(record["pose_graph"].body_scale) for record in body_records],
            [float(record["source_timestamp_seconds"]) for record in body_records],
            [str(record["tracking_state"]) for record in body_records],
            [str(record["motion_v6"]["state"]) for record in body_records],
            scene_cut_flags,
            config=pose_v6_config.iterative,
            hand_visible={
                "left": [frame.visible for frame in left_hand_result.frames],
                "right": [frame.visible for frame in right_hand_result.frames],
            },
            hand_quality_values={
                "left": [frame.confidence for frame in left_grip_v4.frames],
                "right": [frame.confidence for frame in right_grip_v4.frames],
            },
            grip_states={
                "left": [frame.state.value for frame in left_grip_v4.frames],
                "right": [frame.state.value for frame in right_grip_v4.frames],
            },
            motion_blur=[bool(record["prevalidation_motion_blur"]) for record in body_records],
            prediction_ages=[frame.prediction_age_seconds for frame in temporal_frames],
            flow_errors=[frame.flow_errors for frame in temporal_frames],
            wrist_disagreement={
                "left": [
                    bool(frame.wrist_alignment.get("available"))
                    and not bool(frame.wrist_alignment.get("accepted"))
                    for frame in left_grip_v4.frames
                ],
                "right": [
                    bool(frame.wrist_alignment.get("available"))
                    and not bool(frame.wrist_alignment.get("accepted"))
                    for frame in right_grip_v4.frames
                ],
            },
            model_disagreements={
                index: [
                    *(
                        record["refinement_fusion"].get("rejected_disagreement_indexes", [])
                        if isinstance(record.get("refinement_fusion"), dict) else []
                    ),
                    *(
                        record["pass3_fusion"].get("model_disagreement_joint_indexes", [])
                        if isinstance(record.get("pass3_fusion"), dict) else []
                    ),
                ]
                for index, record in enumerate(body_records)
            },
            point_sources=[frame.sources for frame in temporal_frames],
            body_joint_count=BODY_POINT_COUNT,
        )
    except PoseAuditInputError as error:
        # Final geometry has already passed FinalSkeletonContract.  An optional
        # diagnostic-array contract failure degrades audit metadata only; it
        # must not discard several minutes of validated inference output.
        logger.warning(
            "Final Pose V6 audit degraded for %s: component=final_self_audit "
            "field=%s actual_shape=%s expected_shape=%s frame=%s",
            analysis_id,
            error.field,
            error.actual_shape,
            error.expected_shape,
            error.frame_index,
        )
        final_audit = post_anatomical_audit
        final_audit_degraded = {
            "degraded": True,
            "component": "final_self_audit",
            "field": error.field,
            "actual_shape": list(error.actual_shape),
            "expected_shape": error.expected_shape,
            "frame_index": error.frame_index,
            "fallback": "post_anatomical_audit",
        }
    for frame, audit_frame in zip(frames_data, final_audit.frames):
        frame["pose_self_audit_v64"] = audit_frame.to_dict()
        frame["pose_self_audit_v65"] = audit_frame.to_dict()
    global_summary = global_optimization_result.summary
    iterative_v65_summary = {
        "version": "iterative-refinement-v2",
        "profile": pose_v6_config.profile,
        "best_result_not_last": True,
        "refinement_iterations": 1
        + int(bool(refinement_results))
        + int(bool(critical_segments))
        + int(global_summary.get("iterations", 0)),
        "pass1_quality": round(pass1_audit.quality_score, 6),
        "pass2_quality": round(pass2_audit.quality_score, 6),
        "pass3_quality": round(pass3_audit.quality_score, 6),
        "expert_quality": None,
        "final_quality": round(final_audit.quality_score, 6),
        "pose_final_quality_score": round(final_audit.quality_score, 6),
        "quality_score_is_accuracy": False,
        "frames_improved_by_pass2": frames_improved_by_pass2,
        "frames_improved_by_pass3": frames_improved_by_pass3,
        "frames_improved_by_expert": 0,
        "pass2_usage_ratio": round(
            min(processed_frames, len(refinement_results)) / processed_frames, 6
        ),
        "pass3_usage_ratio": round(
            min(
                processed_frames,
                sum(segment.frame_count for segment in critical_segments),
            ) / processed_frames,
            6,
        ),
        "expert_pass_usage_ratio": 0.0,
        "frames_unchanged": max(
            0, processed_frames - frames_improved_by_pass2 - frames_improved_by_pass3,
        ),
        "frames_rolled_back": pass2_rollback_count + pass3_rollback_count,
        "rollback_count": pass2_rollback_count + pass3_rollback_count
        + int(global_summary.get("rollback_count", 0))
        + int(grip_reanalysis_summary.get("rollback_count", 0)),
        "repaired_frames_count": min(
            processed_frames,
            int(global_summary.get("repaired_frames_count", 0))
            + frames_improved_by_pass2 + frames_improved_by_pass3
            + len(grip_reanalysis_summary.get("triggered_frames", [])),
        ),
        "critical_segments_count": len(critical_segments),
        "hard_segments_count": len(pass1_audit.hard_segments),
        "global_optimization_applied": int(
            global_summary.get("correction_count", 0)
        ) > 0,
        "pass1_self_audit": pass1_audit.to_dict(include_frame_audit=False),
        "pass2_self_audit": pass2_audit.to_dict(include_frame_audit=False),
        "pass3_self_audit": pass3_audit.to_dict(include_frame_audit=False),
        "expert_resolution_pass": expert_resolution_summary,
        "post_global_optimization_self_audit": (
            post_global_optimization_audit.to_dict(include_frame_audit=False)
        ),
        "post_anatomical_self_audit": post_anatomical_audit.to_dict(
            include_frame_audit=False
        ),
        "final_self_audit": final_audit.to_dict(include_frame_audit=False),
        "final_self_audit_diagnostic": final_audit_degraded,
        "final_skeleton_contract": final_skeleton_contract.to_dict(),
        "critical_segments": [segment.to_dict() for segment in critical_segments],
        "pass3_iteration_diagnostics": pass3_results,
        "global_trajectory_optimization": global_summary,
        "hand_grip_reanalysis": grip_reanalysis_summary,
        "converged": bool(global_summary.get("converged", False)),
        "pass2_converged": pass2_converged,
        "maximum_repair_iterations": pose_v6_config.iterative.maximum_repair_iterations,
    }
    # Additive compatibility alias for consumers introduced with Pose V6.4.
    iterative_v64_summary = iterative_v65_summary
    temporal_v6_summary = summarize_temporal_frames(
        temporal_frames,
        [str(record["motion_v6"]["state"]) for record in body_records],
        joint_names=JOINT_NAMES,
        fps=fps,
    )
    fusion_records = [
        record["refinement_fusion"]
        for record in body_records
        if isinstance(record.get("refinement_fusion"), dict)
    ]
    temporal_v6_summary["hard_frame_fusion"] = {
        "candidate_frame_count": len(fusion_records),
        "frames_with_refined_joints": sum(
            int(record.get("accepted_joint_count", 0)) > 0
            for record in fusion_records
        ),
        "accepted_joint_count": sum(
            int(record.get("accepted_joint_count", 0)) for record in fusion_records
        ),
        "rejected_disagreement_count": sum(
            int(record.get("rejected_disagreement_count", 0)) for record in fusion_records
        ),
        "accepted_frame_ratio": round(
            sum(int(record.get("accepted_joint_count", 0)) > 0 for record in fusion_records)
            / max(1, len(fusion_records)),
            6,
        ),
    }
    temporal_v6_summary["offline_trajectory_refinement"] = trajectory_result.summary
    render_v6_summary = summarize_render_sources(
        render_v6_frames,
        eligible_frames=[
            str(record["tracking_state"]) not in {
                TrackingState.LOST.value,
                TrackingState.REACQUIRING.value,
            }
            and not bool(
                record["camera_motion"] is not None
                and record["camera_motion"].scene_cut
            )
            for record in body_records
        ],
    )
    high_motion_frame_indexes = [
        index for index, record in enumerate(body_records)
        if str(record["motion_v6"]["state"]) in {
            MotionState.FAST_MOTION.value,
            MotionState.EXTREME_MOTION.value,
        }
    ]
    main_bone_names = {
        "shoulders", "left_upper_arm", "left_forearm", "right_upper_arm",
        "right_forearm", "hips", "left_thigh", "left_lower_leg",
        "right_thigh", "right_lower_leg",
    }
    high_motion_main_possible = len(high_motion_frame_indexes) * len(main_bone_names)
    high_motion_main_visible = sum(
        render_v6_frames[index][name].visible
        for index in high_motion_frame_indexes
        for name in main_bone_names
        if name in render_v6_frames[index]
    )
    geometry_possible = len(high_motion_frame_indexes) * 8
    geometry_valid = sum(
        decision.accepted
        for index in high_motion_frame_indexes
        for name, decision in limb_chain_result.bone_decisions[index].items()
        if name in {
            "left_upper_arm", "left_forearm", "right_upper_arm", "right_forearm",
            "left_thigh", "left_lower_leg", "right_thigh", "right_lower_leg",
        }
    )
    wrist_possible = len(high_motion_frame_indexes) * 2
    ankle_possible = len(high_motion_frame_indexes) * 2
    wrist_valid = sum(
        temporal_frames[index].render_scores[joint] > 0.0
        for index in high_motion_frame_indexes for joint in (9, 10)
    )
    ankle_valid = sum(
        temporal_frames[index].render_scores[joint] > 0.0
        for index in high_motion_frame_indexes for joint in (15, 16)
    )
    catastrophic_rendered = sum(
        bone.visible
        and bone.bone_length_ratio_to_canonical is not None
        and bone.bone_length_ratio_to_canonical > 1.85
        for frame in render_v6_frames for bone in frame.values()
    )
    combined_repair_attempts = (
        int(high_motion_summary.get("attempted_chain_count", 0))
        + int(limb_chain_result.summary["chain_repair_attempt_count"])
    )
    combined_repair_successes = (
        int(high_motion_summary.get("accepted_chain_count", 0))
        + int(limb_chain_result.summary["chain_repair_success_count"])
    )
    high_motion_kpis = {
        **limb_chain_result.summary,
        "high_motion_frame_count": len(high_motion_frame_indexes),
        "high_motion_joint_error_count": int(
            high_motion_summary.get("high_motion_joint_error_count", 0)
        ),
        "high_motion_repair_count": int(
            high_motion_summary.get("accepted_chain_count", 0)
        ) + int(limb_chain_result.summary["high_motion_repair_count"]),
        "high_motion_repair_success_ratio": round(
            combined_repair_successes / combined_repair_attempts, 6,
        ) if combined_repair_attempts else 1.0,
        "main_skeleton_high_motion_coverage_ratio": round(
            high_motion_main_visible / high_motion_main_possible, 6,
        ) if high_motion_main_possible else 0.0,
        "high_motion_geometry_valid_ratio": round(
            geometry_valid / geometry_possible, 6,
        ) if geometry_possible else 0.0,
        "wrist_high_motion_valid_ratio": round(
            wrist_valid / wrist_possible, 6,
        ) if wrist_possible else 0.0,
        "ankle_high_motion_valid_ratio": round(
            ankle_valid / ankle_possible, 6,
        ) if ankle_possible else 0.0,
        "temporal_supersample_usage_ratio": high_motion_summary.get(
            "temporal_supersample_usage_ratio", 0.0,
        ),
        "deep_flow_usage_ratio": 0.0,
        "expert_pose_usage_ratio": 0.0,
        "catastrophic_bone_outlier_count": int(catastrophic_rendered),
        "accepted_geometry_target": {
            "catastrophic_bone_outlier_count": 0,
            "final_limb_chain_break_count": 0,
        },
    }
    render_v6_summary["high_motion_v66"] = high_motion_kpis
    temporal_v6_summary["high_motion_recovery_v66"] = high_motion_summary
    temporal_v6_summary["limb_chain_consistency_v66"] = limb_chain_result.summary
    frame_quality_values = sorted(
        float(frame.quality_score) for frame in final_audit.frames
    )
    worst_count = max(1, int(math.ceil(len(frame_quality_values) * 0.01)))
    bone_residuals = [
        abs(float(decision.bone_length_ratio_to_canonical) - 1.0)
        for frame in limb_chain_result.bone_decisions
        for decision in frame.values()
        if decision.bone_length_ratio_to_canonical is not None
        and math.isfinite(float(decision.bone_length_ratio_to_canonical))
    ]
    catastrophic_penalty = min(0.80, catastrophic_rendered * 0.35)
    chain_penalty = min(
        0.45,
        int(limb_chain_result.summary["final_limb_chain_break_count"]) * 0.08,
    )
    stale_penalty = min(
        0.20,
        int(limb_chain_result.summary["stale_endpoint_reject_count"]) * 0.01,
    )
    quality_v3 = max(
        0.0,
        float(final_audit.quality_score)
        - catastrophic_penalty
        - chain_penalty
        - stale_penalty,
    )
    quality_v3_summary = {
        "version": "pose-quality-v3",
        "quality_score": round(quality_v3, 6),
        "quality_score_is_accuracy": False,
        "worst_1_percent_frame_quality": round(
            float(np.mean(frame_quality_values[:worst_count])), 6,
        ),
        "bone_length_residual_percentile_95": round(
            float(np.percentile(bone_residuals, 95)), 6,
        ) if bone_residuals else 0.0,
        "bone_length_residual_percentile_99": round(
            float(np.percentile(bone_residuals, 99)), 6,
        ) if bone_residuals else 0.0,
        "catastrophic_penalty": round(catastrophic_penalty, 6),
        "chain_break_penalty": round(chain_penalty, 6),
        "stale_endpoint_penalty": round(stale_penalty, 6),
        "worst_case_weighted": True,
    }
    iterative_v66_summary = {
        **iterative_v65_summary,
        "version": "iterative-refinement-v3",
        "pose_final_quality_score": round(quality_v3, 6),
        "quality_v3": quality_v3_summary,
        "high_motion_recovery": high_motion_summary,
        "limb_chain_consistency": limb_chain_result.summary,
        "high_motion_kpis": high_motion_kpis,
    }
    grip_valid_coverage_ratio = round(
        (
            sum(frame.state.value != "UNKNOWN" for frame in left_grip_v4.frames)
            + sum(frame.state.value != "UNKNOWN" for frame in right_grip_v4.frames)
        ) / max(1, 2 * processed_frames),
        6,
    )
    overlay_label_count = sum(int(item.get("overlay_label_count", 0)) for item in overlay_diagnostics_records)
    overlay_label_overlap_count = sum(
        int(item.get("overlay_label_overlap_count", 0)) for item in overlay_diagnostics_records
    )
    overlay_readability_score = round(
        float(np.mean([
            float(item.get("overlay_label_readability_score", 1.0))
            for item in overlay_diagnostics_records
        ])) if overlay_diagnostics_records else 1.0,
        6,
    )
    overlay_main_metric_visibility_ratio = round(
        float(np.mean([
            float(item.get("overlay_main_metric_visibility_ratio", 1.0))
            for item in overlay_diagnostics_records
        ])) if overlay_diagnostics_records else 1.0,
        6,
    )
    coalesced_layer_contracts = coalesce_short_timeline_gaps([
        frame["timeline_v6"]["layers"]
        for frame in frames_data
        if isinstance(frame.get("timeline_v6"), dict)
    ])
    for frame, layers in zip(frames_data, coalesced_layer_contracts):
        frame["timeline_v6"]["layers"] = layers
    timeline_v6_summary = summarize_layer_coverage(
        coalesced_layer_contracts,
        fps=fps,
    )
    temporal_worst_frames = rank_temporal_worst_frames(body_records, limit=30)
    runtime_breakdown = {
        "pass1_ms": round(1000.0 * pass1_seconds, 3),
        "pass2_ms": round(1000.0 * pass2_seconds, 3),
        "pass3_ms": round(1000.0 * pass3_seconds, 3),
        "high_motion_pass_ms": round(1000.0 * high_motion_seconds, 3),
        "expert_pass_ms": round(1000.0 * expert_pass_seconds, 3),
        "global_optimization_ms": round(1000.0 * global_optimization_seconds, 3),
        "person_detection_ms": round(1000.0 * sum(
            float(record["timing_seconds"]["detector"])
            for record in body_records
        ), 3),
        "body_pose_ms": round(1000.0 * sum(
            float(record["timing_seconds"]["pose"])
            for record in body_records
        ), 3),
        "track_conditioned_pose_recovery_ms": round(1000.0 * sum(
            float(record["timing_seconds"]["pose_recovery"])
            for record in body_records
        ), 3),
        "hand_ms": round(1000.0 * (sum(
            float(record["timing_seconds"]["hands"])
            for record in body_records
        ) + hand_validation_seconds + grip_reanalysis_seconds), 3),
        "object_logic_ms": round(1000.0 * hand_object_seconds, 3),
        "validation_ms": round(1000.0 * validation_seconds, 3),
        "smoothing_ms": round(1000.0 * smoothing_seconds, 3),
        "render_ms": round(1000.0 * drawing_seconds, 3),
        "encode_ms": round(1000.0 * encoding_seconds, 3),
        "total_ms": round(1000.0 * (time.perf_counter() - processing_started_at), 3),
    }

    result_document = {
        "schema_version": POSE_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "generated_by": f"Ergonomia AI Worker {WORKER_VERSION}",
        "worker_version": WORKER_VERSION,
        "pipeline_version": QUALITY_VERSION,
        "pose_version": POSE_VERSION,
        "pose_schema_version": POSE_SCHEMA_VERSION,
        "quality_version": QUALITY_VERSION,
        "pose_model": (
            "COCO YOLOX-X + RTMW Wholebody performance "
            "+ MediaPipe Hand Landmarker full"
        ),
        "detector_model": "YOLOX-X COCO multiclass person",
        "hand_model": "MediaPipe Hand Landmarker full float16",
        "models": {
            "body_detector": "YOLOX-X COCO multiclass",
            "pose_model": "RTMW WholeBody performance 384x288",
            "hand_model": "MediaPipe Hand Landmarker full float16",
        },
        "keypoint_format": {
            "body": "coco-wholebody-133",
            "hands": "mediapipe-hand-21",
        },
        "coordinate_space": "source-video-pixels",
        "primary_person_only": True,
        "strict_bbox_required": True,
        "strict_bbox_scope": "initial-acquisition-and-bounded-track-recovery",
        "track_conditioned_pose_recovery": True,
        "data_contract": {
            "raw": "unmodified-model-observations",
            "analysis": "validated-measurements-and-explicit-safe-reconstruction",
            "render": "persistent-motion-aware-visualization",
            "predictions_are_measurements": False,
            "missing_values_are_carried_forward": False,
            "render_only_is_analysis_usable": False,
            "final_skeleton_is_immutable": True,
            "final_fusion_coordinate_space": "ORIGINAL_PIXELS",
            "atomic_bone_endpoint_contract": "atomic-bone-endpoint-v1",
            "temporal_supersamples_are_measurements": False,
            "point_sources": [source.value for source in PointSource],
            "timeline_states": [
                "MEASURED", "REFINED_MODEL", "TEMPORALLY_RECONSTRUCTED",
                "FLOW_TRACKED", "KINEMATICALLY_INFERRED",
                "LOW_CONFIDENCE_BUT_USABLE", "NOT_VISIBLE", "NO_DATA",
            ],
        },
        "source": {
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "frame_count": int(
                analysis.get("source_frame_count") or 0
            ),
            "duration_seconds": float(
                analysis.get("source_duration_seconds") or 0
            ),
            "native_frame_timeline": timeline.to_dict(),
        },
        "active_segment": {
            "source_start_frame": active_segment.start_frame,
            "source_end_frame": active_segment.end_frame,
            "source_start_seconds": active_segment.start_seconds,
            "source_end_seconds": active_segment.end_seconds,
            "output_duration_seconds": active_segment.duration_seconds,
            "output_frame_count": processed_frames,
            "scan_stride": active_segment.scan_stride,
            "scan_presence_ratio": active_segment.scan_presence_ratio,
            "selection_mode": "multiple-active-segments-envelope",
            "segments": [
                {
                    "source_start_frame": segment.start_frame,
                    "source_end_frame": segment.end_frame,
                    "source_start_seconds": segment.start_seconds,
                    "source_end_seconds": segment.end_seconds,
                    "frame_count": segment.frame_count,
                }
                for segment in active_segment.segments
            ],
        },
        "coverage": {
            "source_frame_count": int(analysis.get("source_frame_count") or 0),
            "processed_frame_count": processed_frames,
            "processing_coverage_ratio": round(
                processed_frames
                / max(1, int(analysis.get("source_frame_count") or processed_frames)),
                6,
            ),
            "pose_presence_ratio": round(presence_ratio, 6),
            "measurement_coverage_ratio": temporal_v6_summary[
                "measurement_coverage_ratio"
            ],
            "analysis_usable_coverage_ratio": temporal_v6_summary[
                "analysis_usable_coverage_ratio"
            ],
            "render_bone_coverage_ratio": render_v6_summary[
                "render_bone_coverage_ratio"
            ],
            "render_skeleton_coverage_ratio": render_v6_summary[
                "render_skeleton_coverage_ratio"
            ],
            "main_skeleton_render_coverage_ratio": render_v6_summary[
                "main_skeleton_render_coverage_ratio"
            ],
            "main_skeleton_high_motion_coverage_ratio": high_motion_kpis[
                "main_skeleton_high_motion_coverage_ratio"
            ],
            "high_motion_geometry_valid_ratio": high_motion_kpis[
                "high_motion_geometry_valid_ratio"
            ],
            "angle_usable_coverage_ratio": angle_v2.summary[
                "angle_usable_coverage_ratio"
            ],
            "grip_valid_coverage_ratio": grip_valid_coverage_ratio,
            "overlay_label_count": overlay_label_count,
            "overlay_label_overlap_count": overlay_label_overlap_count,
            "overlay_label_readability_score": overlay_readability_score,
            "overlay_main_metric_visibility_ratio": overlay_main_metric_visibility_ratio,
            "left_hand_grip_coverage_ratio": left_grip_v4.summary[
                "valid_coverage_ratio"
            ],
            "right_hand_grip_coverage_ratio": right_grip_v4.summary[
                "valid_coverage_ratio"
            ],
            "timeline_v6": timeline_v6_summary,
            "first_processed_source_timestamp_seconds": round(
                float(body_records[0]["source_timestamp_seconds"]), 6
            ),
            "last_processed_source_timestamp_seconds": round(
                float(body_records[-1]["source_timestamp_seconds"]), 6
            ),
        },
        "configuration": {
            "model_mode": settings.model_mode,
            "inference_stride": 1,
            "detector_score_threshold": settings.detector_score_threshold,
            "detector_nms_threshold": settings.detector_nms_threshold,
            "keypoint_threshold": settings.keypoint_threshold,
            "body_presence_threshold": settings.body_presence_threshold,
            "body_min_keypoints": settings.body_min_keypoints,
            "scan_min_quality": settings.scan_min_quality,
            "tracking_method": TRACKING_METHOD,
            "hand_tracking_method": HAND_TRACKING_METHOD,
            "smoothing_method": SMOOTHING_METHOD,
            "hand_validation": {
                "min_lock_frames": settings.hand_min_lock_frames,
                "max_interpolation_gap_frames": (
                    settings.hand_max_interpolation_gap_frames
                ),
                "max_root_wrist_distance_ratio": (
                    settings.hand_max_root_wrist_distance_ratio
                ),
                "max_joint_velocity_palm_ratio": (
                    settings.hand_max_joint_velocity_palm_ratio
                ),
                "max_median_joint_velocity_palm_ratio": (
                    settings.hand_max_median_joint_velocity_palm_ratio
                ),
                "bone_log_tolerance": settings.hand_bone_log_tolerance,
                "max_bone_outliers": settings.hand_max_bone_outliers,
                "reacquire_confirm_frames": settings.hand_reacquire_confirm_frames,
            },
            "body_validation": {
                "reacquire_confirm_frames": settings.body_reacquire_confirm_frames,
                "lost_after_missing_frames": settings.body_lost_after_missing_frames,
                "edge_margin_ratio": settings.body_edge_margin_ratio,
                "max_joint_velocity_bbox_ratio": (
                    settings.body_max_joint_velocity_bbox_ratio
                ),
                "max_joint_acceleration_bbox_ratio": (
                    settings.body_max_joint_acceleration_bbox_ratio
                ),
                "bone_log_tolerance": settings.body_bone_log_tolerance,
                "max_interpolation_gap_frames": (
                    settings.body_max_interpolation_gap_frames
                ),
                "max_prediction_frames": settings.body_max_prediction_frames,
                "max_scale_change_ratio": settings.body_scale_max_change_ratio,
                "prediction_is_diagnostic_only": True,
            },
            "hand_graph": {
                "adaptive_roi_enabled": settings.hand_use_adaptive_roi,
                "global_assignment": "two-by-two-cost-with-hysteresis",
                "palm_frame_enabled": True,
                "finger_chain_validation_enabled": True,
                "fallback_to_rtmw_rejected_fingers": False,
                "hand_pipeline_available": hand_failure_count < processed_frames,
            },
            "object_association_available": object_association_available,
            "holding": {
                "enabled": settings.holding_enabled,
                "minimum_confirmation_seconds": (
                    settings.holding_min_confirmation_seconds
                ),
                "release_confirmation_seconds": (
                    settings.holding_release_confirmation_seconds
                ),
                "maximum_unknown_gap_seconds": (
                    settings.holding_max_unknown_gap_seconds
                ),
                "force_estimation_enabled": False,
                "weight_estimation_enabled": False,
                "enter_threshold": settings.holding_enter_threshold,
                "keep_threshold": settings.holding_keep_threshold,
                "exit_threshold": settings.holding_exit_threshold,
                "minimum_static_seconds": settings.holding_min_static_seconds,
            },
            "render": {
                "quality_threshold": settings.render_quality_threshold,
                "fade_frames": settings.render_fade_frames,
                "draw_angles": settings.draw_angles,
                "draw_objects": settings.draw_objects,
                "geometric_severity_is_normative_risk": False,
            },
            "pose_v6": {
                "profile": pose_v6_config.profile,
                "track_conditioned_rtmw_recovery": True,
                "track_recovery_seconds": pose_v6_config.temporal.track_recovery_seconds,
                "hard_lost_seconds": pose_v6_config.temporal.hard_lost_seconds,
                "analysis_interpolation_seconds": pose_v6_config.temporal.analysis_interpolation_seconds,
                "render_persistence_seconds": pose_v6_config.temporal.render_persistence_seconds,
                "flow_enabled": pose_v6_config.optical_flow.enabled,
                "flow_max_error": pose_v6_config.optical_flow.maximum_forward_backward_error,
                "recovery_roi_scale": pose_v6_config.recovery_roi_scale,
                "hard_frame_fusion": "per-joint-confidence-and-disagreement-gated",
                "timeline_contract": "pose-timeline-coverage-v1",
                "anatomical_projection": "canonical-normalized-constrained-chain-v1",
                "angle_engine": "angle-engine-v3.0",
                "grip_engine": "grip-v5.0",
                "coordinate_space_contract": "pose-coordinate-space-v1",
                "atomic_endpoint_contract": "atomic-bone-endpoint-v1",
                "final_chain_consistency": "limb-chain-consistency-v1",
                "native_frame_timeline": timeline.to_dict(),
                "high_motion": {
                    "enabled": pose_v6_config.high_motion.enabled,
                    "temporal_supersampling_factor": (
                        pose_v6_config.high_motion.temporal_supersampling_factor
                    ),
                    "temporal_support_is_measurement": False,
                    "limb_crop_scales": list(
                        pose_v6_config.high_motion.limb_crop_scales
                    ),
                    "maximum_rtmw_batch_size": (
                        pose_v6_config.high_motion.maximum_rtmw_batch_size
                    ),
                    "maximum_endpoint_age_delta_seconds": (
                        pose_v6_config.high_motion
                        .maximum_endpoint_age_delta_seconds
                    ),
                    "motion_blur_awareness": True,
                    "directional_motion_gate": True,
                    "deep_flow_enabled": False,
                    "deep_flow_reason": (
                        "no repository-configured RAFT/GMFlow weights or "
                        "validated backend; pyramidal LK cycle check remains active"
                    ),
                },
                "iterative_refinement": {
                    "enabled": pose_v6_config.iterative.enabled,
                    "pass2_maximum_ratio": pose_v6_config.iterative.pass2_maximum_ratio,
                    "pass3_critical_ratio": pose_v6_config.iterative.pass3_critical_ratio,
                    "expert_resolution_ratio": pose_v6_config.iterative.expert_resolution_ratio,
                    "critical_temporal_context_seconds": pose_v6_config.iterative.critical_temporal_context_seconds,
                    "maximum_repair_iterations": pose_v6_config.iterative.maximum_repair_iterations,
                    "convergence_epsilon": pose_v6_config.iterative.convergence_epsilon,
                    "minimum_quality_gain": pose_v6_config.iterative.minimum_quality_gain,
                    "pass2_roi_scales": list(pose_v6_config.iterative.pass2_roi_scales),
                    "pass3_roi_scales": list(pose_v6_config.iterative.pass3_roi_scales),
                    "expert_roi_scales": list(pose_v6_config.iterative.expert_roi_scales),
                    "expert_model_enabled": False,
                    "expert_model_assessment": [
                        candidate.to_dict() for candidate in expert_candidates
                    ],
                    "expert_model_evaluation_v66": list(expert_model_evaluation),
                    "rtmw_hard_frame_batching": "multi-bbox-single-call",
                    "inference_device": "cuda",
                },
            },
            "draw_hands": settings.draw_hands,
            "draw_face": settings.draw_face,
            "debug_overlay": settings.debug_overlay,
        },
        "summary": {
            "processed_frames": processed_frames,
            "detected_frames": detected_frames,
            "presence_ratio": round(presence_ratio, 6),
            "average_body_confidence": round(
                average_confidence,
                6,
            ),
            "left_hand": serialize_hand_summary(
                left_hand_result.summary
            ),
            "right_hand": serialize_hand_summary(
                right_hand_result.summary
            ),
            "tracking": {
                "track_loss_count": tracker.track_loss_count,
                "reacquisition_count": tracker.reacquisition_count,
                "losses": tracker.track_loss_count,
                "reacquisitions": tracker.reacquisition_count,
                "recovery_attempts": sum(
                    bool(record["recovery_attempted"])
                    for record in body_records
                ),
                "recovery_successes": sum(
                    record["bbox_source"] == BBoxSource.TRACK_PREDICTED.value
                    for record in body_records
                ),
                "detector_miss_while_track_locked_count": sum(
                    not bool(record["raw_person_detected"])
                    and bool(record["track_started"])
                    and str(record["tracking_state"]) not in {
                        TrackingState.LOST.value,
                        TrackingState.REACQUIRING.value,
                    }
                    for record in body_records
                ),
                "person_switches": None,
                "person_switch_measurement_available": False,
                "partial_frames": partial_frames,
                "occluded_frames": occluded_frames,
                "final_state": tracker.state.value,
                "out_of_frame_ratio": round(
                    out_of_frame_frames / processed_frames, 6
                ),
                "partial_ratio": round(partial_frames / processed_frames, 6),
                "occluded_ratio": round(occluded_frames / processed_frames, 6),
                "valid_body_frame_ratio": round(presence_ratio, 6),
                "mean_pose_quality": round(mean_pose_quality, 6),
                "invalid_bone_count": invalid_bone_count,
                "hand_assignment_switches": hand_assignment_memory.assignment_switches,
                "body_proportion_profile": pose_graph.bone_profile.to_dict(),
            },
            "body": pose_graph_summary,
            "hands": {
                "left": serialize_hand_summary(left_hand_result.summary),
                "right": serialize_hand_summary(right_hand_result.summary),
                "assignment_switches": hand_assignment_memory.assignment_switches,
                "finger_rejections": finger_rejections,
                "rescue": hand_rescue_summary,
                "grip_v4": {
                    "left": left_grip_v4.summary,
                    "right": right_grip_v4.summary,
                    "grip_valid_coverage_ratio": grip_valid_coverage_ratio,
                },
                "grip_v5": {
                    "left": left_grip_v4.summary,
                    "right": right_grip_v4.summary,
                    "grip_valid_coverage_ratio": grip_valid_coverage_ratio,
                },
            },
            "regional_quality": region_quality_coverage(frames_data, fps=fps),
            "quality": quality_summary,
            "quality_v3": quality_v3_summary,
            "high_motion_v66": high_motion_kpis,
            "holding": {
                "version": "holding-v3",
                "left": {
                    **serialize_holding_summary_v2(left_holding_summary),
                    **_summarize_holding_v3(left_holding_v3, holding_durations),
                },
                "right": {
                    **serialize_holding_summary_v2(right_holding_summary),
                    **_summarize_holding_v3(right_holding_v3, holding_durations),
                },
                "bimanual": {
                    "observation_known": bimanual_observation_seconds > 0.0,
                    "valid_observation_seconds": round(bimanual_observation_seconds, 6),
                    "likely_holding_seconds": (
                        round(sum(duration for duration, flag in zip(holding_durations, bimanual_holding_v3_flags) if flag), 6)
                        if bimanual_observation_seconds > 0.0
                        else None
                    ),
                    "episode_count": (
                        sum(flag and (index == 0 or not bimanual_holding_v3_flags[index - 1]) for index, flag in enumerate(bimanual_holding_v3_flags))
                        if bimanual_observation_seconds > 0.0
                        else None
                    ),
                },
                "external_load_known": False,
            },
            "movement": movement_summary,
            "precision_v62": {
                **anatomical_result.summary,
                **angle_v2.summary,
                "main_skeleton_render_coverage_ratio": render_v6_summary[
                    "main_skeleton_render_coverage_ratio"
                ],
                "single_frame_bone_flicker_count": render_v6_summary[
                    "single_frame_bone_flicker_count"
                ],
                "grip_valid_coverage_ratio": grip_valid_coverage_ratio,
                "left_hand_grip_coverage_ratio": left_grip_v4.summary[
                    "valid_coverage_ratio"
                ],
                "right_hand_grip_coverage_ratio": right_grip_v4.summary[
                    "valid_coverage_ratio"
                ],
            },
            "iterative_v64": iterative_v64_summary,
            "iterative_v65": iterative_v65_summary,
            "iterative_v66": iterative_v66_summary,
            "temporal_v6": temporal_v6_summary,
            "render_v6": render_v6_summary,
            "timeline_v6": timeline_v6_summary,
            "runtime_breakdown": runtime_breakdown,
        },
        "frames": frames_data,
    }

    result_document = augment_pose_document_v5(
        result_document,
        config=pose_v5_config,
        refinement_results=refinement_results,
    )
    result_document = augment_pose_document_v6(
        result_document,
        config=pose_v6_config,
        temporal_summary=temporal_v6_summary,
        render_summary=render_v6_summary,
    )

    try:
        write_pose_document(
            output_json_path,
            result_document,
            document_name="pose-keypoints",
        )
    except PoseOutputSerializationError as error:
        logger.error(
            "%s document=%s path=%s type=%s value=%s",
            error.error_code,
            error.document_name,
            error.path,
            error.python_type,
            error.value_preview,
        )
        raise

    worst_tracking_frames = [
        index
        for index, record in enumerate(body_records)
        if record["tracking_state"]
        in {TrackingState.LOST.value, TrackingState.REACQUIRING.value}
    ][:10]
    bone_outlier_scores = [
        max(
            (
                abs(bone.length_error)
                for bone in frame.bones.values()
                if bone.length_error is not None
            ),
            default=0.0,
        )
        for frame in pose_graph_frames
    ]
    worst_bone_outliers = sorted(
        (
            index
            for index, value in enumerate(bone_outlier_scores)
            if value > 0.0
        ),
        key=lambda index: bone_outlier_scores[index],
        reverse=True,
    )[:10]
    worst_hand_frames = sorted(
        range(len(left_hand_graph)),
        key=lambda index: min(
            left_hand_graph[index].quality,
            right_hand_graph[index].quality,
        ),
    )[:10]
    holding_transition_frames = [
        index
        for index in range(1, len(left_holding_frames))
        if (
            left_holding_frames[index].state
            != left_holding_frames[index - 1].state
            or right_holding_frames[index].state
            != right_holding_frames[index - 1].state
        )
    ]
    worst_quality_frames = sorted(
        range(len(frame_quality_objects)),
        key=lambda index: frame_quality_objects[index].score,
    )[:10]
    qa_frame_indices = list(
        dict.fromkeys(
            [
                *worst_tracking_frames,
                *worst_bone_outliers,
                *worst_hand_frames,
                *holding_transition_frames,
                *worst_quality_frames,
                *[int(item["frame_index"]) for item in temporal_worst_frames],
            ]
        )
    )[:30]

    diagnostics_document = {
        "schema_version": "4.0",
        "worker_version": WORKER_VERSION,
        "pipeline_version": QUALITY_VERSION,
        "pose_version": POSE_VERSION,
        "pose_schema_version": POSE_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "runtime_seconds": round(time.perf_counter() - processing_started_at, 4),
        "runtime_breakdown_seconds": runtime_breakdown,
        "iterative_v64": iterative_v64_summary,
        "iterative_v65": iterative_v65_summary,
        "iterative_v66": iterative_v66_summary,
        "tracking": result_document["summary"]["tracking"],
        "scene_cut_count": scene_cut_count,
        "refinement": result_document["refinement"],
        "regional_quality": region_quality_coverage(result_document["frames"], fps=fps),
        "body": pose_graph_summary,
        "quality": quality_summary,
        "quality_v3": quality_v3_summary,
        "high_motion_v66": {
            "recovery": high_motion_summary,
            "kpis": high_motion_kpis,
            "limb_chain_consistency": limb_chain_result.summary,
        },
        "native_frame_timeline": timeline.to_dict(),
        "video": {
            "mean_blur_quality": round(
                float(np.mean([
                    frame.components["blur"] for frame in frame_quality_objects
                ])),
                6,
            ),
            "mean_exposure_quality": round(
                float(np.mean([
                    frame.components["exposure"] for frame in frame_quality_objects
                ])),
                6,
            ),
            "out_of_frame_ratio": round(out_of_frame_frames / processed_frames, 6),
        },
        "hands": {
            "left": serialize_hand_summary(left_hand_result.summary),
            "right": serialize_hand_summary(right_hand_result.summary),
            "inference_failure_count": hand_failure_count,
            "inference_failure_types": hand_failure_types,
            "assignment_switches": hand_assignment_memory.assignment_switches,
            "finger_rejections": finger_rejections,
        },
        "holding": result_document["summary"]["holding"],
        "movement": movement_summary,
        "temporal_v6": temporal_v6_summary,
        "render": {
            **render_v6_summary,
            "safety_rejections": sum(
                int(item["safety_rejections"])
                for item in overlay_diagnostics_records
            ),
            "maximum_rendered_length": max(
                (
                    float(item["maximum_rendered_length"])
                    for item in overlay_diagnostics_records
                ),
                default=0.0,
            ),
        },
        "rejections": {
            "invalid_bones": invalid_bone_count,
            "left_hand": left_hand_result.summary.reject_reason_counts,
            "right_hand": right_hand_result.summary.reject_reason_counts,
        },
        "worst_frame_indices": qa_frame_indices,
        "worst_tracking_frames": worst_tracking_frames,
        "worst_bone_outlier_frames": worst_bone_outliers,
        "worst_hand_frames": worst_hand_frames,
        "holding_transition_frames": holding_transition_frames[:10],
        "temporal_worst_frames": temporal_worst_frames,
    }
    try:
        write_pose_document(
            diagnostics_path,
            diagnostics_document,
            document_name="pose-diagnostics",
            pretty=True,
        )
    except PoseOutputSerializationError as error:
        logger.error(
            "%s document=%s path=%s type=%s value=%s",
            error.error_code,
            error.document_name,
            error.path,
            error.python_type,
            error.value_preview,
        )
        raise

    logger.info(
        "Pose V6 zakończone: frames_total=%d body_valid_ratio=%.3f "
        "left_hand_valid_ratio=%.3f right_hand_valid_ratio=%.3f "
        "track_losses=%d reacquisitions=%d holding_left_seconds=%.3f "
        "holding_right_seconds=%.3f bimanual_seconds=%.3f render_coverage=%.3f runtime=%.2fs.",
        processed_frames,
        presence_ratio,
        left_hand_result.summary.valid_ratio,
        right_hand_result.summary.valid_ratio,
        tracker.track_loss_count,
        tracker.reacquisition_count,
        left_holding_summary.likely_holding_seconds,
        right_holding_summary.likely_holding_seconds,
        bimanual_holding["likely_holding_seconds"],
        float(render_v6_summary["render_bone_coverage_ratio"]),
        time.perf_counter() - processing_started_at,
    )
    if hand_failure_count:
        logger.warning(
            "Hand pipeline: pominięto %d klatek; typy=%s.",
            hand_failure_count,
            hand_failure_types,
        )

    return PoseProcessingResult(
        video_path=output_video_path,
        json_path=output_json_path,
        thumbnail_path=thumbnail_path,
        diagnostics_path=diagnostics_path,
        processed_frames=processed_frames,
        detected_frames=detected_frames,
        average_confidence=average_confidence,
        presence_ratio=presence_ratio,
        active_segment=active_segment,
        left_hand_summary=left_hand_result.summary,
        right_hand_summary=right_hand_result.summary,
    )

def upload_result_file(
    supabase: Client,
    bucket_name: str,
    local_path: Path,
    storage_path: str,
    content_type: str,
) -> None:
    with local_path.open("rb") as file_handle:
        supabase.storage.from_(bucket_name).upload(
            path=storage_path,
            file=file_handle,
            file_options={
                "content-type": content_type,
                "cache-control": "3600",
                "upsert": "true",
            },
        )


def upload_pose_results(
    supabase: Client,
    settings: PoseWorkerSettings,
    analysis: dict[str, Any],
    result: PoseProcessingResult,
    logger: logging.Logger,
) -> tuple[str, str, str]:
    user_id = str(analysis["user_id"])
    analysis_id = str(analysis["id"])
    base_path = f"{user_id}/{analysis_id}/results"

    video_storage_path = f"{base_path}/pose-overlay.mp4"
    json_storage_path = f"{base_path}/pose-keypoints.json"
    thumbnail_storage_path = f"{base_path}/pose-thumbnail.jpg"
    diagnostics_storage_path = f"{base_path}/pose-diagnostics.json"

    upload_result_file(
        supabase,
        settings.results_bucket,
        result.video_path,
        video_storage_path,
        "video/mp4",
    )
    json_size_bytes = result.json_path.stat().st_size
    logger.info(
        "Pose JSON przed uploadem: bytes=%d MB=%.3f path=%s",
        json_size_bytes,
        json_size_bytes / (1024 * 1024),
        result.json_path,
    )
    compressed_json = compress_json_artifact(result.json_path, json_storage_path)
    logger.info(
        "Pose JSON po gzip: bytes=%d MB=%.3f path=%s storage_path=%s",
        compressed_json.compressed_size_bytes,
        compressed_json.compressed_size_bytes / (1024 * 1024),
        compressed_json.compressed_path,
        compressed_json.storage_path,
    )
    try:
        upload_compressed_json(
            supabase.storage.from_(settings.results_bucket),
            compressed_json,
        )
    except Exception:
        logger.exception(
            "Upload skompresowanego Pose JSON nie powiódł się: "
            "source_bytes=%d gzip_bytes=%d path=%s storage_path=%s. "
            "Lokalne artefakty zostają zachowane.",
            compressed_json.source_size_bytes,
            compressed_json.compressed_size_bytes,
            compressed_json.compressed_path,
            compressed_json.storage_path,
        )
        raise
    json_storage_path = compressed_json.storage_path
    diagnostics_size_bytes = result.diagnostics_path.stat().st_size
    logger.info(
        "Pose diagnostics przed uploadem: bytes=%d MB=%.3f path=%s",
        diagnostics_size_bytes,
        diagnostics_size_bytes / (1024 * 1024),
        result.diagnostics_path,
    )
    upload_result_file(
        supabase,
        settings.results_bucket,
        result.thumbnail_path,
        thumbnail_storage_path,
        "image/jpeg",
    )
    upload_result_file(
        supabase,
        settings.results_bucket,
        result.diagnostics_path,
        diagnostics_storage_path,
        "application/json",
    )

    return video_storage_path, json_storage_path, thumbnail_storage_path



def complete_pose_inference_v3(
    supabase: Client,
    settings: PoseWorkerSettings,
    analysis: dict[str, Any],
    result: PoseProcessingResult,
    video_storage_path: str,
    json_storage_path: str,
    thumbnail_storage_path: str,
) -> None:
    segment = result.active_segment

    response = supabase.rpc(
        "complete_pose_inference_v3",
        {
            "p_analysis_id": str(analysis["id"]),
            "p_worker_id": settings.worker_id,
            "p_result_video_path": video_storage_path,
            "p_result_json_path": json_storage_path,
            "p_thumbnail_path": thumbnail_storage_path,
            "p_pose_model": (
                "COCO YOLOX-X + RTMW Wholebody performance "
                "+ MediaPipe Hand Landmarker full"
            ),
            "p_sample_stride": 1,
            "p_processed_frames": result.processed_frames,
            "p_detected_frames": result.detected_frames,
            "p_average_confidence": round(
                result.average_confidence,
                6,
            ),
            "p_active_start_frame": segment.start_frame,
            "p_active_end_frame": segment.end_frame,
            "p_active_start_seconds": segment.start_seconds,
            "p_active_end_seconds": segment.end_seconds,
            "p_active_duration_seconds": segment.duration_seconds,
            "p_presence_ratio": round(result.presence_ratio, 6),
            "p_tracking_method": TRACKING_METHOD,
            "p_smoothing_method": SMOOTHING_METHOD,
            "p_quality_version": QUALITY_VERSION,
            "p_hand_model": "MediaPipe Hand Landmarker full float16",
            "p_left_hand_valid_ratio": round(
                result.left_hand_summary.valid_ratio,
                6,
            ),
            "p_right_hand_valid_ratio": round(
                result.right_hand_summary.valid_ratio,
                6,
            ),
            "p_left_hand_rejected_frames": (
                result.left_hand_summary.rejected_frames
            ),
            "p_right_hand_rejected_frames": (
                result.right_hand_summary.rejected_frames
            ),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Nie udało się zakończyć etapu estymacji pozy V4."
        )

def process_analysis(
    supabase: Client,
    settings: PoseWorkerSettings,
    model: StrictWholebodyModel,
    analysis: dict[str, Any],
    logger: logging.Logger,
) -> None:
    analysis_id = str(
        analysis["id"]
    )
    job_directory = (
        DATA_DIRECTORY / analysis_id
    )
    job_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    preserve_job_directory = False

    logger.info(
        "Rozpoczynam Pose Pipeline V6 / Worker %s: %s — %s",
        WORKER_VERSION,
        analysis_id,
        analysis.get("title"),
    )

    try:
        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            21,
            "downloading-for-pose-v6",
        )

        video_path = download_source_video(
            supabase,
            settings,
            analysis,
            job_directory,
        )

        active_segment = scan_active_segment(
            supabase,
            settings,
            model,
            analysis_id,
            video_path,
            logger,
        )

        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            30,
            "pose-inference-active-segment-v6",
        )

        hand_engine = MediaPipeHandEngine(
            create_hand_pipeline_config(settings)
        )

        try:
            result = process_pose_video(
                supabase,
                settings,
                model,
                hand_engine,
                analysis,
            video_path,
            job_directory,
                active_segment,
                logger,
            )
        finally:
            hand_engine.close()

        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            91,
            "uploading-pose-results-v6",
        )

        try:
            (
                video_storage_path,
                json_storage_path,
                thumbnail_storage_path,
            ) = upload_pose_results(
                supabase,
                settings,
                analysis,
                result,
                logger,
            )
        except Exception:
            preserve_job_directory = True
            raise

        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            97,
            "saving-pose-results-v6",
        )

        complete_pose_inference_v3(
            supabase,
            settings,
            analysis,
            result,
            video_storage_path,
            json_storage_path,
            thumbnail_storage_path,
        )

        logger.info(
            "Analiza %s gotowa do obliczeń ergonomicznych. "
            "Wynik przycięto do %.3f s.",
            analysis_id,
            active_segment.duration_seconds,
        )
    except Exception as error:
        logger.exception(
            "Błąd Pose Pipeline V6 dla analizy %s.",
            analysis_id,
        )

        try:
            mark_analysis_failed(
                supabase,
                analysis_id,
                settings.worker_id,
                error,
            )
        except Exception:
            logger.exception(
                "Nie udało się zapisać błędu analizy %s.",
                analysis_id,
            )

        raise
    finally:
        if (
            job_directory.exists()
            and not settings.keep_worker_files
            and not preserve_job_directory
        ):
            shutil.rmtree(
                job_directory,
                ignore_errors=True,
            )
            logger.info(
                "Usunięto lokalne pliki analizy %s.",
                analysis_id,
            )


def run_worker(settings: PoseWorkerSettings, once: bool) -> int:
    logger = configure_logging()
    supabase = create_supabase_client(settings)
    model = initialize_pose_model(settings, logger)

    while True:
        try:
            analysis = claim_next_pose_analysis(supabase, settings.worker_id)

            if analysis is None:
                logger.info("Brak analiz gotowych do Pose Pipeline V6.")

                if once:
                    return 0

                time.sleep(settings.poll_interval_seconds)
                continue

            process_analysis(
                supabase,
                settings,
                model,
                analysis,
                logger,
            )

            if once:
                return 0
        except KeyboardInterrupt:
            logger.info("Worker został zatrzymany.")
            return 0
        except Exception:
            logger.exception("Nieobsłużony błąd cyklu Pose Pipeline V6.")

            if once:
                return 1

            time.sleep(settings.poll_interval_seconds)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Ergonomia AI Worker {WORKER_VERSION} — Pose Pipeline V6.6"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Przetwórz maksymalnie jedną analizę i zakończ działanie.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        settings = load_settings()
        return run_worker(settings, arguments.once)
    except Exception as error:
        print(f"BŁĄD KONFIGURACJI: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
