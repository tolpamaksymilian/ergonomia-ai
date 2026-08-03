from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import cv2
import torch
from dotenv import load_dotenv
from supabase import Client, create_client


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "jobs"
LOG_DIRECTORY = WORKER_DIRECTORY / "logs"


@dataclass(frozen=True)
class WorkerSettings:
    supabase_url: str
    supabase_secret_key: str
    bucket_name: str
    worker_id: str
    poll_interval_seconds: int
    progress_update_interval_frames: int
    keep_worker_files: bool


@dataclass(frozen=True)
class VideoMetadata:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float


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


def load_settings() -> WorkerSettings:
    if not ENV_PATH.exists():
        raise RuntimeError(
            f"Nie znaleziono konfiguracji: {ENV_PATH}"
        )

    load_dotenv(ENV_PATH)

    poll_interval = int(
        os.getenv(
            "WORKER_POLL_INTERVAL_SECONDS",
            "10",
        )
    )

    progress_interval = int(
        os.getenv(
            "WORKER_PROGRESS_UPDATE_INTERVAL_FRAMES",
            "30",
        )
    )

    if poll_interval < 1:
        raise RuntimeError(
            "WORKER_POLL_INTERVAL_SECONDS musi być większe od zera."
        )

    if progress_interval < 1:
        raise RuntimeError(
            "WORKER_PROGRESS_UPDATE_INTERVAL_FRAMES "
            "musi być większe od zera."
        )

    return WorkerSettings(
        supabase_url=(
            get_required_environment_variable(
                "SUPABASE_URL"
            )
        ),
        supabase_secret_key=(
            get_required_environment_variable(
                "SUPABASE_SECRET_KEY"
            )
        ),
        bucket_name=os.getenv(
            "ANALYSIS_BUCKET",
            "analysis-videos",
        ).strip(),
        worker_id=os.getenv(
            "WORKER_ID",
            "local-worker-01",
        ).strip(),
        poll_interval_seconds=poll_interval,
        progress_update_interval_frames=(
            progress_interval
        ),
        keep_worker_files=parse_boolean(
            os.getenv("KEEP_WORKER_FILES"),
            default=False,
        ),
    )


def configure_logging() -> logging.Logger:
    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = logging.getLogger(
        "ergonomia-ai-worker"
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
        LOG_DIRECTORY / "worker.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def create_supabase_client(
    settings: WorkerSettings,
) -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key,
    )


def claim_next_analysis(
    supabase: Client,
    worker_id: str,
) -> dict[str, Any] | None:
    response = supabase.rpc(
        "claim_next_analysis",
        {
            "p_worker_id": worker_id,
        },
    ).execute()

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def update_analysis_progress(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    progress: int,
    processing_stage: str,
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
            "p_processing_stage": (
                processing_stage
            ),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Worker utracił blokadę analizy "
            "podczas aktualizacji postępu."
        )


def complete_preprocessing(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    metadata: VideoMetadata,
) -> None:
    response = supabase.rpc(
        "complete_analysis_preprocessing",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_width": metadata.width,
            "p_height": metadata.height,
            "p_fps": metadata.fps,
            "p_frame_count": (
                metadata.frame_count
            ),
            "p_duration_seconds": (
                metadata.duration_seconds
            ),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Nie udało się zakończyć preprocessingu analizy."
        )


def mark_analysis_failed(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    error: Exception,
) -> None:
    error_code = type(error).__name__.upper()

    response = supabase.rpc(
        "fail_analysis_processing",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_error_code": error_code,
            "p_error_message": str(error),
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Nie udało się oznaczyć analizy jako failed."
        )


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


def download_video(
    supabase: Client,
    settings: WorkerSettings,
    analysis: dict[str, Any],
    job_directory: Path,
) -> Path:
    analysis_id = str(analysis["id"])

    source_video_path = str(
        analysis["source_video_path"]
    )

    source_file_name = str(
        analysis.get("source_file_name")
        or "source-video.mp4"
    )

    suffix = get_safe_video_suffix(
        source_file_name
    )

    destination_path = (
        job_directory
        / f"source{suffix}"
    )

    file_content = (
        supabase.storage
        .from_(settings.bucket_name)
        .download(source_video_path)
    )

    destination_path.write_bytes(
        file_content
    )

    if destination_path.stat().st_size <= 0:
        raise RuntimeError(
            "Pobrany plik filmu jest pusty."
        )

    logging.getLogger(
        "ergonomia-ai-worker"
    ).info(
        "Pobrano film analizy %s: %.2f MB",
        analysis_id,
        destination_path.stat().st_size
        / 1024
        / 1024,
    )

    return destination_path


