"""CPU-only worker integrating Risk Engine V1 with the analysis queue."""

from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv
from supabase import Client, create_client


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
WORKER_DIRECTORY = SCRIPT_DIRECTORY.parent
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "risk-jobs"
LOG_DIRECTORY = WORKER_DIRECTORY / "logs"
LOG_PATH = LOG_DIRECTORY / "risk-worker.log"

# Keep direct script execution from the repository root compatible with imports
# used by ``python -m worker.src.risk.cli``.
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

if __package__:
    from worker.src.risk.integration import (  # noqa: E402
        RiskIntegrationError,
        build_database_summary,
        build_risk_storage_path,
        process_risk_files_for_analysis,
        read_profile_document,
        upload_risk_file,
    )
else:
    from risk.integration import (  # noqa: E402
        RiskIntegrationError,
        build_database_summary,
        build_risk_storage_path,
        process_risk_files_for_analysis,
        read_profile_document,
        upload_risk_file,
    )


LOGGER = logging.getLogger("ergonomia-ai-risk-worker")
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_LOG_LEVEL = "INFO"
EXPECTED_RESULTS_BUCKET = "analysis-results"
CLAIM_RPC_NAME = "claim_next_risk_analysis"
COMPLETE_RPC_NAME = "complete_risk_assessment_v1"
FAIL_RPC_NAME = "fail_risk_processing"


class RiskWorkerError(RuntimeError):
    """Expected worker failure with a stable database-facing error code."""

    error_code = "RISK_WORKER_ERROR"


class RiskWorkerConfigurationError(RiskWorkerError):
    error_code = "RISK_CONFIG_MISSING"


class RiskDownloadError(RiskWorkerError):
    error_code = "RISK_INPUT_NOT_FOUND"


class RiskCompleteRpcError(RiskWorkerError):
    error_code = "RISK_COMPLETE_RPC_ERROR"


@dataclass(frozen=True)
class WorkerSettings:
    supabase_url: str
    supabase_secret_key: str
    results_bucket: str
    worker_id: str
    risk_profile_path: Path
    poll_interval_seconds: int
    log_level: str
    keep_worker_files: bool


@dataclass(frozen=True)
class ClaimedAnalysis:
    analysis_id: str
    user_id: str
    title: str
    ergonomics_metrics_path: str


def _required_environment_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RiskWorkerConfigurationError(f"Brak wymaganej zmiennej środowiskowej: {name}")
    return value


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_positive_integer(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RiskWorkerConfigurationError(f"{name} musi być liczbą całkowitą") from exc
    if parsed <= 0:
        raise RiskWorkerConfigurationError(f"{name} musi być większe od zera")
    return parsed


def _parse_log_level(value: str) -> str:
    normalized = value.strip().upper()
    if not isinstance(getattr(logging, normalized, None), int):
        raise RiskWorkerConfigurationError(f"Nieobsługiwany WORKER_LOG_LEVEL: {value}")
    return normalized


def _resolve_profile_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = WORKER_DIRECTORY / path
    return path.resolve()


def load_settings(
    *,
    poll_interval_override: int | None = None,
    log_level_override: str | None = None,
) -> WorkerSettings:
    load_dotenv(ENV_PATH)

    results_bucket = os.getenv("ANALYSIS_RESULTS_BUCKET", EXPECTED_RESULTS_BUCKET).strip()
    if results_bucket != EXPECTED_RESULTS_BUCKET:
        raise RiskWorkerConfigurationError(
            "Risk Worker wymaga prywatnego bucketu analysis-results"
        )

    fallback_worker_id = f"{os.getenv('WORKER_ID', socket.gethostname()).strip() or socket.gethostname()}-risk"
    worker_id = os.getenv("RISK_WORKER_ID", fallback_worker_id).strip()
    if not worker_id:
        raise RiskWorkerConfigurationError("RISK_WORKER_ID nie może być pusty")

    poll_interval = poll_interval_override
    if poll_interval is None:
        poll_interval = _parse_positive_integer(
            "WORKER_POLL_INTERVAL_SECONDS",
            os.getenv("WORKER_POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS)),
        )
    elif poll_interval <= 0:
        raise RiskWorkerConfigurationError("--poll-interval musi być większe od zera")

    log_level = _parse_log_level(
        log_level_override or os.getenv("WORKER_LOG_LEVEL", DEFAULT_LOG_LEVEL)
    )
    profile_path = _resolve_profile_path(_required_environment_value("RISK_PROFILE_PATH"))

    # Fail before connecting to Supabase when the explicit profile is absent or
    # invalid. No fallback profile is provided by design.
    read_profile_document(profile_path)

    return WorkerSettings(
        supabase_url=_required_environment_value("SUPABASE_URL"),
        supabase_secret_key=_required_environment_value("SUPABASE_SECRET_KEY"),
        results_bucket=results_bucket,
        worker_id=worker_id,
        risk_profile_path=profile_path,
        poll_interval_seconds=poll_interval,
        log_level=log_level,
        keep_worker_files=_parse_bool(os.getenv("KEEP_WORKER_FILES")),
    )


def configure_logging(log_level: str) -> None:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    LOGGER.setLevel(getattr(logging, log_level))
    LOGGER.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    LOGGER.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)


def create_supabase_client(settings: WorkerSettings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_secret_key)


def claim_next_analysis(client: Client, worker_id: str) -> Mapping[str, Any] | None:
    response = client.rpc(CLAIM_RPC_NAME, {"p_worker_id": worker_id}).execute()
    data = response.data
    if not data:
        return None
    if isinstance(data, list):
        row = data[0] if data else None
    else:
        row = data
    if not isinstance(row, Mapping):
        raise RiskWorkerError("RPC przejęcia zadania zwróciło nieprawidłową odpowiedź")
    return row


def _required_claim_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RiskWorkerError(f"Przejęte zadanie nie zawiera pola {field}")
    return value.strip()


def parse_claimed_analysis(row: Mapping[str, Any], worker_id: str) -> ClaimedAnalysis:
    claimed_worker_id = _required_claim_text(row, "worker_id")
    if claimed_worker_id != worker_id:
        raise RiskWorkerError("RPC zwróciło zadanie przypisane do innego workera")
    if row.get("processing_stage") != "risk-processing":
        raise RiskWorkerError("RPC nie ustawiło etapu risk-processing")
    return ClaimedAnalysis(
        analysis_id=_required_claim_text(row, "id"),
        user_id=_required_claim_text(row, "user_id"),
        title=str(row.get("title") or "Bez tytułu"),
        ergonomics_metrics_path=_required_claim_text(row, "ergonomics_metrics_path"),
    )


def download_metrics_file(
    client: Client,
    bucket: str,
    storage_path: str,
    destination: Path,
) -> None:
    try:
        payload = client.storage.from_(bucket).download(storage_path)
    except Exception as exc:
        raise RiskDownloadError("Nie udało się pobrać ergonomics-metrics.json") from exc

    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise RiskDownloadError("Pobrany ergonomics-metrics.json jest pusty")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def update_heartbeat(client: Client, analysis_id: str, worker_id: str, progress: int) -> None:
    response = client.rpc(
        "update_analysis_progress",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_progress": progress,
            "p_processing_stage": "risk-processing",
        },
    ).execute()
    if response.data is not True:
        raise RiskCompleteRpcError("Risk Worker utracił blokadę zadania")


