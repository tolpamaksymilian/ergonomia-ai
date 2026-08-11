"""CPU-only worker generating Analysis Report V1 from existing JSON results."""

from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv
from supabase import Client, create_client


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
WORKER_DIRECTORY = SCRIPT_DIRECTORY.parent
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "report-jobs"
LOG_DIRECTORY = WORKER_DIRECTORY / "logs"
LOG_PATH = LOG_DIRECTORY / "report-worker.log"

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

if __package__:
    from worker.src.assessment import process_assessment_files  # noqa: E402
    from worker.src.company_methods import process_company_methods  # noqa: E402
    from worker.src.assessment.keyframes import extract_keyframes, write_assessment  # noqa: E402
    from worker.src.report.integration import (  # noqa: E402
        build_database_summary,
        build_report_file,
        build_report_storage_path,
        upload_report_file,
        upload_result_file,
    )
    from worker.src.report.schemas import (  # noqa: E402
        REPORT_VERSION,
        ReportEngineError,
        ReportErgonomicsInputMissingError,
        ReportRiskInputMissingError,
    )
else:
    from assessment import process_assessment_files  # noqa: E402
    from company_methods import process_company_methods  # noqa: E402
    from assessment.keyframes import extract_keyframes, write_assessment  # noqa: E402
    from report.integration import (  # noqa: E402
        build_database_summary,
        build_report_file,
        build_report_storage_path,
        upload_report_file,
        upload_result_file,
    )
    from report.schemas import (  # noqa: E402
        REPORT_VERSION,
        ReportEngineError,
        ReportErgonomicsInputMissingError,
        ReportRiskInputMissingError,
    )


LOGGER = logging.getLogger("ergonomia-ai-report-worker")
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_LOG_LEVEL = "INFO"
EXPECTED_RESULTS_BUCKET = "analysis-results"
CLAIM_RPC_NAME = "claim_next_report_analysis"
COMPLETE_RPC_NAME = "complete_report_v1"
FAIL_RPC_NAME = "fail_report_generation"


class ReportWorkerError(RuntimeError):
    error_code = "REPORT_BUILD_ERROR"


class ReportWorkerConfigurationError(ReportWorkerError):
    error_code = "REPORT_CONFIG_ERROR"


class ReportCompleteRpcError(ReportWorkerError):
    error_code = "REPORT_COMPLETE_RPC_ERROR"


@dataclass(frozen=True)
class WorkerSettings:
    supabase_url: str
    supabase_secret_key: str
    results_bucket: str
    worker_id: str
    poll_interval_seconds: int
    log_level: str
    keep_worker_files: bool
    assessment_enabled: bool = True
    assessment_max_candidates: int = 12
    assessment_min_quality: float = 0.55
    assessment_keyframes_enabled: bool = True


@dataclass(frozen=True)
class ClaimedAnalysis:
    analysis_id: str
    user_id: str
    title: str
    ergonomics_metrics_path: str
    risk_assessment_path: str
    metadata: dict[str, Any]


def _required_environment_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ReportWorkerConfigurationError(
            f"Brak wymaganej zmiennej środowiskowej: {name}"
        )
    return value


