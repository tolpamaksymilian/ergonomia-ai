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


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "pose-jobs"
LOG_DIRECTORY = WORKER_DIRECTORY / "logs"

QUALITY_VERSION = "pose-v2.2"
TRACKING_METHOD = (
    "coco-yolox-strict-bbox-anatomy-iou-primary-person-v3"
)
SMOOTHING_METHOD = "confidence-aware-one-euro-v1"

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
    max_track_gap_frames: int

    one_euro_min_cutoff: float
    one_euro_beta: float
    one_euro_d_cutoff: float

    draw_hands: bool
    draw_face: bool
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
    processed_frames: int
    detected_frames: int
    average_confidence: float
    presence_ratio: float
    active_segment: ActiveSegment


class LowPassFilter:
    def __init__(self) -> None:
        self.initialized = False
        self.value = 0.0

    def reset(self, value: float) -> float:
        self.initialized = True
        self.value = float(value)
        return self.value

    def apply(self, value: float, alpha: float) -> float:
        if not self.initialized:
            return self.reset(value)

        self.value = alpha * float(value) + (1.0 - alpha) * self.value
        return self.value


class OneEuroFilter1D:
    def __init__(
        self,
        min_cutoff: float,
        beta: float,
        d_cutoff: float,
    ) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_filter = LowPassFilter()
        self.dx_filter = LowPassFilter()
        self.previous_raw_value: float | None = None
        self.previous_timestamp: float | None = None

    @staticmethod
    def _alpha(cutoff: float, delta_time: float) -> float:
        safe_cutoff = max(1e-4, cutoff)
        safe_delta = max(1e-4, delta_time)
        tau = 1.0 / (2.0 * math.pi * safe_cutoff)
        return 1.0 / (1.0 + tau / safe_delta)

    def reset(self, value: float, timestamp: float) -> float:
        self.previous_raw_value = float(value)
        self.previous_timestamp = float(timestamp)
        self.dx_filter.reset(0.0)
        return self.x_filter.reset(value)

    def apply(self, value: float, timestamp: float) -> float:
        if self.previous_timestamp is None or self.previous_raw_value is None:
            return self.reset(value, timestamp)

        delta_time = max(1e-4, timestamp - self.previous_timestamp)
        derivative = (float(value) - self.previous_raw_value) / delta_time

        filtered_derivative = self.dx_filter.apply(
            derivative,
            self._alpha(self.d_cutoff, delta_time),
        )

        dynamic_cutoff = self.min_cutoff + self.beta * abs(filtered_derivative)
        filtered_value = self.x_filter.apply(
            value,
            self._alpha(dynamic_cutoff, delta_time),
        )

        self.previous_raw_value = float(value)
        self.previous_timestamp = float(timestamp)
        return filtered_value


class KeypointSmoother:
    def __init__(
        self,
        threshold: float,
        max_gap_frames: int,
        min_cutoff: float,
        beta: float,
        d_cutoff: float,
    ) -> None:
        self.threshold = threshold
        self.max_gap_frames = max_gap_frames
        self.filters = [
            (
                OneEuroFilter1D(min_cutoff, beta, d_cutoff),
                OneEuroFilter1D(min_cutoff, beta, d_cutoff),
            )
            for _ in range(KEYPOINT_COUNT)
        ]
        self.last_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
        self.last_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)
        self.missing_frames = np.full(
            (KEYPOINT_COUNT,),
            max_gap_frames + 1,
            dtype=np.int32,
        )

    def update(
        self,
        points: np.ndarray,
        scores: np.ndarray,
        timestamp: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        output_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
        output_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)

        usable_count = min(KEYPOINT_COUNT, points.shape[0], scores.shape[0])

        for index in range(KEYPOINT_COUNT):
            is_valid = (
                index < usable_count
                and float(scores[index]) >= self.threshold
                and np.isfinite(points[index]).all()
            )

            if is_valid:
                x_filter, y_filter = self.filters[index]

                if self.missing_frames[index] > self.max_gap_frames:
                    filtered_x = x_filter.reset(float(points[index, 0]), timestamp)
                    filtered_y = y_filter.reset(float(points[index, 1]), timestamp)
                else:
                    filtered_x = x_filter.apply(float(points[index, 0]), timestamp)
                    filtered_y = y_filter.apply(float(points[index, 1]), timestamp)

                output_points[index] = (filtered_x, filtered_y)
                output_scores[index] = float(scores[index])

                self.last_points[index] = output_points[index]
                self.last_scores[index] = output_scores[index]
                self.missing_frames[index] = 0
                continue

            self.missing_frames[index] += 1

            if (
                self.missing_frames[index] <= self.max_gap_frames
                and self.last_scores[index] >= self.threshold
            ):
                decay = 0.82 ** int(self.missing_frames[index])
                output_points[index] = self.last_points[index]
                output_scores[index] = self.last_scores[index] * decay

        return output_points, output_scores

    def update_missing(self) -> tuple[np.ndarray, np.ndarray]:
        output_points = np.zeros((KEYPOINT_COUNT, 2), dtype=np.float32)
        output_scores = np.zeros((KEYPOINT_COUNT,), dtype=np.float32)

        for index in range(KEYPOINT_COUNT):
            self.missing_frames[index] += 1

            if (
                self.missing_frames[index] <= self.max_gap_frames
                and self.last_scores[index] >= self.threshold
            ):
                decay = 0.82 ** int(self.missing_frames[index])
                output_points[index] = self.last_points[index]
                output_scores[index] = self.last_scores[index] * decay

        return output_points, output_scores


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