def complete_risk_assessment(
    client: Client,
    *,
    analysis_id: str,
    worker_id: str,
    storage_path: str,
    assessment: Mapping[str, Any],
    database_summary: Mapping[str, Any],
) -> None:
    profile = assessment.get("profile")
    if not isinstance(profile, Mapping):
        raise RiskWorkerError("Risk Engine nie zwrócił metadanych profilu")

    try:
        result = client.rpc(
            COMPLETE_RPC_NAME,
            {
                "p_analysis_id": analysis_id,
                "p_worker_id": worker_id,
                "p_assessment_path": storage_path,
                "p_assessment_version": database_summary["risk_engine_version"],
                "p_profile_id": profile.get("profile_id"),
                "p_profile_version": profile.get("profile_version"),
                "p_profile_status": profile.get("status"),
                "p_processed_frames": database_summary["frame_count"],
                "p_valid_metric_ratio": database_summary["valid_metric_ratio"],
                "p_overall_level": database_summary["overall_level"],
                "p_assessment_summary": dict(database_summary),
            },
        ).execute()
    except Exception as error:
        raise RiskCompleteRpcError(
            "RPC zakończenia etapu Risk Engine zwróciło błąd"
        ) from error
    if result.data is not True:
        raise RiskCompleteRpcError(
            "Nie udało się atomowo zapisać wyniku Risk Engine; blokada workera mogła wygasnąć"
        )


def sanitize_error_message(error: BaseException, settings: WorkerSettings | None = None) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ").strip()
    if settings is not None:
        for secret in (settings.supabase_secret_key, settings.supabase_url):
            if secret:
                message = message.replace(secret, "[REDACTED]")
    return (message or error.__class__.__name__)[:2000]


def error_code_for(error: BaseException) -> str:
    if isinstance(error, RiskIntegrationError):
        return error.error_code
    if isinstance(error, RiskWorkerError):
        return error.error_code
    if isinstance(error, (json.JSONDecodeError, ValueError, TypeError)):
        return "RISK_INPUT_INVALID"
    return "RISK_WORKER_ERROR"


def fail_analysis(
    client: Client,
    *,
    analysis_id: str,
    worker_id: str,
    error: BaseException,
    settings: WorkerSettings,
) -> None:
    response = client.rpc(
        FAIL_RPC_NAME,
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_error_code": error_code_for(error),
            "p_error_message": sanitize_error_message(error, settings),
        },
    ).execute()
    if response.data is not True:
        LOGGER.error("analysis_id=%s nie udało się zapisać stanu risk-failed", analysis_id)


def cleanup_job_directory(job_directory: Path, keep_worker_files: bool) -> None:
    if keep_worker_files or not job_directory.exists():
        return
    shutil.rmtree(job_directory)


