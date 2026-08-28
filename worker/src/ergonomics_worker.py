from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

from ergonomics.integration import (
    EmptyMetricsFramesError,
    EmptyPoseFileError,
    ErgonomicsIntegrationError,
    InvalidPoseJsonError,
    METRICS_VERSION,
    MissingResultJsonPathError,
    build_database_summary,
    build_metrics_storage_path,
    calculate_valid_metric_ratio,
    upload_metrics_file,
    validate_pose_source_document,
)
from ergonomics.processor import process_pose_file
from ergonomics.schemas import METRIC_NAMES
try:
    from worker.src.pose_artifact_storage import decompress_json_payload
except ModuleNotFoundError:  # pragma: no cover - worker/src direct execution
    from pose_artifact_storage import decompress_json_payload


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "ergonomics-jobs"
LOG_DIRECTORY = WORKER_DIRECTORY / "logs"


@dataclass(frozen=True)
class ErgonomicsWorkerSettings:
    supabase_url: str
    supabase_secret_key: str
    results_bucket: str
    worker_id: str
    poll_interval_seconds: int
    keep_worker_files: bool


class StorageDownloadError(RuntimeError):
    error_code = "STORAGE_DOWNLOAD_ERROR"


class MetricsEngineError(RuntimeError):
    error_code = "METRICS_ENGINE_ERROR"


class StorageUploadError(RuntimeError):
    error_code = "STORAGE_UPLOAD_ERROR"


class LostWorkerLockError(RuntimeError):
    error_code = "LOST_WORKER_LOCK"


def get_required_environment_variable(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Brakuje wymaganej zmiennej środowiskowej: {name}")
    return value


def parse_boolean(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "tak", "on"}


def load_settings() -> ErgonomicsWorkerSettings:
    if not ENV_PATH.exists():
        raise RuntimeError(f"Nie znaleziono konfiguracji: {ENV_PATH}")

    load_dotenv(ENV_PATH)
    pose_worker_id = os.getenv("WORKER_ID", "local-worker-01").strip()
    worker_id = os.getenv(
        "ERGONOMICS_WORKER_ID",
        f"{pose_worker_id or 'local-worker-01'}-ergonomics",
    ).strip()

    settings = ErgonomicsWorkerSettings(
        supabase_url=get_required_environment_variable("SUPABASE_URL"),
        supabase_secret_key=get_required_environment_variable("SUPABASE_SECRET_KEY"),
        results_bucket=os.getenv(
            "ANALYSIS_RESULTS_BUCKET",
            "analysis-results",
        ).strip(),
        worker_id=worker_id,
        poll_interval_seconds=int(
            os.getenv("WORKER_POLL_INTERVAL_SECONDS", "10")
        ),
        keep_worker_files=parse_boolean(
            os.getenv("KEEP_WORKER_FILES"),
            default=False,
        ),
    )

    if not settings.worker_id:
        raise RuntimeError("ERGONOMICS_WORKER_ID nie może być pusty.")
    if not settings.results_bucket:
        raise RuntimeError("ANALYSIS_RESULTS_BUCKET nie może być pusty.")
    if settings.results_bucket != "analysis-results":
        raise RuntimeError(
            "ANALYSIS_RESULTS_BUCKET musi wskazywać prywatny bucket analysis-results."
        )
    if settings.poll_interval_seconds < 1:
        raise RuntimeError(
            "WORKER_POLL_INTERVAL_SECONDS musi być większe od zera."
        )
    return settings


def configure_logging() -> logging.Logger:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ergonomia-ai-ergonomics-worker")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_DIRECTORY / "ergonomics-worker.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def create_supabase_client(settings: ErgonomicsWorkerSettings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_secret_key)


def claim_next_ergonomics_analysis(
    supabase: Client,
    worker_id: str,
) -> dict[str, Any] | None:
    response = supabase.rpc(
        "claim_next_ergonomics_analysis",
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
    response = supabase.rpc(
        "update_analysis_progress",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_progress": max(1, min(99, int(progress))),
            "p_processing_stage": stage,
        },
    ).execute()
    if response.data is not True:
        raise LostWorkerLockError(
            "Ergonomics Worker utracił blokadę podczas aktualizacji postępu."
        )


def mark_analysis_failed(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
    error: Exception,
) -> None:
    error_code = str(
        getattr(error, "error_code", type(error).__name__.upper())
    )[:100]
    response = supabase.rpc(
        "fail_ergonomics_processing",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_error_code": error_code,
            "p_error_message": str(error),
        },
    ).execute()
    if response.data is not True:
        raise LostWorkerLockError(
            "Nie udało się zapisać błędu etapu ergonomicznego."
        )


