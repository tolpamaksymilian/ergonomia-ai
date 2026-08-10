"""Start and supervise all Ergonomia AI workers without importing GPU code."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import IO, Mapping, Sequence

from dotenv import load_dotenv


RELEASE_VERSION = "0.7.0-beta.1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = REPOSITORY_ROOT / "worker"
ENV_PATH = WORKER_ROOT / ".env"
READINESS_SCRIPT = WORKER_ROOT / "src" / "check_database_readiness.py"


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    label: str
    script: Path
    no_work_markers: tuple[str, ...]


WORKERS: tuple[WorkerSpec, ...] = (
    WorkerSpec("preprocessing", "Preprocessing", WORKER_ROOT / "src" / "main.py", ("brak nowych analiz",)),
    WorkerSpec("pose", "Pose", WORKER_ROOT / "src" / "pose_worker.py", ("brak analiz gotowych",)),
    WorkerSpec("ergonomics", "Ergonomics", WORKER_ROOT / "src" / "ergonomics_worker.py", ("brak analiz gotowych",)),
    WorkerSpec("risk", "Risk", WORKER_ROOT / "src" / "risk_worker.py", ("brak analiz oczekuj",)),
    WorkerSpec("report", "Report", WORKER_ROOT / "src" / "report_worker.py", ("brak analiz oczekuj",)),
)


class StageResult(str, Enum):
    SUCCESS = "SUCCESS"
    NO_WORK = "NO_WORK"
    FAILED = "FAILED"
    CONFIG_ERROR = "CONFIG_ERROR"


@dataclass(frozen=True)
class ManagerSettings:
    restart_delay_seconds: float
    max_restarts: int
    manager_id: str


def load_manager_environment() -> ManagerSettings:
    load_dotenv(ENV_PATH, override=False)
    manager_id = os.getenv("PIPELINE_MANAGER_ID", "local-pipeline-manager-01").strip()
    if not manager_id:
        raise ValueError("PIPELINE_MANAGER_ID nie może być pusty")
    restart_delay = float(os.getenv("PIPELINE_RESTART_DELAY_SECONDS", "5"))
    max_restarts = int(os.getenv("PIPELINE_MAX_RESTARTS", "5"))
    if restart_delay < 1 or restart_delay > 300:
        raise ValueError("PIPELINE_RESTART_DELAY_SECONDS musi mieścić się w zakresie 1-300")
    if max_restarts < 0 or max_restarts > 100:
        raise ValueError("PIPELINE_MAX_RESTARTS musi mieścić się w zakresie 0-100")
    return ManagerSettings(restart_delay, max_restarts, manager_id)


def select_workers(value: str | None) -> tuple[WorkerSpec, ...]:
    if not value:
        return WORKERS
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not requested:
        raise ValueError("Lista --workers nie może być pusta")
    known = {worker.name: worker for worker in WORKERS}
    unknown = sorted(set(requested) - known.keys())
    if unknown:
        raise ValueError(f"Nieznane workery: {', '.join(unknown)}")
    if len(requested) != len(set(requested)):
        raise ValueError("Ten sam worker nie może zostać uruchomiony dwukrotnie")
    return tuple(known[name] for name in requested)


def validate_local_configuration(selected: Sequence[WorkerSpec]) -> list[str]:
    errors: list[str] = []
    if not ENV_PATH.is_file():
        errors.append("missing_file:worker/.env")
    for worker in selected:
        if not worker.script.is_file():
            errors.append(f"missing_worker:{worker.name}")
    required_migrations = (
        "20260806120000_integrate_risk_worker_v1.sql",
        "20260806203000_integrate_report_worker_v1.sql",
        "20260806210500_finalize_pipeline_v021.sql",
    )
    for filename in required_migrations:
        if not (REPOSITORY_ROOT / "supabase" / "migrations" / filename).is_file():
            errors.append(f"missing_migration:{filename}")
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "ANALYSIS_BUCKET", "ANALYSIS_RESULTS_BUCKET"):
        if not os.getenv(name, "").strip():
            errors.append(f"missing_environment_variable:{name}")
    profile_value = os.getenv("RISK_PROFILE_PATH", "").strip()
    if "risk" in {item.name for item in selected}:
        if not profile_value:
            errors.append("missing_environment_variable:RISK_PROFILE_PATH")
        else:
            profile_path = Path(profile_value)
            if not profile_path.is_absolute():
                profile_path = WORKER_ROOT / profile_path
            if not profile_path.is_file():
                errors.append("missing_file:RISK_PROFILE_PATH")
    return errors


def run_database_check() -> int:
    command = [sys.executable, str(READINESS_SCRIPT)]
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    for line in completed.stdout.splitlines():
        print(f"[check] {line}")
    return completed.returncode


def check_environment(selected: Sequence[WorkerSpec]) -> bool:
    errors = validate_local_configuration(selected)
    for error in errors:
        print(f"CHECK_ERROR={error}")
    if errors:
        return False
    return run_database_check() == 0


def classify_once_result(returncode: int, output: str, worker: WorkerSpec) -> StageResult:
    normalized = output.casefold()
    if returncode == 0:
        if any(marker in normalized for marker in worker.no_work_markers):
            return StageResult.NO_WORK
        return StageResult.SUCCESS
    if "błąd konfiguracji" in normalized or "blad konfiguracji" in normalized or "missing_environment" in normalized:
        return StageResult.CONFIG_ERROR
    return StageResult.FAILED


def run_worker_once(worker: WorkerSpec) -> StageResult:
    completed = subprocess.run(
        [sys.executable, str(worker.script), "--once"],
        cwd=REPOSITORY_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    for line in completed.stdout.splitlines():
        print(f"[{worker.name}] {line}")
    return classify_once_result(completed.returncode, completed.stdout, worker)


def run_once(selected: Sequence[WorkerSpec]) -> int:
    if not check_environment(selected):
        print("Pipeline Manager: CONFIG_ERROR")
        return 2
    results: dict[str, StageResult] = {}
    for worker in selected:
        results[worker.name] = run_worker_once(worker)
    print("")
    print(f"Pipeline Manager v{RELEASE_VERSION}")
    for worker in selected:
        print(f"{worker.label}: {results[worker.name].value}")
    failed = any(result in {StageResult.FAILED, StageResult.CONFIG_ERROR} for result in results.values())
    print("Pipeline cycle failed." if failed else "Pipeline cycle completed.")
    return 1 if failed else 0


def _forward_output(worker_name: str, stream: IO[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            print(f"[{worker_name}] {line.rstrip()}", flush=True)
    finally:
        stream.close()


def start_worker(worker: WorkerSpec) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [sys.executable, "-u", str(worker.script)],
        cwd=REPOSITORY_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if process.stdout is not None:
        threading.Thread(
            target=_forward_output,
            args=(worker.name, process.stdout),
            daemon=True,
            name=f"pipeline-log-{worker.name}",
        ).start()
    print(f"[{worker.name}] started pid={process.pid}")
    return process


def stop_processes(processes: Mapping[str, subprocess.Popen[str]]) -> None:
    for process in processes.values():
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 10
    for process in processes.values():
        if process.poll() is None:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run_continuous(
    selected: Sequence[WorkerSpec],
    settings: ManagerSettings,
    *,
    restart: bool,
) -> int:
    if not check_environment(selected):
        return 2
    processes = {worker.name: start_worker(worker) for worker in selected}
    restarts = {worker.name: 0 for worker in selected}
    specs = {worker.name: worker for worker in selected}
    try:
        while processes:
            time.sleep(0.5)
            for name, process in tuple(processes.items()):
                returncode = process.poll()
                if returncode is None:
                    continue
                print(f"[{name}] exited code={returncode}")
                if not restart or restarts[name] >= settings.max_restarts:
                    if restart:
                        print(f"[{name}] restart limit exhausted; stopping Pipeline Manager")
                    return 1
                restarts[name] += 1
                delay = min(settings.restart_delay_seconds * restarts[name], 60.0)
                print(f"[{name}] restart {restarts[name]}/{settings.max_restarts} in {delay:.1f}s")
                time.sleep(delay)
                processes[name] = start_worker(specs[name])
        return 1
    except KeyboardInterrupt:
        print("Pipeline Manager: zatrzymywanie procesów potomnych...")
        return 0
    finally:
        stop_processes(processes)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Ergonomia AI Pipeline Manager v{RELEASE_VERSION}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Uruchom po jednym cyklu każdego etapu")
    mode.add_argument("--check", action="store_true", help="Sprawdź konfigurację i gotowość bazy")
    parser.add_argument("--no-restart", action="store_true", help="Nie restartuj zakończonych workerów")
    parser.add_argument("--workers", help="Lista: preprocessing,pose,ergonomics,risk,report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    try:
        settings = load_manager_environment()
        selected = select_workers(arguments.workers)
    except (TypeError, ValueError) as error:
        print(f"CONFIG_ERROR={error}", file=sys.stderr)
        return 2
    if arguments.check:
        return 0 if check_environment(selected) else 2
    if arguments.once:
        return run_once(selected)
    return run_continuous(selected, settings, restart=not arguments.no_restart)


if __name__ == "__main__":
    raise SystemExit(main())