def load_settings() -> PoseWorkerSettings:
    if not ENV_PATH.exists():
        raise RuntimeError(f"Nie znaleziono konfiguracji: {ENV_PATH}")

    load_dotenv(ENV_PATH)

    model_mode = os.getenv(
        "POSE_MODEL_MODE",
        "performance",
    ).strip().lower()

    if model_mode != "performance":
        raise RuntimeError(
            "Pose Pipeline V2.2 korzysta z modelu performance. "
            "Ustaw POSE_MODEL_MODE=performance."
        )

    settings = PoseWorkerSettings(
        supabase_url=get_required_environment_variable(
            "SUPABASE_URL"
        ),
        supabase_secret_key=get_required_environment_variable(
            "SUPABASE_SECRET_KEY"
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
        max_track_gap_frames=int(
            os.getenv(
                "POSE_MAX_TRACK_GAP_FRAMES",
                "9",
            )
        ),
        one_euro_min_cutoff=float(
            os.getenv(
                "POSE_ONE_EURO_MIN_CUTOFF",
                "1.0",
            )
        ),
        one_euro_beta=float(
            os.getenv(
                "POSE_ONE_EURO_BETA",
                "0.035",
            )
        ),
        one_euro_d_cutoff=float(
            os.getenv(
                "POSE_ONE_EURO_D_CUTOFF",
                "1.0",
            )
        ),
        draw_hands=parse_boolean(
            os.getenv("POSE_DRAW_HANDS"),
            default=True,
        ),
        draw_face=parse_boolean(
            os.getenv("POSE_DRAW_FACE"),
            default=False,
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

    if settings.max_track_gap_frames < 0:
        raise RuntimeError(
            "POSE_MAX_TRACK_GAP_FRAMES nie może być ujemne."
        )

    if settings.one_euro_min_cutoff <= 0:
        raise RuntimeError(
            "POSE_ONE_EURO_MIN_CUTOFF musi być większe od zera."
        )

    if settings.one_euro_beta < 0:
        raise RuntimeError(
            "POSE_ONE_EURO_BETA nie może być ujemne."
        )

    if settings.one_euro_d_cutoff <= 0:
        raise RuntimeError(
            "POSE_ONE_EURO_D_CUTOFF musi być większe od zera."
        )

    if settings.progress_update_interval_frames < 1:
        raise RuntimeError(
            "POSE_PROGRESS_UPDATE_INTERVAL_FRAMES musi być większe od zera."
        )

    if not 0 <= settings.output_crf <= 51:
        raise RuntimeError(
            "POSE_OUTPUT_CRF musi mieścić się w zakresie 0-51."
        )

    return settings


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

    def __call__(
        self,
        frame: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        frame_height, frame_width = frame.shape[:2]

        detection_result = self.detector(frame)

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

        for box, class_id in zip(
            bounding_boxes_array,
            class_ids_array,
        ):
            if int(class_id) != 0:
                continue

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

        keypoints, scores = self.pose_model(
            frame,
            bboxes=accepted_boxes,
        )

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
            0.50 * average_confidence
            + 0.22 * visibility_quality
            + 0.16 * area_quality
            + 0.12 * continuity
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
    supabase: Client,
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
            "Skan obecności V2.2: %d próbek, "
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

                update_progress(
                    supabase,
                    analysis_id,
                    settings.worker_id,
                    progress,
                    "detecting-active-segment-v2.2",
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
            "Aktywny fragment V2.2: "
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
) -> None:
    if not (
        point_is_valid(points, scores, first_index, threshold)
        and point_is_valid(points, scores, second_index, threshold)
    ):
        return

    first_point = tuple(np.round(points[first_index]).astype(int))
    second_point = tuple(np.round(points[second_index]).astype(int))

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
        )

    # Wirtualna linia kark-tułów: stabilniejsza i czytelniejsza
    # niż gęsta siatka twarzy.
    if (
        point_is_valid(points, scores, 5, threshold)
        and point_is_valid(points, scores, 6, threshold)
    ):
        neck = (points[5] + points[6]) / 2.0
        neck_score = min(float(scores[5]), float(scores[6]))

        if (
            point_is_valid(points, scores, 11, threshold)
            and point_is_valid(points, scores, 12, threshold)
        ):
            pelvis = (points[11] + points[12]) / 2.0
            cv2.line(
                output,
                tuple(np.round(neck).astype(int)),
                tuple(np.round(pelvis).astype(int)),
                torso_color,
                thickness + 1,
                cv2.LINE_AA,
            )

        if point_is_valid(points, scores, 0, threshold) and neck_score >= threshold:
            cv2.line(
                output,
                tuple(np.round(points[0]).astype(int)),
                tuple(np.round(neck).astype(int)),
                torso_color,
                thickness,
                cv2.LINE_AA,
            )

    if settings.draw_hands:
        for hand_start, body_wrist in ((91, 9), (112, 10)):
            draw_connection(
                output,
                points,
                scores,
                body_wrist,
                hand_start,
                threshold,
                hand_color,
                max(1, thickness - 1),
            )

            for local_first, local_second in HAND_LOCAL_EDGES:
                draw_connection(
                    output,
                    points,
                    scores,
                    hand_start + local_first,
                    hand_start + local_second,
                    threshold,
                    hand_color,
                    max(1, thickness - 1),
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


def process_pose_video(
    supabase: Client,
    settings: PoseWorkerSettings,
    model: StrictWholebodyModel,
    analysis: dict[str, Any],
    video_path: Path,
    job_directory: Path,
    active_segment: ActiveSegment,
    logger: logging.Logger,
) -> PoseProcessingResult:
    analysis_id = str(
        analysis["id"]
    )
    capture = cv2.VideoCapture(
        str(video_path)
    )

    if not capture.isOpened():
        raise RuntimeError(
            "OpenCV nie może otworzyć filmu źródłowego."
        )

    fps = float(
        capture.get(
            cv2.CAP_PROP_FPS
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

    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError(
            "Film ma nieprawidłowe parametry techniczne."
        )

    raw_output_video_path = (
        job_directory
        / "pose-overlay-raw.mp4"
    )
    output_video_path = (
        job_directory
        / "pose-overlay.mp4"
    )
    output_json_path = (
        job_directory
        / "pose-keypoints.json"
    )
    thumbnail_path = (
        job_directory
        / "pose-thumbnail.jpg"
    )

    writer = create_video_writer(
        raw_output_video_path,
        fps,
        width,
        height,
    )

    smoother = KeypointSmoother(
        threshold=settings.keypoint_threshold,
        max_gap_frames=settings.max_track_gap_frames,
        min_cutoff=settings.one_euro_min_cutoff,
        beta=settings.one_euro_beta,
        d_cutoff=settings.one_euro_d_cutoff,
    )

    frames_data: list[dict[str, Any]] = []

    processed_frames = 0
    detected_frames = 0

    confidence_sum = 0.0
    confidence_count = 0

    best_quality = -1.0
    best_thumbnail: np.ndarray | None = None

    previous_bbox: np.ndarray | None = None
    missing_track_frames = 0
    track_started = False
    track_ended = False

    capture.set(
        cv2.CAP_PROP_POS_FRAMES,
        active_segment.start_frame,
    )

    try:
        for source_frame_index in range(
            active_segment.start_frame,
            active_segment.end_frame + 1,
        ):
            success, frame = capture.read()

            if (
                not success
                or frame is None
                or frame.size == 0
            ):
                raise RuntimeError(
                    "Nie udało się odczytać klatki "
                    f"{source_frame_index}."
                )

            inference_started_at = (
                time.perf_counter()
            )

            if track_ended:
                keypoints_array, scores_array = (
                    StrictWholebodyModel.empty_result()
                )
                candidate = None
            else:
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

            raw_points = np.zeros(
                (KEYPOINT_COUNT, 2),
                dtype=np.float32,
            )
            raw_scores = np.zeros(
                (KEYPOINT_COUNT,),
                dtype=np.float32,
            )

            candidate_detected = (
                candidate is not None
            )
            source_timestamp = (
                source_frame_index / fps
            )

            if candidate is not None:
                track_started = True

                usable_point_count = min(
                    KEYPOINT_COUNT,
                    candidate.keypoints.shape[0],
                )
                usable_score_count = min(
                    KEYPOINT_COUNT,
                    candidate.scores.shape[0],
                )

                raw_points[
                    :usable_point_count
                ] = candidate.keypoints[
                    :usable_point_count
                ]
                raw_scores[
                    :usable_score_count
                ] = candidate.scores[
                    :usable_score_count
                ]

                (
                    smoothed_points,
                    smoothed_scores,
                ) = smoother.update(
                    raw_points,
                    raw_scores,
                    source_timestamp,
                )

                previous_bbox = (
                    candidate.bbox
                )
                missing_track_frames = 0
                detected_frames += 1

                valid_body_scores = raw_scores[
                    :BODY_POINT_COUNT
                ][
                    raw_scores[:BODY_POINT_COUNT]
                    >= settings.body_presence_threshold
                ]

                if valid_body_scores.size > 0:
                    confidence_sum += float(
                        valid_body_scores.sum()
                    )
                    confidence_count += int(
                        valid_body_scores.size
                    )

                frame_quality = (
                    candidate.body_keypoint_count
                    + candidate.body_average_confidence
                    + candidate.selection_score
                )
            else:
                missing_track_frames += 1
                frame_quality = -1.0

                if (
                    track_started
                    and missing_track_frames
                    > settings.max_track_gap_frames
                ):
                    track_ended = True
                    previous_bbox = None

                    smoothed_points = np.zeros(
                        (KEYPOINT_COUNT, 2),
                        dtype=np.float32,
                    )
                    smoothed_scores = np.zeros(
                        (KEYPOINT_COUNT,),
                        dtype=np.float32,
                    )
                else:
                    (
                        smoothed_points,
                        smoothed_scores,
                    ) = smoother.update_missing()

            rendered_frame = draw_precise_pose(
                frame,
                smoothed_points,
                smoothed_scores,
                settings,
            )

            output_frame_index = (
                processed_frames
            )
            output_timestamp = (
                output_frame_index / fps
            )

            cv2.putText(
                rendered_frame,
                (
                    "Ergonomia AI | aktywny fragment "
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

            writer.write(
                rendered_frame
            )

            if (
                candidate_detected
                and frame_quality > best_quality
            ):
                best_quality = frame_quality
                best_thumbnail = (
                    rendered_frame.copy()
                )

            inference_seconds = (
                time.perf_counter()
                - inference_started_at
            )

            frame_bbox = (
                [
                    round(
                        float(value),
                        2,
                    )
                    for value in candidate.bbox
                ]
                if candidate is not None
                else None
            )

            frames_data.append(
                {
                    "source_frame_index": (
                        source_frame_index
                    ),
                    "output_frame_index": (
                        output_frame_index
                    ),
                    "source_timestamp_seconds": round(
                        source_timestamp,
                        4,
                    ),
                    "output_timestamp_seconds": round(
                        output_timestamp,
                        4,
                    ),
                    "detected": (
                        candidate_detected
                    ),
                    "track_started": (
                        track_started
                    ),
                    "track_ended": (
                        track_ended
                    ),
                    "selection_score": (
                        round(
                            candidate.selection_score,
                            6,
                        )
                        if candidate is not None
                        else 0.0
                    ),
                    "body_keypoint_count": (
                        candidate.body_keypoint_count
                        if candidate is not None
                        else 0
                    ),
                    "bbox_xyxy": frame_bbox,
                    "inference_seconds": round(
                        inference_seconds,
                        4,
                    ),
                    "raw_keypoints": (
                        serialize_coordinates(
                            raw_points,
                            raw_scores,
                        )
                    ),
                    "smoothed_keypoints": (
                        serialize_coordinates(
                            smoothed_points,
                            smoothed_scores,
                        )
                    ),
                    "scores": serialize_scores(
                        smoothed_scores
                    ),
                }
            )

            processed_frames += 1

            if (
                processed_frames
                % settings.progress_update_interval_frames
                == 0
            ):
                frame_ratio = (
                    processed_frames
                    / max(
                        1,
                        active_segment.frame_count,
                    )
                )
                progress = (
                    30
                    + int(
                        min(1.0, frame_ratio)
                        * 58
                    )
                )

                update_progress(
                    supabase,
                    analysis_id,
                    settings.worker_id,
                    min(progress, 88),
                    "pose-inference-active-segment-v2.2",
                )
    finally:
        capture.release()
        writer.release()

    if processed_frames <= 0:
        raise RuntimeError(
            "Nie przetworzono żadnej klatki "
            "aktywnego fragmentu."
        )

    if detected_frames <= 0:
        raise RuntimeError(
            "Nie wykryto pracownika "
            "w aktywnym fragmencie."
        )

    presence_ratio = (
        detected_frames / processed_frames
    )

    if (
        presence_ratio
        < settings.min_presence_ratio
    ):
        raise RuntimeError(
            "Jakość nagrania jest zbyt niska: "
            "pracownik został poprawnie wykryty tylko w "
            f"{presence_ratio * 100:.1f}% aktywnego fragmentu."
        )

    if best_thumbnail is None:
        raise RuntimeError(
            "Nie udało się wybrać miniatury "
            "z pracownikiem."
        )

    if not cv2.imwrite(
        str(thumbnail_path),
        best_thumbnail,
    ):
        raise RuntimeError(
            "Nie udało się zapisać miniatury."
        )

    average_confidence = (
        confidence_sum / confidence_count
        if confidence_count > 0
        else 0.0
    )
    average_confidence = float(
        np.clip(
            average_confidence,
            0.0,
            1.0,
        )
    )

    transcode_video_to_h264(
        raw_output_video_path,
        output_video_path,
        logger,
        settings.output_crf,
    )
    raw_output_video_path.unlink(
        missing_ok=True
    )

    result_document = {
        "schema_version": "2.2",
        "analysis_id": analysis_id,
        "generated_by": (
            "Ergonomia AI Pose Worker"
        ),
        "quality_version": QUALITY_VERSION,
        "pose_model": (
            "COCO YOLOX-X + "
            "RTMW Wholebody performance"
        ),
        "detector_model": (
            "YOLOX-X COCO multiclass person"
        ),
        "keypoint_format": (
            "coco-wholebody-133"
        ),
        "coordinate_space": (
            "source-video-pixels"
        ),
        "primary_person_only": True,
        "strict_bbox_required": True,
        "source": {
            "width": width,
            "height": height,
            "fps": round(
                fps,
                3,
            ),
            "frame_count": int(
                analysis.get(
                    "source_frame_count"
                )
                or 0
            ),
            "duration_seconds": float(
                analysis.get(
                    "source_duration_seconds"
                )
                or 0
            ),
        },
        "active_segment": {
            "source_start_frame": (
                active_segment.start_frame
            ),
            "source_end_frame": (
                active_segment.end_frame
            ),
            "source_start_seconds": (
                active_segment.start_seconds
            ),
            "source_end_seconds": (
                active_segment.end_seconds
            ),
            "output_duration_seconds": (
                active_segment.duration_seconds
            ),
            "output_frame_count": (
                processed_frames
            ),
            "scan_stride": (
                active_segment.scan_stride
            ),
            "scan_presence_ratio": (
                active_segment.scan_presence_ratio
            ),
        },
        "configuration": {
            "model_mode": settings.model_mode,
            "inference_stride": 1,
            "detector_score_threshold": (
                settings.detector_score_threshold
            ),
            "detector_nms_threshold": (
                settings.detector_nms_threshold
            ),
            "detector_min_height_ratio": (
                settings.detector_min_height_ratio
            ),
            "detector_min_area_ratio": (
                settings.detector_min_area_ratio
            ),
            "detector_min_aspect_ratio": (
                settings.detector_min_aspect_ratio
            ),
            "detector_max_aspect_ratio": (
                settings.detector_max_aspect_ratio
            ),
            "keypoint_threshold": (
                settings.keypoint_threshold
            ),
            "body_presence_threshold": (
                settings.body_presence_threshold
            ),
            "body_min_keypoints": (
                settings.body_min_keypoints
            ),
            "scan_min_quality": (
                settings.scan_min_quality
            ),
            "tracking_method": (
                TRACKING_METHOD
            ),
            "smoothing_method": (
                SMOOTHING_METHOD
            ),
            "one_euro": {
                "min_cutoff": (
                    settings.one_euro_min_cutoff
                ),
                "beta": (
                    settings.one_euro_beta
                ),
                "d_cutoff": (
                    settings.one_euro_d_cutoff
                ),
            },
            "draw_hands": (
                settings.draw_hands
            ),
            "draw_face": (
                settings.draw_face
            ),
        },
        "summary": {
            "processed_frames": (
                processed_frames
            ),
            "detected_frames": (
                detected_frames
            ),
            "presence_ratio": round(
                presence_ratio,
                6,
            ),
            "average_body_confidence": round(
                average_confidence,
                6,
            ),
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

    logger.info(
        "Pose V2.2 zakończone: %d klatek, "
        "wykrycie %.1f%%, confidence %.4f.",
        processed_frames,
        presence_ratio * 100,
        average_confidence,
    )

    return PoseProcessingResult(
        video_path=output_video_path,
        json_path=output_json_path,
        thumbnail_path=thumbnail_path,
        processed_frames=processed_frames,
        detected_frames=detected_frames,
        average_confidence=(
            average_confidence
        ),
        presence_ratio=presence_ratio,
        active_segment=active_segment,
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

    return video_storage_path, json_storage_path, thumbnail_storage_path


def complete_pose_inference_v2(
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
        "complete_pose_inference_v2",
        {
            "p_analysis_id": str(analysis["id"]),
            "p_worker_id": settings.worker_id,
            "p_result_video_path": video_storage_path,
            "p_result_json_path": json_storage_path,
            "p_thumbnail_path": thumbnail_storage_path,
            "p_pose_model": "COCO YOLOX-X + RTMW Wholebody performance",
            "p_sample_stride": 1,
            "p_processed_frames": result.processed_frames,
            "p_detected_frames": result.detected_frames,
            "p_average_confidence": round(result.average_confidence, 6),
            "p_active_start_frame": segment.start_frame,
            "p_active_end_frame": segment.end_frame,
            "p_active_start_seconds": segment.start_seconds,
            "p_active_end_seconds": segment.end_seconds,
            "p_active_duration_seconds": segment.duration_seconds,
            "p_presence_ratio": round(result.presence_ratio, 6),
            "p_tracking_method": TRACKING_METHOD,
            "p_smoothing_method": SMOOTHING_METHOD,
            "p_quality_version": QUALITY_VERSION,
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError("Nie udało się zakończyć etapu estymacji pozy V2.2.")


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
        "Rozpoczynam Pose Pipeline V2.2: %s — %s",
        analysis_id,
        analysis.get("title"),
    )

    try:
        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            21,
            "downloading-for-pose-v2.2",
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
            "pose-inference-active-segment-v2.2",
        )

        result = process_pose_video(
            supabase,
            settings,
            model,
            analysis,
            video_path,
            job_directory,
            active_segment,
            logger,
        )

        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            91,
            "uploading-pose-results-v2.2",
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
            "saving-pose-results-v2.2",
        )

        complete_pose_inference_v2(
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
            "Błąd Pose Pipeline V2.2 dla analizy %s.",
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
                logger.info("Brak analiz gotowych do Pose Pipeline V2.2.")

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
            logger.exception("Nieobsłużony błąd cyklu Pose Pipeline V2.2.")

            if once:
                return 1

            time.sleep(settings.poll_interval_seconds)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ergonomia AI — Pose Pipeline V2.2 z detektorem COCO i ścisłym trackingiem"
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