def process_video_frames(
    supabase: Client,
    settings: WorkerSettings,
    analysis_id: str,
    video_path: Path,
) -> VideoMetadata:
    logger = logging.getLogger(
        "ergonomia-ai-worker"
    )

    capture = cv2.VideoCapture(
        str(video_path)
    )

    if not capture.isOpened():
        raise RuntimeError(
            "OpenCV nie może otworzyć pobranego filmu."
        )

    try:
        fps = float(
            capture.get(
                cv2.CAP_PROP_FPS
            )
        )

        reported_frame_count = int(
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
            raise RuntimeError(
                "Film nie zawiera poprawnej wartości FPS."
            )

        if width <= 0 or height <= 0:
            raise RuntimeError(
                "Film nie zawiera poprawnej rozdzielczości."
            )

        update_analysis_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=10,
            processing_stage=(
                "reading-video-frames"
            ),
        )

        read_frame_count = 0

        while True:
            success, frame = capture.read()

            if not success:
                break

            if frame is None or frame.size == 0:
                raise RuntimeError(
                    "OpenCV zwróciło pustą klatkę filmu."
                )

            read_frame_count += 1

            should_update_progress = (
                read_frame_count
                % settings.progress_update_interval_frames
                == 0
            )

            if (
                should_update_progress
                and reported_frame_count > 0
            ):
                frame_ratio = min(
                    1.0,
                    read_frame_count
                    / reported_frame_count,
                )

                progress = 10 + int(
                    frame_ratio * 80
                )

                update_analysis_progress(
                    supabase=supabase,
                    analysis_id=analysis_id,
                    worker_id=settings.worker_id,
                    progress=min(
                        progress,
                        90,
                    ),
                    processing_stage=(
                        "reading-video-frames"
                    ),
                )

        if read_frame_count <= 0:
            raise RuntimeError(
                "Film nie zawiera żadnej możliwej do odczytania klatki."
            )

        duration_seconds = (
            read_frame_count / fps
        )

        logger.info(
            "Odczytano film: %dx%d, %.3f FPS, "
            "%d klatek, %.3f s",
            width,
            height,
            fps,
            read_frame_count,
            duration_seconds,
        )

        return VideoMetadata(
            width=width,
            height=height,
            fps=round(fps, 3),
            frame_count=read_frame_count,
            duration_seconds=round(
                duration_seconds,
                3,
            ),
        )
    finally:
        capture.release()


def process_analysis(
    supabase: Client,
    settings: WorkerSettings,
    analysis: dict[str, Any],
) -> None:
    logger = logging.getLogger(
        "ergonomia-ai-worker"
    )

    analysis_id = str(
        analysis["id"]
    )

    title = str(
        analysis.get("title")
        or analysis_id
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
        "Rozpoczynam preprocessing: %s — %s",
        analysis_id,
        title,
    )

    try:
        update_analysis_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=3,
            processing_stage=(
                "downloading-video"
            ),
        )

        video_path = download_video(
            supabase=supabase,
            settings=settings,
            analysis=analysis,
            job_directory=job_directory,
        )

        update_analysis_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=7,
            processing_stage=(
                "video-downloaded"
            ),
        )

        metadata = process_video_frames(
            supabase=supabase,
            settings=settings,
            analysis_id=analysis_id,
            video_path=video_path,
        )

        update_analysis_progress(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            progress=95,
            processing_stage=(
                "saving-video-metadata"
            ),
        )

        complete_preprocessing(
            supabase=supabase,
            analysis_id=analysis_id,
            worker_id=settings.worker_id,
            metadata=metadata,
        )

        logger.info(
            "Preprocessing zakończony. "
            "Analiza %s jest gotowa do modelu AI.",
            analysis_id,
        )
    except Exception as error:
        logger.exception(
            "Błąd preprocessingu analizy %s",
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
                "Nie udało się zapisać błędu "
                "analizy %s w Supabase.",
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


def print_runtime_information(
    settings: WorkerSettings,
    logger: logging.Logger,
) -> None:
    logger.info(
        "Ergonomia AI Worker"
    )

    logger.info(
        "Worker ID: %s",
        settings.worker_id,
    )

    logger.info(
        "PyTorch: %s",
        torch.__version__,
    )

    logger.info(
        "CUDA runtime: %s",
        torch.version.cuda,
    )

    logger.info(
        "CUDA dostępna: %s",
        torch.cuda.is_available(),
    )

    if torch.cuda.is_available():
        logger.info(
            "GPU: %s",
            torch.cuda.get_device_name(0),
        )


def run_worker(
    settings: WorkerSettings,
    once: bool,
) -> int:
    logger = configure_logging()

    print_runtime_information(
        settings,
        logger,
    )

    supabase = create_supabase_client(
        settings
    )

    while True:
        try:
            analysis = claim_next_analysis(
                supabase,
                settings.worker_id,
            )

            if analysis is None:
                logger.info(
                    "Brak nowych analiz do preprocessingu."
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
                analysis=analysis,
            )

            if once:
                return 0

        except KeyboardInterrupt:
            logger.info(
                "Worker został zatrzymany przez użytkownika."
            )

            return 0

        except Exception:
            logger.exception(
                "Nieobsłużony błąd cyklu workera."
            )

            if once:
                return 1

            time.sleep(
                settings.poll_interval_seconds
            )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ergonomia AI — lokalny worker preprocessingu"
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