def download_pose_document(
    supabase: Client,
    settings: ErgonomicsWorkerSettings,
    result_json_path: str,
    destination_path: Path,
) -> None:
    if not result_json_path.strip():
        raise MissingResultJsonPathError(
            "Analiza nie zawiera ścieżki result_json_path."
        )

    try:
        payload = supabase.storage.from_(settings.results_bucket).download(
            result_json_path
        )
    except Exception as error:
        raise StorageDownloadError(
            f"Nie udało się pobrać pose-keypoints.json: {error}"
        ) from error

    if not payload:
        raise EmptyPoseFileError("Pobrany pose-keypoints.json jest pusty.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        decoded_payload = decompress_json_payload(payload)
    except (OSError, EOFError) as error:
        raise InvalidPoseJsonError(
            f"Nie można zdekompresować pose-keypoints.json.gz: {error}"
        ) from error
    destination_path.write_bytes(decoded_payload)
    if destination_path.stat().st_size <= 0:
        raise EmptyPoseFileError("Zapisany pose-keypoints.json jest pusty.")


def load_pose_document(input_path: Path, analysis_id: str) -> dict[str, object]:
    if not input_path.is_file() or input_path.stat().st_size <= 0:
        raise EmptyPoseFileError(f"Brak niepustego pliku wejściowego: {input_path}")

    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidPoseJsonError(
            f"pose-keypoints.json nie jest poprawnym dokumentem JSON UTF-8: {error}"
        ) from error

    return validate_pose_source_document(document, analysis_id)


def complete_ergonomics_metrics(
    supabase: Client,
    settings: ErgonomicsWorkerSettings,
    analysis_id: str,
    storage_path: str,
    processed_frames: int,
    valid_metric_ratio: float,
    database_summary: dict[str, object],
) -> None:
    response = supabase.rpc(
        "complete_ergonomics_metrics_v1",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": settings.worker_id,
            "p_metrics_path": storage_path,
            "p_metrics_version": METRICS_VERSION,
            "p_processed_frames": processed_frames,
            "p_valid_metric_ratio": valid_metric_ratio,
            "p_metrics_summary": database_summary,
        },
    ).execute()
    if response.data is not True:
        raise LostWorkerLockError(
            "Nie udało się atomowo zakończyć etapu metryk ergonomicznych."
        )


