from __future__ import annotations

import argparse
import json
import logging
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

# Import torch musi pozostać przed onnxruntime.
import onnxruntime as ort

from dotenv import load_dotenv
from rtmlib import Wholebody, draw_skeleton
from supabase import Client, create_client


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"

DATA_DIRECTORY = (
    WORKER_DIRECTORY
    / "data"
    / "pose-jobs"
)

LOG_DIRECTORY = (
    WORKER_DIRECTORY
    / "logs"
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
    sample_stride: int
    keypoint_threshold: float
    progress_update_interval_samples: int


@dataclass(frozen=True)
class PoseProcessingResult:
    video_path: Path
    json_path: Path
    thumbnail_path: Path
    processed_frames: int
    detected_frames: int
    average_confidence: float


def get_required_environment_variable(
    name: str,
) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Brakuje wymaganej zmiennej środowiskowej: {name}"
        )

    return value


def parse_boolean(
    value: str | None,
    default: bool = False,
) -> bool:
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
        raise RuntimeError(
            f"Nie znaleziono konfiguracji: {ENV_PATH}"
        )

    load_dotenv(ENV_PATH)

    model_mode = os.getenv(
        "POSE_MODEL_MODE",
        "balanced",
    ).strip().lower()

    if model_mode not in {
        "lightweight",
        "balanced",
        "performance",
    }:
        raise RuntimeError(
            "POSE_MODEL_MODE musi mieć wartość: "
            "lightweight, balanced albo performance."
        )

    sample_stride = int(
        os.getenv(
            "POSE_SAMPLE_STRIDE",
            "3",
        )
    )

    progress_interval = int(
        os.getenv(
            "POSE_PROGRESS_UPDATE_INTERVAL_SAMPLES",
            "10",
        )
    )

    keypoint_threshold = float(
        os.getenv(
            "POSE_KEYPOINT_THRESHOLD",
            "0.35",
        )
    )

    if sample_stride < 1:
        raise RuntimeError(
            "POSE_SAMPLE_STRIDE musi być większe od zera."
        )

    if progress_interval < 1:
        raise RuntimeError(
            "POSE_PROGRESS_UPDATE_INTERVAL_SAMPLES "
            "musi być większe od zera."
        )

    if not 0 < keypoint_threshold <= 1:
        raise RuntimeError(
            "POSE_KEYPOINT_THRESHOLD musi mieścić się "
            "w zakresie większym od 0 i nie większym niż 1."
        )

    return PoseWorkerSettings(
        supabase_url=get_required_environment_variable(
            "SUPABASE_URL"
        ),
        supabase_secret_key=(
            get_required_environment_variable(
                "SUPABASE_SECRET_KEY"
            )
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
        sample_stride=sample_stride,
        keypoint_threshold=keypoint_threshold,
        progress_update_interval_samples=(
            progress_interval
        ),
    )


def configure_logging() -> logging.Logger:
    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = logging.getLogger(
        "ergonomia-ai-pose-worker"
    )

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(
        sys.stdout
    )

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


def create_supabase_client(
    settings: PoseWorkerSettings,
) -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key,
    )


def claim_next_pose_analysis(
    supabase: Client,
    worker_id: str,
) -> dict[str, Any] | None:
    response = supabase.rpc(
        "claim_next_pose_analysis",
        {
            "p_worker_id": worker_id,
        },
    ).execute()

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def update_progress(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    progress: int,
    stage: str,
) -> None:
    safe_progress = max(
        1,
        min(99, int(progress)),
    )

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
            "Worker utracił blokadę analizy "
            "podczas aktualizacji postępu."
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
            "p_error_code": (
                type(error).__name__.upper()
            ),
            "p_error_message": str(error),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Nie udało się oznaczyć analizy jako failed."
        )


def initialize_pose_model(
    settings: PoseWorkerSettings,
    logger: logging.Logger,
) -> Wholebody:
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
        "Inicjalizacja RTMW Wholebody, tryb: %s",
        settings.model_mode,
    )

    started_at = time.perf_counter()

    model = Wholebody(
        to_openpose=False,
        mode=settings.model_mode,
        backend="onnxruntime",
        device="cuda",
    )

    logger.info(
        "Model RTMW gotowy po %.2f s.",
        time.perf_counter() - started_at,
    )

    return model


