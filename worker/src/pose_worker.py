from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
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
from pose_v4 import POSE_SCHEMA_VERSION, POSE_VERSION
from pose_v4.graph import (
    BiomechanicalPoseGraph,
    PoseGraphConfig,
    apply_interpolation_metadata,
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

WORKER_VERSION = "0.4.0-beta.1"
QUALITY_VERSION = POSE_VERSION
TRACKING_METHOD = (
    "coco-yolox-biomechanical-identity-state-machine-v5"
)
HAND_TRACKING_METHOD = (
    "mediapipe-adaptive-roi-global-assignment-hand-graph-v3"
)
SMOOTHING_METHOD = "offline-bidirectional-body-v3+offline-hand-v3"

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
class ActiveSegment:
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    scan_stride: int
    scan_presence_ratio: float

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
            "Pose Pipeline V4 korzysta z modelu performance. "
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


def configure_logging() -> logging.Logger:
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
            "p_error_code": type(error).__name__.upper()[:100],
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
    4. Brak bounding boxa zwraca pusty wynik i nie uruchamia RTMW.
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

    def __call__(
        self,
        frame: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        frame_height, frame_width = frame.shape[:2]
        self.last_object_detections = []
        self.last_timing_seconds = {"detector": 0.0, "pose": 0.0}

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

        pose_started_at = time.perf_counter()
        keypoints, scores = self.pose_model(
            frame,
            bboxes=accepted_boxes,
        )
        self.last_timing_seconds["pose"] = time.perf_counter() - pose_started_at

        return normalize_pose_arrays(
            keypoints,
            scores,
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


def select_primary_person(
    keypoints: np.ndarray,
    scores: np.ndarray,
    frame_width: int,
    frame_height: int,
    settings: PoseWorkerSettings,
    previous_bbox: np.ndarray | None,
) -> PoseCandidate | None:
    best_candidate: PoseCandidate | None = None

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
            >= settings.body_presence_threshold
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
                >= settings.body_presence_threshold
            )
        ]
        hip_indices = [
            index
            for index in (11, 12)
            if (
                index < usable_body_count
                and body_scores[index]
                >= settings.body_presence_threshold
            )
        ]

        if not shoulder_indices or not hip_indices:
            continue

        bbox = get_body_bbox(
            person_keypoints,
            person_scores,
            settings.body_presence_threshold,
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
                        break

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

        if (
            confirmed_start_sample is None
            or last_valid_sample is None
        ):
            raise RuntimeError(
                "Nie wykryto stabilnego fragmentu "
                "z prawdziwym pracownikiem."
            )

        detected_start_frame = sample_frames[
            confirmed_start_sample
        ]
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

        logger.info(
            "Aktywny fragment V4: "
            "%.3f-%.3f s (%d-%d), "
            "długość %.3f s, jakość %.3f.",
            start_frame / fps,
            (end_frame + 1) / fps,
            start_frame,
            end_frame,
            active_duration,
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
    Pose Pipeline V4 działa dwupasowo i rozdziela RAW, ANALYSIS oraz RENDER.

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
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Film ma nieprawidłowe parametry techniczne.")

    raw_output_video_path = job_directory / "pose-overlay-raw.mp4"
    output_video_path = job_directory / "pose-overlay.mp4"
    output_json_path = job_directory / "pose-keypoints.json"
    diagnostics_path = job_directory / "pose-diagnostics.json"
    thumbnail_path = job_directory / "pose-thumbnail.jpg"

    tracker = PersonTrackingStateMachine(
        TrackingConfig(
            keypoint_threshold=settings.body_presence_threshold,
            reacquire_confirm_frames=settings.body_reacquire_confirm_frames,
            lost_after_missing_frames=settings.body_lost_after_missing_frames,
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
            maximum_prediction_frames=settings.body_max_prediction_frames,
            maximum_scale_change_ratio=settings.body_scale_max_change_ratio,
        )
    )
    hand_graph_config = HandGraphConfig()
    hand_assignment_memory = HandAssignmentMemory()

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

            inference_started_at = time.perf_counter()
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
            )
            object_detection_frames.append(list(model.last_object_detections))

            raw_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
            raw_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
            source_timestamp = source_frame_index / fps
            candidate_detected = candidate is not None

            if candidate is not None:
                usable_point_count = min(KEYPOINT_COUNT, candidate.keypoints.shape[0])
                usable_score_count = min(KEYPOINT_COUNT, candidate.scores.shape[0])
                raw_points[:usable_point_count] = candidate.keypoints[:usable_point_count]
                raw_scores[:usable_score_count] = candidate.scores[:usable_score_count]

            tracking = tracker.update(
                detected=candidate_detected,
                bbox=candidate.bbox if candidate is not None else None,
                points=raw_points,
                scores=raw_scores,
                frame_width=width,
                frame_height=height,
                candidate_quality=(candidate.selection_score if candidate is not None else 0.0),
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

                timestamp_ms = int(round(processed_frames / fps * 1000.0))
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
                    "source_timestamp_seconds": source_timestamp,
                    "output_timestamp_seconds": processed_frames / fps,
                    "detected": tracking.accept_pose,
                    "raw_person_detected": candidate_detected,
                    "track_started": track_started,
                    "track_ended": tracking.state == TrackingState.LOST,
                    "tracking_state": tracking.state.value,
                    "tracking_reasons": list(tracking.reasons),
                    "tracking_identity_score": tracking.identity_score,
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
                    "pose_graph": graph_frame,
                    "hand_union_roi": combined_hand_roi,
                    "inference_seconds": time.perf_counter() - inference_started_at,
                    "timing_seconds": {
                        "detector": model.last_timing_seconds.get("detector", 0.0),
                        "pose": model.last_timing_seconds.get("pose", 0.0),
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
                    "pose-v3-collecting-body-and-hands",
                )
    finally:
        capture.release()

    smoothing_started_at = time.perf_counter()
    smoothed_points, smoothed_scores, interpolation_masks = smooth_body_sequence(
        [record["smoothed_points"] for record in body_records],
        [record["smoothed_scores"] for record in body_records],
        [record["tracking_state"] for record in body_records],
        frame_width=width,
        frame_height=height,
        maximum_gap_frames=settings.body_max_interpolation_gap_frames,
        interpolation_allowed=[
            record["pose_graph"].interpolation_allowed()
            for record in body_records
        ],
    )
    for index, record in enumerate(body_records):
        record["smoothed_points"] = smoothed_points[index]
        record["smoothed_scores"] = smoothed_scores[index]
        record["body_interpolated"] = interpolation_masks[index]
        record["pose_graph"] = apply_interpolation_metadata(
            record["pose_graph"],
            smoothed_points[index],
            smoothed_scores[index],
            interpolation_masks[index],
        )
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
        "pose-v3-validating-hand-trajectories",
    )

    hand_validation_started_at = time.perf_counter()
    left_hand_result = stabilize_hand_track(
        "left",
        raw_hand_frames["left"],
        hand_engine.config,
    )
    right_hand_result = stabilize_hand_track(
        "right",
        raw_hand_frames["right"],
        hand_engine.config,
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
    hand_validation_seconds = time.perf_counter() - hand_validation_started_at

    hand_object_started_at = time.perf_counter()
    output_timestamps = [
        float(record["output_timestamp_seconds"]) for record in body_records
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
    color_hysteresis = MetricColorHysteresis()
    overlay_palette = OverlayPalette()
    overlay_diagnostics_records: list[dict[str, object]] = []
    overlay_metric_frames: list[dict[str, dict[str, object]]] = []

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
            metric_input_frame = {
                "detected": body_record["detected"],
                "smoothed_keypoints": serialize_coordinates(
                    body_record["smoothed_points"],
                    body_record["smoothed_scores"],
                ),
                "scores": serialize_scores(body_record["smoothed_scores"]),
                "body_quality": body_record["pose_graph"].to_dict(),
                "left_hand": serialize_hand_frame(left_frame),
                "right_hand": serialize_hand_frame(right_frame),
            }
            overlay_metrics = compute_overlay_metrics_from_frame(
                metric_input_frame,
                quality_threshold=settings.keypoint_threshold,
            )
            overlay_metric_frames.append(overlay_metrics)
            bbox_value = body_record.get("bbox_xyxy")
            bbox_array = (
                np.asarray(bbox_value, dtype=np.float32)
                if isinstance(bbox_value, list) and len(bbox_value) == 4
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
            )
            overlay_diagnostics_records.append(
                {
                    "rendered_bones": overlay_diagnostics.rendered_bones,
                    "hidden_bones": overlay_diagnostics.hidden_bones,
                    "safety_rejections": overlay_diagnostics.safety_rejections,
                    "maximum_rendered_length": round(overlay_diagnostics.maximum_rendered_length, 3),
                    "severities": overlay_diagnostics.severities,
                }
            )

            output_timestamp = body_record["output_timestamp_seconds"]
            cv2.putText(
                rendered_frame,
                (
                    "Ergonomia AI Worker V0.4 | aktywny fragment "
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
                    },
                    "right_hand": {
                        **serialize_hand_frame(right_frame),
                        "pipeline_available": body_record["hand_error"] is None,
                        "graph_v2": right_hand_graph[frame_offset].to_dict(),
                        "grip": serialize_holding_frame_v2(
                            right_holding_frames[frame_offset]
                        ),
                    },
                    "holding": {
                        "left": serialize_holding_frame_v2(
                            left_holding_frames[frame_offset]
                        ),
                        "right": serialize_holding_frame_v2(
                            right_holding_frames[frame_offset]
                        ),
                        "bimanual_candidate": bool(
                            bimanual_holding["frame_flags"][frame_offset]
                        ),
                        "bimanual_association_mode": (
                            bimanual_holding["association_modes"][frame_offset]
                        ),
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
                    "pose-v3-rendering-validated-results",
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
    runtime_breakdown = {
        "person_detection_ms": round(1000.0 * sum(
            float(record["timing_seconds"]["detector"])
            for record in body_records
        ), 3),
        "body_pose_ms": round(1000.0 * sum(
            float(record["timing_seconds"]["pose"])
            for record in body_records
        ), 3),
        "hand_ms": round(1000.0 * (sum(
            float(record["timing_seconds"]["hands"])
            for record in body_records
        ) + hand_validation_seconds), 3),
        "object_logic_ms": round(1000.0 * hand_object_seconds, 3),
        "validation_ms": round(1000.0 * validation_seconds, 3),
        "smoothing_ms": round(1000.0 * smoothing_seconds, 3),
        "render_ms": round(1000.0 * drawing_seconds, 3),
        "encode_ms": round(1000.0 * encoding_seconds, 3),
    }

    result_document = {
        "schema_version": POSE_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "generated_by": "Ergonomia AI Worker V0.4",
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
        "data_contract": {
            "raw": "unmodified-model-observations",
            "analysis": "validated-measurements-only",
            "render": "quality-gated-visualization-only",
            "predictions_are_measurements": False,
            "missing_values_are_carried_forward": False,
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
            },
            "quality": quality_summary,
            "holding": {
                "version": "holding-v2",
                "left": serialize_holding_summary_v2(left_holding_summary),
                "right": serialize_holding_summary_v2(right_holding_summary),
                "bimanual": {
                    "likely_holding_seconds": bimanual_holding[
                        "likely_holding_seconds"
                    ],
                    "episode_count": bimanual_holding["episode_count"],
                },
                "external_load_known": False,
            },
            "movement": movement_summary,
            "runtime_breakdown": runtime_breakdown,
        },
        "frames": frames_data,
    }

    output_json_path.write_text(
        json.dumps(
            result_document,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

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
            ]
        )
    )[:20]

    diagnostics_document = {
        "schema_version": "2.0",
        "worker_version": WORKER_VERSION,
        "pipeline_version": QUALITY_VERSION,
        "pose_version": POSE_VERSION,
        "pose_schema_version": POSE_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "runtime_seconds": round(time.perf_counter() - processing_started_at, 4),
        "runtime_breakdown_seconds": runtime_breakdown,
        "tracking": result_document["summary"]["tracking"],
        "body": pose_graph_summary,
        "quality": quality_summary,
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
        "render": {
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
    }
    diagnostics_path.write_text(
        json.dumps(diagnostics_document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(
        "Pose V0.4 zakończone: frames_total=%d body_valid_ratio=%.3f "
        "left_hand_valid_ratio=%.3f right_hand_valid_ratio=%.3f "
        "track_losses=%d reacquisitions=%d holding_left_seconds=%.3f "
        "holding_right_seconds=%.3f bimanual_seconds=%.3f runtime=%.2fs.",
        processed_frames,
        presence_ratio,
        left_hand_result.summary.valid_ratio,
        right_hand_result.summary.valid_ratio,
        tracker.track_loss_count,
        tracker.reacquisition_count,
        left_holding_summary.likely_holding_seconds,
        right_holding_summary.likely_holding_seconds,
        bimanual_holding["likely_holding_seconds"],
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
    upload_result_file(
        supabase,
        settings.results_bucket,
        result.json_path,
        json_storage_path,
        "application/json",
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

    logger.info(
        "Rozpoczynam Pose Pipeline V4 / Worker %s: %s — %s",
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
            "downloading-for-pose-v3",
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
            "pose-inference-active-segment-v3",
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
            "uploading-pose-results-v3",
        )

        (
            video_storage_path,
            json_storage_path,
            thumbnail_storage_path,
        ) = upload_pose_results(
            supabase,
            settings,
            analysis,
            result,
        )

        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            97,
            "saving-pose-results-v3",
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
            "Błąd Pose Pipeline V4 dla analizy %s.",
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
                logger.info("Brak analiz gotowych do Pose Pipeline V4.")

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
            logger.exception("Nieobsłużony błąd cyklu Pose Pipeline V4.")

            if once:
                return 1

            time.sleep(settings.poll_interval_seconds)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ergonomia AI Worker V0.4 — Pose Pipeline V4"
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