def process_analysis(
    supabase: Client,
    settings: ErgonomicsWorkerSettings,
    analysis: dict[str, Any],
    logger: logging.Logger,
) -> None:
    analysis_id = str(analysis["id"])
    user_id = str(analysis["user_id"])
    title = str(analysis.get("title") or "")
    result_json_path = str(analysis.get("result_json_path") or "").strip()
    job_directory = DATA_DIRECTORY / analysis_id
    input_path = job_directory / "pose-keypoints.json"
    output_path = job_directory / "ergonomics-metrics.json"
    started = time.perf_counter()

    job_directory.mkdir(parents=True, exist_ok=True)
    logger.info("Rozpoczynam Ergonomics Metrics V1: %s — %s", analysis_id, title)

    try:
        if not result_json_path:
            raise MissingResultJsonPathError(
                "Analiza nie zawiera ścieżki result_json_path."
            )

        logger.info("Analiza %s: downloading-pose-metrics-source.", analysis_id)
        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            79,
            "ergonomics-processing",
        )
        download_pose_document(
            supabase,
            settings,
            result_json_path,
            input_path,
        )
        pose_document = load_pose_document(input_path, analysis_id)
        pose_frames = pose_document["frames"]
        frame_count = len(pose_frames) if isinstance(pose_frames, list) else 0
        if frame_count == 0:
            raise EmptyMetricsFramesError(
                "pose-keypoints.json nie zawiera klatek do przetworzenia."
            )

        logger.info(
            "Pobrano źródło %s do %s; schema=%s, klatki=%d.",
            result_json_path,
            input_path,
            pose_document.get("schema_version"),
            frame_count,
        )

        logger.info("Analiza %s: calculating-ergonomics-metrics.", analysis_id)
        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            82,
            "ergonomics-processing",
        )
        try:
            metrics_document = process_pose_file(input_path, output_path)
        except ErgonomicsIntegrationError:
            raise
        except Exception as error:
            raise MetricsEngineError(
                f"Ergonomics Metrics Engine zakończył się błędem: {error}"
            ) from error

        processed_frames = len(metrics_document.get("frames", []))
        if processed_frames == 0:
            raise EmptyMetricsFramesError(
                "Ergonomics Metrics Engine zwrócił dokument bez klatek."
            )

        valid_metric_ratio = calculate_valid_metric_ratio(metrics_document)
        database_summary = build_database_summary(metrics_document)
        storage_path = build_metrics_storage_path(user_id, analysis_id)

        logger.info("Analiza %s: uploading-ergonomics-metrics.", analysis_id)
        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            87,
            "ergonomics-processing",
        )
        try:
            uploaded_path = upload_metrics_file(
                supabase.storage,
                settings.results_bucket,
                output_path,
                storage_path,
            )
        except Exception as error:
            if isinstance(error, ErgonomicsIntegrationError):
                raise
            raise StorageUploadError(
                f"Nie udało się przesłać ergonomics-metrics.json: {error}"
            ) from error

        logger.info("Analiza %s: saving-ergonomics-metrics.", analysis_id)
        update_progress(
            supabase,
            analysis_id,
            settings.worker_id,
            89,
            "ergonomics-processing",
        )
        complete_ergonomics_metrics(
            supabase,
            settings,
            analysis_id,
            uploaded_path,
            processed_frames,
            valid_metric_ratio,
            database_summary,
        )

        elapsed = time.perf_counter() - started
        logger.info(
            "Analiza %s gotowa do Risk Engine: klatki=%d, metryki=%d, "
            "valid_metric_ratio=%.6f, czas=%.3f s, upload=%s, "
            "etap=ready-for-risk-assessment.",
            analysis_id,
            processed_frames,
            len(METRIC_NAMES),
            valid_metric_ratio,
            elapsed,
            uploaded_path,
        )
    except Exception as error:
        logger.exception("Błąd Ergonomics Worker dla analizy %s.", analysis_id)
        try:
            mark_analysis_failed(
                supabase,
                analysis_id,
                settings.worker_id,
                error,
            )
        except Exception:
            logger.exception(
                "Nie udało się zapisać błędu ergonomicznego analizy %s.",
                analysis_id,
            )
        raise
    finally:
        if job_directory.exists() and not settings.keep_worker_files:
            shutil.rmtree(job_directory, ignore_errors=True)
            logger.info("Usunięto lokalne pliki ergonomiczne analizy %s.", analysis_id)


def run_worker(settings: ErgonomicsWorkerSettings, once: bool) -> int:
    logger = configure_logging()
    supabase = create_supabase_client(settings)

    while True:
        try:
            analysis = claim_next_ergonomics_analysis(
                supabase,
                settings.worker_id,
            )
            if analysis is None:
                logger.info("Brak analiz gotowych do Ergonomics Metrics V1.")
                if once:
                    return 0
                time.sleep(settings.poll_interval_seconds)
                continue

            process_analysis(supabase, settings, analysis, logger)
            if once:
                return 0
        except KeyboardInterrupt:
            logger.info("Ergonomics Worker został zatrzymany.")
            return 0
        except Exception:
            logger.exception("Nieobsłużony błąd cyklu Ergonomics Worker.")
            if once:
                return 1
            time.sleep(settings.poll_interval_seconds)


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ergonomia AI — osobny Ergonomics Metrics Worker V1"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Przetwórz maksymalnie jedną analizę i zakończ działanie.",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        settings = load_settings()
        return run_worker(settings, options.once)
    except Exception as error:
        print(f"BŁĄD KONFIGURACJI: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