def get_safe_video_suffix(
    file_name: str,
) -> str:
    suffix = Path(file_name).suffix.lower()

    if suffix in {
        ".mp4",
        ".mov",
        ".webm",
    }:
        return suffix

    return ".mp4"


def download_source_video(
    supabase: Client,
    settings: PoseWorkerSettings,
    analysis: dict[str, Any],
    job_directory: Path,
) -> Path:
    file_name = str(
        analysis.get("source_file_name")
        or "source.mp4"
    )

    suffix = get_safe_video_suffix(
        file_name
    )

    destination_path = (
        job_directory
        / f"source{suffix}"
    )

    file_content = (
        supabase.storage
        .from_(settings.source_bucket)
        .download(
            str(analysis["source_video_path"])
        )
    )

    destination_path.write_bytes(
        file_content
    )

    if destination_path.stat().st_size <= 0:
        raise RuntimeError(
            "Pobrany film źródłowy jest pusty."
        )

    return destination_path


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
        keypoints_array = (
            keypoints_array[np.newaxis, ...]
        )

    if scores_array.ndim == 1:
        scores_array = (
            scores_array[np.newaxis, ...]
        )

    if (
        keypoints_array.ndim != 3
        or scores_array.ndim != 2
        or keypoints_array.shape[0]
        != scores_array.shape[0]
    ):
        return (
            np.empty(
                (0, 133, 2),
                dtype=np.float32,
            ),
            np.empty(
                (0, 133),
                dtype=np.float32,
            ),
        )

    return keypoints_array, scores_array


def serialize_people(
    keypoints: np.ndarray,
    scores: np.ndarray,
    threshold: float,
) -> list[dict[str, Any]]:
    people: list[dict[str, Any]] = []

    people_count = min(
        keypoints.shape[0],
        scores.shape[0],
    )

    for person_index in range(
        people_count
    ):
        person_scores = scores[
            person_index
        ]

        confident_keypoints = int(
            np.count_nonzero(
                person_scores >= threshold
            )
        )

        people.append(
            {
                "person_index": person_index,
                "confident_keypoints": (
                    confident_keypoints
                ),
                "keypoints": (
                    np.round(
                        keypoints[person_index],
                        2,
                    ).tolist()
                ),
                "scores": (
                    np.round(
                        person_scores,
                        4,
                    ).tolist()
                ),
            }
        )

    return people


def create_video_writer(
    output_path: Path,
    fps: float,
    width: int,
    height: int,
) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(
        *"mp4v"
    )

    writer = cv2.VideoWriter(
        str(output_path),
        fourcc,
        fps,
        (width, height),
    )

    if not writer.isOpened():
        raise RuntimeError(
            "Nie udało się utworzyć filmu wynikowego."
        )

    return writer