def _finite_float(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RiskWorkerError(f"Wynik Risk Engine nie zawiera liczby {field}")
    result = float(value)
    if not math.isfinite(result):
        raise RiskWorkerError(f"Wynik Risk Engine zawiera niepoprawne {field}")
    return result


def process_claimed_analysis(
    client: Client,
    settings: WorkerSettings,
    claimed_row: Mapping[str, Any],
) -> bool:
    claimed = parse_claimed_analysis(claimed_row, settings.worker_id)
    job_directory = DATA_DIRECTORY / claimed.analysis_id
    metrics_path = job_directory / "ergonomics-metrics.json"
    assessment_path = job_directory / "risk-assessment.json"
    started_at = time.perf_counter()

    LOGGER.info(
        "analysis_id=%s title=%r input=%s stage=risk-processing",
        claimed.analysis_id,
        claimed.title,
        claimed.ergonomics_metrics_path,
    )

    try:
        download_metrics_file(
            client,
            settings.results_bucket,
            claimed.ergonomics_metrics_path,
            metrics_path,
        )
        update_heartbeat(client, claimed.analysis_id, settings.worker_id, 93)

        assessment = process_risk_files_for_analysis(
            metrics_path,
            settings.risk_profile_path,
            assessment_path,
            expected_analysis_id=claimed.analysis_id,
        )
        database_summary = build_database_summary(assessment)
        frame_count = int(database_summary["frame_count"])
        valid_metric_ratio = _finite_float(
            database_summary["valid_metric_ratio"], "valid_metric_ratio"
        )
        overall_level = str(database_summary["overall_level"])
        profile = assessment["profile"]

        LOGGER.info(
            "analysis_id=%s profile_id=%s profile_version=%s frames=%d coverage=%.6f overall=%s",
            claimed.analysis_id,
            profile["profile_id"],
            profile["profile_version"],
            frame_count,
            valid_metric_ratio,
            overall_level,
        )

        update_heartbeat(client, claimed.analysis_id, settings.worker_id, 95)
        storage_path = build_risk_storage_path(claimed.user_id, claimed.analysis_id)
        upload_risk_file(
            client.storage,
            settings.results_bucket,
            assessment_path,
            storage_path,
        )
        complete_risk_assessment(
            client,
            analysis_id=claimed.analysis_id,
            worker_id=settings.worker_id,
            storage_path=storage_path,
            assessment=assessment,
            database_summary=database_summary,
        )

        LOGGER.info(
            "analysis_id=%s output=%s duration_seconds=%.3f stage=ready-for-report progress=97",
            claimed.analysis_id,
            storage_path,
            time.perf_counter() - started_at,
        )
        return True
    except Exception as error:
        LOGGER.error(
            "analysis_id=%s code=%s message=%s",
            claimed.analysis_id,
            error_code_for(error),
            sanitize_error_message(error, settings),
        )
        try:
            fail_analysis(
                client,
                analysis_id=claimed.analysis_id,
                worker_id=settings.worker_id,
                error=error,
                settings=settings,
            )
        except Exception as fail_error:
            LOGGER.error(
                "analysis_id=%s nie udało się zapisać błędu etapu: %s",
                claimed.analysis_id,
                sanitize_error_message(fail_error, settings),
            )
        return False
    finally:
        try:
            cleanup_job_directory(job_directory, settings.keep_worker_files)
        except OSError as cleanup_error:
            LOGGER.warning(
                "analysis_id=%s nie udało się posprzątać katalogu roboczego: %s",
                claimed.analysis_id,
                sanitize_error_message(cleanup_error, settings),
            )


def run_worker(settings: WorkerSettings, *, once: bool) -> int:
    client = create_supabase_client(settings)
    LOGGER.info(
        "Risk Worker uruchomiony worker_id=%s mode=%s profile=%s",
        settings.worker_id,
        "once" if once else "continuous",
        settings.risk_profile_path.name,
    )

    while True:
        try:
            claimed_row = claim_next_analysis(client, settings.worker_id)
        except Exception as error:
            LOGGER.error("Błąd pobierania zadania: %s", sanitize_error_message(error, settings))
            if once:
                return 1
            time.sleep(settings.poll_interval_seconds)
            continue

        if claimed_row is None:
            if once:
                LOGGER.info("Brak analiz oczekujących na Risk Engine")
                return 0
            time.sleep(settings.poll_interval_seconds)
            continue

        success = process_claimed_analysis(client, settings, claimed_row)
        if once:
            return 0 if success else 1


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ergonomia AI Risk Worker V1 (CPU-only)",
    )
    parser.add_argument("--once", action="store_true", help="Przetwórz najwyżej jedno zadanie")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=None,
        help="Nadpisz odstęp odpytywania kolejki w sekundach",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Nadpisz poziom logowania, np. INFO albo DEBUG",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    try:
        settings = load_settings(
            poll_interval_override=arguments.poll_interval,
            log_level_override=arguments.log_level,
        )
        configure_logging(settings.log_level)
        return run_worker(settings, once=arguments.once)
    except (RiskWorkerConfigurationError, RiskIntegrationError) as error:
        print(f"Błąd konfiguracji Risk Workera: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