def _parse_bool(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _parse_positive_integer(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ReportWorkerConfigurationError(f"{name} musi być liczbą całkowitą") from error
    if parsed <= 0:
        raise ReportWorkerConfigurationError(f"{name} musi być większe od zera")
    return parsed


def _parse_ratio(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ReportWorkerConfigurationError(f"{name} musi być liczbą") from error
    if not 0.0 <= parsed <= 1.0:
        raise ReportWorkerConfigurationError(f"{name} musi mieścić się w zakresie 0-1")
    return parsed


def _parse_log_level(value: str) -> str:
    normalized = value.strip().upper()
    if not isinstance(getattr(logging, normalized, None), int):
        raise ReportWorkerConfigurationError(
            f"Nieobsługiwany WORKER_LOG_LEVEL: {value}"
        )
    return normalized


def resolve_optional_ffmpeg() -> str | None:
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("ffmpeg")


def load_settings(
    *,
    poll_interval_override: int | None = None,
    log_level_override: str | None = None,
) -> WorkerSettings:
    load_dotenv(ENV_PATH)
    results_bucket = os.getenv("ANALYSIS_RESULTS_BUCKET", EXPECTED_RESULTS_BUCKET).strip()
    if results_bucket != EXPECTED_RESULTS_BUCKET:
        raise ReportWorkerConfigurationError(
            "Report Worker wymaga prywatnego bucketu analysis-results"
        )

    fallback_id = f"{os.getenv('WORKER_ID', socket.gethostname()).strip() or socket.gethostname()}-report"
    worker_id = os.getenv("REPORT_WORKER_ID", fallback_id).strip()
    if not worker_id:
        raise ReportWorkerConfigurationError("REPORT_WORKER_ID nie może być pusty")

    if poll_interval_override is None:
        poll_interval = _parse_positive_integer(
            "WORKER_POLL_INTERVAL_SECONDS",
            os.getenv("WORKER_POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS)),
        )
    elif poll_interval_override <= 0:
        raise ReportWorkerConfigurationError("--poll-interval musi być większe od zera")
    else:
        poll_interval = poll_interval_override

    return WorkerSettings(
        supabase_url=_required_environment_value("SUPABASE_URL"),
        supabase_secret_key=_required_environment_value("SUPABASE_SECRET_KEY"),
        results_bucket=results_bucket,
        worker_id=worker_id,
        poll_interval_seconds=poll_interval,
        log_level=_parse_log_level(
            log_level_override or os.getenv("WORKER_LOG_LEVEL", DEFAULT_LOG_LEVEL)
        ),
        keep_worker_files=_parse_bool(os.getenv("KEEP_WORKER_FILES")),
        assessment_enabled=_parse_bool(os.getenv("ASSESSMENT_ENABLED", "true")),
        assessment_max_candidates=_parse_positive_integer(
            "ASSESSMENT_MAX_CANDIDATES",
            os.getenv("ASSESSMENT_MAX_CANDIDATES", "12"),
        ),
        assessment_min_quality=_parse_ratio(
            "ASSESSMENT_MIN_QUALITY",
            os.getenv("ASSESSMENT_MIN_QUALITY", "0.55"),
        ),
        assessment_keyframes_enabled=_parse_bool(
            os.getenv("ASSESSMENT_KEYFRAMES_ENABLED", "true")
        ),
    )


def configure_logging(log_level: str) -> None:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    LOGGER.setLevel(getattr(logging, log_level))
    LOGGER.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    LOGGER.addHandler(console)

    rotating_file = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    rotating_file.setFormatter(formatter)
    LOGGER.addHandler(rotating_file)


def create_supabase_client(settings: WorkerSettings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_secret_key)


def claim_next_analysis(client: Client, worker_id: str) -> Mapping[str, Any] | None:
    response = client.rpc(CLAIM_RPC_NAME, {"p_worker_id": worker_id}).execute()
    data = response.data
    if not data:
        return None
    row = data[0] if isinstance(data, list) else data
    if not isinstance(row, Mapping):
        raise ReportWorkerError("RPC przejęcia raportu zwróciło nieprawidłową odpowiedź")
    return row


def _required_claim_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReportWorkerError(f"Przejęte zadanie nie zawiera pola {field}")
    return value.strip()


def parse_claimed_analysis(row: Mapping[str, Any], worker_id: str) -> ClaimedAnalysis:
    if _required_claim_text(row, "worker_id") != worker_id:
        raise ReportWorkerError("Zadanie raportu przypisano do innego workera")
    if _required_claim_text(row, "report_worker_id") != worker_id:
        raise ReportWorkerError("Blokada Report Workera jest niespójna")
    if row.get("processing_stage") != "report-processing":
        raise ReportWorkerError("RPC nie ustawiło etapu report-processing")

    analysis_id = _required_claim_text(row, "id")
    title = _required_claim_text(row, "title")
    metadata_fields = (
        "id",
        "title",
        "created_at",
        "source_file_name",
        "source_duration_seconds",
        "source_width",
        "source_height",
        "pose_quality_version",
        "pose_processed_frames",
        "pose_detected_frames",
        "pose_presence_ratio",
    )
    return ClaimedAnalysis(
        analysis_id=analysis_id,
        user_id=_required_claim_text(row, "user_id"),
        title=title,
        ergonomics_metrics_path=_required_claim_text(row, "ergonomics_metrics_path"),
        risk_assessment_path=_required_claim_text(row, "risk_assessment_path"),
        metadata={field: row.get(field) for field in metadata_fields},
    )


def download_json_file(
    client: Client,
    bucket: str,
    storage_path: str,
    destination: Path,
    *,
    source: str,
) -> None:
    try:
        payload = client.storage.from_(bucket).download(storage_path)
    except Exception as error:
        if source == "ergonomics":
            raise ReportErgonomicsInputMissingError(
                "Nie udało się pobrać ergonomics-metrics.json."
            ) from error
        raise ReportRiskInputMissingError(
            "Nie udało się pobrać risk-assessment.json."
        ) from error
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        if source == "ergonomics":
            raise ReportErgonomicsInputMissingError(
                "Pobrany ergonomics-metrics.json jest pusty."
            )
        raise ReportRiskInputMissingError("Pobrany risk-assessment.json jest pusty.")

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
            "p_processing_stage": "report-processing",
        },
    ).execute()
    if response.data is not True:
        raise ReportCompleteRpcError("Report Worker utracił blokadę zadania")


def complete_report(
    client: Client,
    *,
    analysis_id: str,
    worker_id: str,
    report_path: str,
    report_summary: Mapping[str, Any],
) -> None:
    try:
        response = client.rpc(
            COMPLETE_RPC_NAME,
            {
                "p_analysis_id": analysis_id,
                "p_worker_id": worker_id,
                "p_report_path": report_path,
                "p_report_version": REPORT_VERSION,
                "p_report_summary": dict(report_summary),
            },
        ).execute()
    except Exception as error:
        raise ReportCompleteRpcError("RPC zakończenia raportu zwróciło błąd") from error
    if response.data is not True:
        raise ReportCompleteRpcError(
            "Nie udało się atomowo zakończyć raportu; blokada mogła wygasnąć"
        )


def sanitize_error_message(
    error: BaseException,
    settings: WorkerSettings | None = None,
) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ").strip()
    if settings is not None:
        for secret in (settings.supabase_secret_key, settings.supabase_url):
            if secret:
                message = message.replace(secret, "[REDACTED]")
    return (message or error.__class__.__name__)[:2000]


def error_code_for(error: BaseException) -> str:
    if isinstance(error, ReportEngineError):
        return error.error_code
    if isinstance(error, ReportWorkerError):
        return error.error_code
    return "REPORT_BUILD_ERROR"


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
        LOGGER.error("analysis_id=%s nie udało się zapisać stanu report-failed", analysis_id)


def cleanup_job_directory(job_directory: Path, keep_worker_files: bool) -> None:
    if keep_worker_files or not job_directory.exists():
        return
    shutil.rmtree(job_directory)


def process_claimed_analysis(
    client: Client,
    settings: WorkerSettings,
    claimed_row: Mapping[str, Any],
) -> bool:
    claimed = parse_claimed_analysis(claimed_row, settings.worker_id)
    try:
        context_response = (
            client.table("analyses")
            .select("analysis_date,analysis_context,workstation:workstations(name,code,department,area),analysis_category_links(category:analysis_categories(name,group_name))")
            .eq("id", claimed.analysis_id)
            .single()
            .execute()
        )
        context_data = context_response.data if isinstance(context_response.data, Mapping) else {}
        links = context_data.pop("analysis_category_links", [])
        context_data["categories"] = [item["category"] for item in links if isinstance(item, Mapping) and isinstance(item.get("category"), Mapping)] if isinstance(links, list) else []
        claimed.metadata.update(context_data)
    except Exception as context_error:
        LOGGER.warning("analysis_id=%s analysis_context=unavailable reason=%s", claimed.analysis_id, sanitize_error_message(context_error, settings))
    job_directory = DATA_DIRECTORY / claimed.analysis_id
    ergonomics_path = job_directory / "ergonomics-metrics.json"
    risk_path = job_directory / "risk-assessment.json"
    pose_path = job_directory / "pose-keypoints.json"
    overlay_path = job_directory / "pose-overlay.mp4"
    assessment_path = job_directory / "ergonomic-assessment.json"
    company_inputs_path = job_directory / "company-method-inputs.json"
    company_methods_path = job_directory / "company-method-assessment.json"
    report_path = job_directory / "analysis-report.json"
    started_at = time.perf_counter()

    LOGGER.info(
        "worker_id=%s analysis_id=%s title=%r stage=report-processing",
        settings.worker_id,
        claimed.analysis_id,
        claimed.title,
    )
    try:
        download_json_file(
            client,
            settings.results_bucket,
            claimed.ergonomics_metrics_path,
            ergonomics_path,
            source="ergonomics",
        )
        download_json_file(
            client,
            settings.results_bucket,
            claimed.risk_assessment_path,
            risk_path,
            source="risk",
        )
        update_heartbeat(client, claimed.analysis_id, settings.worker_id, 99)

        assessment_storage_path = (
            f"{claimed.user_id}/{claimed.analysis_id}/results/ergonomic-assessment.json"
        )
        if settings.assessment_enabled:
            try:
                pose_storage_path = (
                    f"{claimed.user_id}/{claimed.analysis_id}/results/pose-keypoints.json"
                )
                download_json_file(
                    client,
                    settings.results_bucket,
                    pose_storage_path,
                    pose_path,
                    source="pose",
                )
                assessment = process_assessment_files(
                    pose_path,
                    ergonomics_path,
                    assessment_path,
                    maximum_candidates=settings.assessment_max_candidates,
                    minimum_quality=settings.assessment_min_quality,
                )
                keyframes: list[dict[str, Any]] = []
                ffmpeg_binary = resolve_optional_ffmpeg()
                if settings.assessment_keyframes_enabled and ffmpeg_binary:
                    try:
                        overlay_storage_path = (
                            f"{claimed.user_id}/{claimed.analysis_id}/results/pose-overlay.mp4"
                        )
                        download_json_file(
                            client,
                            settings.results_bucket,
                            overlay_storage_path,
                            overlay_path,
                            source="overlay",
                        )
                        keyframe_prefix = (
                            f"{claimed.user_id}/{claimed.analysis_id}/results/assessment-keyframes"
                        )
                        keyframes = extract_keyframes(
                            assessment,
                            overlay_path,
                            job_directory / "assessment-keyframes",
                            keyframe_prefix,
                            ffmpeg_binary,
                            limit=6,
                        )
                        for keyframe in keyframes:
                            upload_result_file(
                                client.storage,
                                settings.results_bucket,
                                job_directory / "assessment-keyframes" / str(keyframe["filename"]),
                                str(keyframe["storage_path"]),
                                "image/jpeg",
                            )
                        write_assessment(assessment_path, assessment)
                    except Exception as keyframe_error:
                        LOGGER.warning(
                            "analysis_id=%s assessment_keyframes=unavailable reason=%s",
                            claimed.analysis_id,
                            sanitize_error_message(keyframe_error, settings),
                        )
                upload_report_file(
                    client.storage,
                    settings.results_bucket,
                    assessment_path,
                    assessment_storage_path,
                )
                LOGGER.info(
                    "analysis_id=%s assessment=completed output=%s keyframes=%s",
                    claimed.analysis_id,
                    assessment_storage_path,
                    len(keyframes),
                )
            except Exception as assessment_error:
                LOGGER.warning(
                    "analysis_id=%s assessment=unavailable reason=%s; report continues",
                    claimed.analysis_id,
                    sanitize_error_message(assessment_error, settings),
                )

        pose_storage_path = f"{claimed.user_id}/{claimed.analysis_id}/results/pose-keypoints.json"
        if not pose_path.is_file():
            try:
                download_json_file(client, settings.results_bucket, pose_storage_path, pose_path, source="pose")
            except Exception as pose_error:
                LOGGER.warning(
                    "analysis_id=%s company_methods_pose=unavailable reason=%s",
                    claimed.analysis_id,
                    sanitize_error_message(pose_error, settings),
                )
        company_inputs_storage_path = f"{claimed.user_id}/{claimed.analysis_id}/results/company-method-inputs.json"
        try:
            payload = client.storage.from_(settings.results_bucket).download(company_inputs_storage_path)
            if isinstance(payload, (bytes, bytearray)) and payload:
                company_inputs_path.write_bytes(payload)
        except Exception:
            LOGGER.info("analysis_id=%s company_methods_inputs=not_provided", claimed.analysis_id)
        with ergonomics_path.open("r", encoding="utf-8") as handle:
            ergonomics_document = json.load(handle)
        pose_document = None
        if pose_path.is_file():
            with pose_path.open("r", encoding="utf-8") as handle:
                pose_document = json.load(handle)
        company_inputs: Mapping[str, Any] = {}
        if company_inputs_path.is_file():
            with company_inputs_path.open("r", encoding="utf-8") as handle:
                raw_inputs = json.load(handle)
            company_inputs = raw_inputs if isinstance(raw_inputs, Mapping) else {}
        company_methods = process_company_methods(
            pose_document,
            ergonomics_document,
            company_inputs,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        write_assessment(company_methods_path, company_methods)
        company_methods_storage_path = f"{claimed.user_id}/{claimed.analysis_id}/results/company-method-assessment.json"
        upload_report_file(
            client.storage,
            settings.results_bucket,
            company_methods_path,
            company_methods_storage_path,
        )
        LOGGER.info(
            "analysis_id=%s company_methods_version=%s owas=%s missing_inputs=%s output=%s",
            claimed.analysis_id,
            company_methods.get("company_methods_version"),
            company_methods.get("owas", {}).get("status"),
            len(company_methods.get("missing_inputs", [])),
            company_methods_storage_path,
        )

        report = build_report_file(
            claimed.metadata,
            ergonomics_path,
            risk_path,
            report_path,
            assessment_path=assessment_path if assessment_path.is_file() else None,
            company_methods_path=company_methods_path,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        database_summary = build_database_summary(report)
        storage_path = build_report_storage_path(claimed.user_id, claimed.analysis_id)
        upload_report_file(
            client.storage,
            settings.results_bucket,
            report_path,
            storage_path,
        )
        complete_report(
            client,
            analysis_id=claimed.analysis_id,
            worker_id=settings.worker_id,
            report_path=storage_path,
            report_summary=database_summary,
        )

        LOGGER.info(
            "worker_id=%s analysis_id=%s report_version=%s metrics=%s key_moments=%s overall=%s insufficient_data=%s duration_seconds=%.3f output=%s stage=completed",
            settings.worker_id,
            claimed.analysis_id,
            REPORT_VERSION,
            database_summary["metric_count"],
            database_summary["key_moments_count"],
            database_summary["overall_level"],
            database_summary["insufficient_data"],
            time.perf_counter() - started_at,
            storage_path,
        )
        return True
    except Exception as error:
        LOGGER.error(
            "worker_id=%s analysis_id=%s code=%s message=%s",
            settings.worker_id,
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
                "analysis_id=%s nie udało się zapisać błędu raportu: %s",
                claimed.analysis_id,
                sanitize_error_message(fail_error, settings),
            )
        return False
    finally:
        try:
            cleanup_job_directory(job_directory, settings.keep_worker_files)
        except OSError as cleanup_error:
            LOGGER.warning(
                "analysis_id=%s nie udało się posprzątać plików: %s",
                claimed.analysis_id,
                sanitize_error_message(cleanup_error, settings),
            )


def run_worker(settings: WorkerSettings, *, once: bool) -> int:
    client = create_supabase_client(settings)
    LOGGER.info(
        "Report Worker uruchomiony worker_id=%s mode=%s",
        settings.worker_id,
        "once" if once else "continuous",
    )
    while True:
        try:
            claimed_row = claim_next_analysis(client, settings.worker_id)
        except Exception as error:
            LOGGER.error("Błąd kolejki raportów: %s", sanitize_error_message(error, settings))
            if once:
                return 1
            time.sleep(settings.poll_interval_seconds)
            continue

        if claimed_row is None:
            if once:
                LOGGER.info("Brak analiz oczekujących na raport")
                return 0
            time.sleep(settings.poll_interval_seconds)
            continue

        success = process_claimed_analysis(client, settings, claimed_row)
        if once:
            return 0 if success else 1


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ergonomia AI Report Worker V1")
    parser.add_argument("--once", action="store_true", help="Przetwórz najwyżej jeden raport")
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
    except ReportWorkerConfigurationError as error:
        print(f"Błąd konfiguracji Report Workera: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