def transcode_video_to_h264(
    source_path: Path,
    destination_path: Path,
    logger: logging.Logger,
) -> None:
    """
    Konwertuje roboczy film MP4V do:
    MP4 + H.264 + yuv420p.

    Taki format jest obsługiwany przez
    Chrome, Edge, Firefox i Safari.
    """

    ffmpeg_binary = (
        resolve_ffmpeg_binary()
    )

    if not source_path.exists():
        raise RuntimeError(
            "Nie znaleziono roboczego filmu "
            f"do konwersji: {source_path}"
        )

    if source_path.stat().st_size <= 0:
        raise RuntimeError(
            "Roboczy film przed konwersją "
            "jest pusty."
        )

    destination_path.unlink(
        missing_ok=True,
    )

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
        "20",
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

    logger.info(
        "Konwersja filmu wynikowego do H.264..."
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        error_details = (
            result.stderr.strip()
            or result.stdout.strip()
            or (
                "FFmpeg zakończył działanie "
                "nieznanym błędem."
            )
        )

        raise RuntimeError(
            "Nie udało się przekonwertować "
            "filmu do H.264: "
            f"{error_details[-2000:]}"
        )

    if (
        not destination_path.exists()
        or destination_path.stat().st_size <= 0
    ):
        raise RuntimeError(
            "FFmpeg nie utworzył poprawnego "
            "filmu H.264."
        )

    logger.info(
        "Film H.264 gotowy: %.2f MB",
        destination_path.stat().st_size
        / 1024
        / 1024,
    )

def resolve_ffmpeg_binary() -> str:
    """
    Znajduje program FFmpeg.

    Kolejność:
    1. FFMPEG_PATH z worker/.env
    2. ffmpeg dostępny w PATH
    3. alias utworzony przez WinGet
    """

    configured_path = os.getenv(
        "FFMPEG_PATH",
        "",
    ).strip()

    path_from_system = shutil.which(
        "ffmpeg"
    )

    local_app_data = os.getenv(
        "LOCALAPPDATA",
        "",
    ).strip()

    winget_alias_path = (
        Path(local_app_data)
        / "Microsoft"
        / "WinGet"
        / "Links"
        / "ffmpeg.exe"
        if local_app_data
        else None
    )

    candidates = [
        configured_path or None,
        path_from_system,
        (
            str(winget_alias_path)
            if winget_alias_path is not None
            else None
        ),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        candidate_path = Path(
            candidate
        ).expanduser()

        if (
            candidate_path.exists()
            and candidate_path.is_file()
        ):
            return str(
                candidate_path.resolve()
            )

    raise RuntimeError(
        "Nie znaleziono programu FFmpeg. "
        "Ustaw pełną ścieżkę w zmiennej FFMPEG_PATH "
        "w pliku worker/.env."
    )

def transcode_video_to_h264(
    source_path: Path,
    destination_path: Path,
    logger: logging.Logger,
) -> None:
    """
    Konwertuje roboczy film OpenCV/mp4v do formatu
    zgodnego z przeglądarkami: MP4 + H.264 + yuv420p.
    """

    ffmpeg_binary = shutil.which("ffmpeg")

    if ffmpeg_binary is None:
        raise RuntimeError(
            "Nie znaleziono programu FFmpeg w PATH. "
            "Zainstaluj FFmpeg i uruchom ponownie terminal."
        )

    if not source_path.exists():
        raise RuntimeError(
            f"Nie znaleziono roboczego filmu: {source_path}"
        )

    if source_path.stat().st_size <= 0:
        raise RuntimeError(
            "Roboczy film przed konwersją jest pusty."
        )

    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),

        # Film wynikowy obecnie nie zawiera ścieżki audio.
        "-an",

        # Maksymalna zgodność z przeglądarkami.
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",

        # Zapewnia parzyste wymiary wymagane przez yuv420p.
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",

        # Metadane filmu trafiają na początek pliku,
        # dzięki czemu odtwarzanie może zacząć się szybciej.
        "-movflags",
        "+faststart",

        # Jawne oznaczenie H.264 w kontenerze MP4.
        "-tag:v",
        "avc1",

        str(destination_path),
    ]

    logger.info(
        "Konwersja filmu wynikowego do H.264..."
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        error_details = (
            result.stderr.strip()
            or result.stdout.strip()
            or "FFmpeg zakończył działanie nieznanym błędem."
        )

        raise RuntimeError(
            "Nie udało się przekonwertować filmu do H.264: "
            f"{error_details[-2000:]}"
        )

    if (
        not destination_path.exists()
        or destination_path.stat().st_size <= 0
    ):
        raise RuntimeError(
            "FFmpeg nie utworzył poprawnego filmu H.264."
        )

    logger.info(
        "Film H.264 gotowy: %.2f MB",
        destination_path.stat().st_size
        / 1024
        / 1024,
    )


def process_pose_video(
    supabase: Client,
    settings: PoseWorkerSettings,
    model: Wholebody,
    analysis: dict[str, Any],
    video_path: Path,
    job_directory: Path,
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

    if fps <= 0:
        capture.release()

        raise RuntimeError(
            "Film nie zawiera poprawnej wartości FPS."
        )

    if total_frames <= 0:
        capture.release()

        raise RuntimeError(
            "Film nie zawiera poprawnej liczby klatek."
        )

    if width <= 0 or height <= 0:
        capture.release()

        raise RuntimeError(
            "Film nie zawiera poprawnej rozdzielczości."
        )

    raw_output_video_path = (
        job_directory
        / "pose-overlay-raw.mp4"
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
        output_path=raw_output_video_path,
        fps=fps,
        width=width,
        height=height,
    )

    frames_data: list[dict[str, Any]] = []

    processed_frames = 0
    detected_frames = 0

    confidence_sum = 0.0
    confidence_count = 0

    best_quality = -1.0
    best_thumbnail: np.ndarray | None = None

    last_keypoints = np.empty(
        (0, 133, 2),
        dtype=np.float32,
    )

    last_scores = np.empty(
        (0, 133),
        dtype=np.float32,
    )

    frame_index = 0

    try:
        while True:
            success, frame = capture.read()

            if not success:
                break

            if frame is None or frame.size == 0:
                raise RuntimeError(
                    f"Odczytano pustą klatkę: {frame_index}."
                )

            should_run_inference = (
                frame_index
                % settings.sample_stride
                == 0
            )

            if should_run_inference:
                inference_started_at = (
                    time.perf_counter()
                )

                keypoints, scores = model(
                    frame
                )

                (
                    keypoints_array,
                    scores_array,
                ) = normalize_pose_arrays(
                    keypoints,
                    scores,
                )

                processed_frames += 1

                people = serialize_people(
                    keypoints=keypoints_array,
                    scores=scores_array,
                    threshold=(
                        settings.keypoint_threshold
                    ),
                )

                confident_values = (
                    scores_array[
                        scores_array
                        >= settings.keypoint_threshold
                    ]
                )

                confident_count = int(
                    confident_values.size
                )

                average_frame_confidence = (
                    float(
                        confident_values.mean()
                    )
                    if confident_count > 0
                    else 0.0
                )

                if confident_count > 0:
                    detected_frames += 1

                    confidence_sum += float(
                        confident_values.sum()
                    )

                    confidence_count += (
                        confident_count
                    )

                    last_keypoints = (
                        keypoints_array.copy()
                    )

                    last_scores = (
                        scores_array.copy()
                    )

                inference_seconds = (
                    time.perf_counter()
                    - inference_started_at
                )

                frames_data.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": round(
                            frame_index / fps,
                            4,
                        ),
                        "inference_seconds": round(
                            inference_seconds,
                            4,
                        ),
                        "people_count": len(
                            people
                        ),
                        "confident_keypoints": (
                            confident_count
                        ),
                        "average_confidence": round(
                            average_frame_confidence,
                            6,
                        ),
                        "people": people,
                    }
                )

                frame_quality = (
                    confident_count
                    + average_frame_confidence
                )

                if (
                    confident_count > 0
                    and frame_quality
                    > best_quality
                ):
                    best_quality = (
                        frame_quality
                    )

                    best_thumbnail = draw_skeleton(
                        frame.copy(),
                        keypoints_array,
                        scores_array,
                        openpose_skeleton=False,
                        kpt_thr=(
                            settings.keypoint_threshold
                        ),
                    )

                should_update_progress = (
                    processed_frames
                    % settings
                    .progress_update_interval_samples
                    == 0
                )

                if should_update_progress:
                    frame_ratio = min(
                        1.0,
                        frame_index
                        / max(
                            1,
                            total_frames - 1,
                        ),
                    )

                    progress = (
                        30
                        + int(
                            frame_ratio * 58
                        )
                    )

                    update_progress(
                        supabase=supabase,
                        analysis_id=analysis_id,
                        worker_id=(
                            settings.worker_id
                        ),
                        progress=min(
                            progress,
                            88,
                        ),
                        stage="pose-inference",
                    )

            rendered_frame = frame

            if last_keypoints.shape[0] > 0:
                rendered_frame = draw_skeleton(
                    frame.copy(),
                    last_keypoints,
                    last_scores,
                    openpose_skeleton=False,
                    kpt_thr=(
                        settings.keypoint_threshold
                    ),
                )

            cv2.putText(
                rendered_frame,
                (
                    f"Ergonomia AI | "
                    f"frame {frame_index}/{total_frames}"
                ),
                (18, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            writer.write(
                rendered_frame
            )

            frame_index += 1

    finally:
        capture.release()
        writer.release()

    if processed_frames <= 0:
        raise RuntimeError(
            "Nie wykonano inferencji dla żadnej klatki."
        )

    if detected_frames <= 0:
        raise RuntimeError(
            "Model nie wykrył człowieka "
            "w żadnej analizowanej klatce."
        )

    transcode_video_to_h264(
        source_path=raw_output_video_path,
        destination_path=output_video_path,
        logger=logger,
    )

    try:
        raw_output_video_path.unlink(
            missing_ok=True,
        )
    except OSError:
        logger.warning(
            "Nie udało się usunąć roboczego filmu: %s",
            raw_output_video_path,
        )
    if processed_frames <= 0:
        raise RuntimeError(
            "Nie wykonano inferencji dla żadnej klatki."
        )

    if detected_frames <= 0:
        raise RuntimeError(
            "Model nie wykrył człowieka w żadnej analizowanej klatce."
        )

    if best_thumbnail is None:
        raise RuntimeError(
            "Nie udało się wybrać miniatury z wykrytą osobą."
        )

    thumbnail_saved = cv2.imwrite(
        str(thumbnail_path),
        best_thumbnail,
    )

    if not thumbnail_saved:
        raise RuntimeError(
            "Nie udało się zapisać miniatury."
        )

    average_confidence = (
        confidence_sum / confidence_count
        if confidence_count > 0
        else 0.0
    )

    result_document = {
        "schema_version": "1.0",
        "analysis_id": analysis_id,
        "generated_by": "Ergonomia AI Pose Worker",
        "pose_model": (
            f"RTMW Wholebody "
            f"{settings.model_mode}"
        ),
        "keypoint_format": "mmpose-wholebody-133",
        "coordinate_space": "source-video-pixels",
        "source": {
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "frame_count": total_frames,
            "duration_seconds": round(
                total_frames / fps,
                3,
            ),
        },
        "configuration": {
            "sample_stride": (
                settings.sample_stride
            ),
            "keypoint_threshold": (
                settings.keypoint_threshold
            ),
        },
        "summary": {
            "processed_frames": (
                processed_frames
            ),
            "detected_frames": (
                detected_frames
            ),
            "average_confidence": round(
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
        "RTMW zakończone: %d klatek modelu, "
        "%d klatek z wykryciem, confidence %.4f.",
        processed_frames,
        detected_frames,
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
    )


def upload_result_file(
    supabase: Client,
    bucket_name: str,
    local_path: Path,
    storage_path: str,
    content_type: str,
) -> None:
    with local_path.open("rb") as file_handle:
        supabase.storage.from_(
            bucket_name
        ).upload(
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
    user_id = str(
        analysis["user_id"]
    )

    analysis_id = str(
        analysis["id"]
    )

    base_path = (
        f"{user_id}/"
        f"{analysis_id}/"
        "results"
    )

    video_storage_path = (
        f"{base_path}/pose-overlay.mp4"
    )

    json_storage_path = (
        f"{base_path}/pose-keypoints.json"
    )

    thumbnail_storage_path = (
        f"{base_path}/pose-thumbnail.jpg"
    )

    upload_result_file(
        supabase=supabase,
        bucket_name=settings.results_bucket,
        local_path=result.video_path,
        storage_path=video_storage_path,
        content_type="video/mp4",
    )

    upload_result_file(
        supabase=supabase,
        bucket_name=settings.results_bucket,
        local_path=result.json_path,
        storage_path=json_storage_path,
        content_type="application/json",
    )

    upload_result_file(
        supabase=supabase,
        bucket_name=settings.results_bucket,
        local_path=result.thumbnail_path,
        storage_path=thumbnail_storage_path,
        content_type="image/jpeg",
    )

    return (
        video_storage_path,
        json_storage_path,
        thumbnail_storage_path,
    )


def complete_pose_inference(
    supabase: Client,
    settings: PoseWorkerSettings,
    analysis: dict[str, Any],
    result: PoseProcessingResult,
    video_storage_path: str,
    json_storage_path: str,
    thumbnail_storage_path: str,
) -> None:
    response = supabase.rpc(
        "complete_pose_inference",
        {
            "p_analysis_id": str(
                analysis["id"]
            ),
            "p_worker_id": (
                settings.worker_id
            ),
            "p_result_video_path": (
                video_storage_path
            ),
            "p_result_json_path": (
                json_storage_path
            ),
            "p_thumbnail_path": (
                thumbnail_storage_path
            ),
            "p_pose_model": (
                f"RTMW Wholebody "
                f"{settings.model_mode}"
            ),
            "p_sample_stride": (
                settings.sample_stride
            ),
            "p_processed_frames": (
                result.processed_frames
            ),
            "p_detected_frames": (
                result.detected_frames
            ),
            "p_average_confidence": (
                round(
                    result.average_confidence,
                    6,
                )
            ),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Nie udało się zakończyć etapu estymacji pozy."
        )


def process_analysis(
    supabase: Client,
    settings: PoseWorkerSettings,
    model: Wholebody,
    analysis: dict[str, Any],
    logger: logging.Logger,
) -> None:
    analysis_id = str(
        analysis["id"]
    )

    job_directory = (
        DATA_DIRECTORY
        / analysis_id
    )

    job_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger.info(
        "Rozpoczynam RTMW: %s — %s",
        analysis_id,
        analysis.get("title"),
    )

    try:
        update_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=23,
            stage="downloading-for-pose",
        )

        video_path = download_source_video(
            supabase=supabase,
            settings=settings,
            analysis=analysis,
            job_directory=job_directory,
        )

        update_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=27,
            stage="initializing-pose-inference",
        )

        result = process_pose_video(
            supabase=supabase,
            settings=settings,
            model=model,
            analysis=analysis,
            video_path=video_path,
            job_directory=job_directory,
            logger=logger,
        )

        update_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=91,
            stage="uploading-pose-results",
        )

        (
            video_storage_path,
            json_storage_path,
            thumbnail_storage_path,
        ) = upload_pose_results(
            supabase=supabase,
            settings=settings,
            analysis=analysis,
            result=result,
        )

        update_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=97,
            stage="saving-pose-results",
        )

        complete_pose_inference(
            supabase=supabase,
            settings=settings,
            analysis=analysis,
            result=result,
            video_storage_path=(
                video_storage_path
            ),
            json_storage_path=(
                json_storage_path
            ),
            thumbnail_storage_path=(
                thumbnail_storage_path
            ),
        )

        logger.info(
            "Analiza %s jest gotowa do obliczeń ergonomicznych.",
            analysis_id,
        )

    except Exception as error:
        logger.exception(
            "Błąd modelu pozy dla analizy %s.",
            analysis_id,
        )

        try:
            mark_analysis_failed(
                supabase=supabase,
                analysis_id=analysis_id,
                worker_id=settings.worker_id,
                error=error,
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


def run_worker(
    settings: PoseWorkerSettings,
    once: bool,
) -> int:
    logger = configure_logging()

    supabase = create_supabase_client(
        settings
    )

    model = initialize_pose_model(
        settings=settings,
        logger=logger,
    )

    while True:
        try:
            analysis = (
                claim_next_pose_analysis(
                    supabase,
                    settings.worker_id,
                )
            )

            if analysis is None:
                logger.info(
                    "Brak analiz gotowych do RTMW."
                )

                if once:
                    return 0

                time.sleep(
                    settings.poll_interval_seconds
                )

                continue

            process_analysis(
                supabase=supabase,
                settings=settings,
                model=model,
                analysis=analysis,
                logger=logger,
            )

            if once:
                return 0

        except KeyboardInterrupt:
            logger.info(
                "Worker został zatrzymany."
            )

            return 0

        except Exception:
            logger.exception(
                "Nieobsłużony błąd cyklu workera pozy."
            )

            if once:
                return 1

            time.sleep(
                settings.poll_interval_seconds
            )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ergonomia AI — worker RTMW Wholebody"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Przetwórz maksymalnie jedną analizę "
            "i zakończ działanie."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        settings = load_settings()

        return run_worker(
            settings=settings,
            once=arguments.once,
        )

    except Exception as error:
        print(
            f"BŁĄD KONFIGURACJI: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())