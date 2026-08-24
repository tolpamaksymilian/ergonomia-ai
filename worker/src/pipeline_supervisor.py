"""Local single-instance supervisor for the Ergonomia AI pipeline manager.

The supervisor owns only process lifecycle and a sanitized runtime heartbeat.
Queue semantics remain in ``pipeline_manager.py`` and the existing Supabase RPCs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from dotenv import dotenv_values, load_dotenv

try:
    from worker.src.runtime_state import atomic_write_json, cleanup_stale_temp_files
except ModuleNotFoundError:  # direct execution: python worker/src/pipeline_supervisor.py
    from runtime_state import atomic_write_json, cleanup_stale_temp_files


SUPERVISOR_VERSION = "pipeline-supervisor-v1.1-beta.1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = REPOSITORY_ROOT / "worker"
ENV_PATH = WORKER_ROOT / ".env"
RUNTIME_DIRECTORY = REPOSITORY_ROOT / ".runtime"
LOCK_PATH = RUNTIME_DIRECTORY / "pipeline-supervisor.lock"
HEALTH_PATH = RUNTIME_DIRECTORY / "worker-health.json"
STOP_REQUEST_PATH = RUNTIME_DIRECTORY / "pipeline-supervisor.stop"
PIPELINE_MANAGER_STOP_PATH = RUNTIME_DIRECTORY / "pipeline-manager.stop"
PIPELINE_MANAGER_PATH = WORKER_ROOT / "src" / "pipeline_manager.py"
READINESS_PATH = WORKER_ROOT / "src" / "check_database_readiness.py"
REQUIRED_ENVIRONMENT = (
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "ANALYSIS_BUCKET",
    "ANALYSIS_RESULTS_BUCKET",
    "RISK_PROFILE_PATH",
)
BACKOFF_SECONDS = (2.0, 5.0, 10.0, 20.0, 30.0)
SECRET_MARKERS = ("secret", "token", "jwt", "authorization", "apikey", "password")
HEALTH_WARNING_INTERVAL_SECONDS = 30.0
LOCK_GUARD_STALE_SECONDS = 30.0


def _configure_supervisor_stdio() -> None:
    """Keep the supervisor-to-Node boundary deterministic on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass


def _utf8_child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


_configure_supervisor_stdio()


@dataclass(frozen=True)
class SupervisorSettings:
    heartbeat_interval_seconds: float = 3.0
    preflight_retry_seconds: float = 30.0
    crash_limit: int = 5
    crash_window_seconds: float = 600.0
    graceful_shutdown_seconds: float = 12.0


@dataclass(frozen=True)
class PreflightCheck:
    code: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "status": self.status, "message": self.message}


class SupervisorLockError(RuntimeError):
    """Raised when a live supervisor already owns the local runtime lock."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # access denied still means the PID exists
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_lock_pid(path: Path) -> int | None:
    payload = _read_lock_payload(path)
    value = payload.get("pid") if payload is not None else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _command_line_matches_supervisor(command_line: str, repository_root: Path) -> bool:
    """Recognize both absolute and repository-relative supervisor launches.

    A relative command line does not expose the process working directory on
    every platform. In that ambiguous case we fail closed and keep the lock:
    refusing one start is safer than creating duplicate worker trees.
    """

    normalized = command_line.casefold().replace("/", "\\")
    expected = str(
        (repository_root / "worker" / "src" / "pipeline_supervisor.py").resolve()
    ).casefold().replace("/", "\\")
    return expected in normalized or "pipeline_supervisor.py" in normalized


def process_matches_supervisor(pid: int, repository_root: Path = REPOSITORY_ROOT) -> bool:
    """Best-effort protection against a stale lock whose PID was reused."""

    if pid == os.getpid():
        return True
    if not is_process_alive(pid):
        return False
    try:
        if os.name == "nt":
            command = (
                "$p=Get-CimInstance Win32_Process -Filter \"ProcessId = "
                f"{pid}\" -ErrorAction Stop; [Console]::Out.Write($p.CommandLine)"
            )
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                return True  # conservative: never risk a duplicate writer
            command_line = completed.stdout.casefold()
        else:
            command_path = Path(f"/proc/{pid}/cmdline")
            if not command_path.is_file():
                return True
            command_line = command_path.read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").casefold()
    except (OSError, subprocess.SubprocessError):
        return True
    return _command_line_matches_supervisor(command_line, repository_root)


@contextmanager
def _lock_acquisition_guard(path: Path):
    """Serialize stale-lock inspection so check/remove/create cannot race."""

    guard = path.with_name(f"{path.name}.acquire")
    deadline = time.monotonic() + 2.0
    while True:
        try:
            guard.mkdir()
            break
        except FileExistsError as error:
            try:
                stale = time.time() - guard.stat().st_mtime > LOCK_GUARD_STALE_SECONDS
                if stale:
                    guard.rmdir()
                    continue
            except FileNotFoundError:
                continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise SupervisorLockError("pipeline_supervisor_lock_guard_timeout") from error
            time.sleep(0.025)
    try:
        yield
    finally:
        try:
            guard.rmdir()
        except FileNotFoundError:
            pass


def acquire_lock(
    path: Path = LOCK_PATH,
    *,
    pid: int | None = None,
    instance_id: str | None = None,
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    owner_pid = pid or os.getpid()
    owner_instance = instance_id or str(uuid.uuid4())
    resolved_root = str(repository_root.resolve())
    with _lock_acquisition_guard(path):
        if path.exists():
            current = _read_lock_payload(path)
            existing_pid = _read_lock_pid(path)
            lock_root = current.get("repository_root") if current is not None else None
            matching_root = lock_root is None or (
                isinstance(lock_root, str)
                and Path(lock_root).resolve() == repository_root.resolve()
            )
            if (
                existing_pid is not None
                and matching_root
                and process_matches_supervisor(existing_pid, repository_root)
            ):
                raise SupervisorLockError(f"pipeline_supervisor_already_running:{existing_pid}")
            path.unlink(missing_ok=True)
        payload = json.dumps(
            {
                "pid": owner_pid,
                "instance_id": owner_instance,
                "repository_root": resolved_root,
                "started_at": utc_now(),
                "version": SUPERVISOR_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as error:
            raise SupervisorLockError("pipeline_supervisor_lock_race") from error
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())


def release_lock(
    path: Path = LOCK_PATH,
    *,
    pid: int | None = None,
    instance_id: str | None = None,
) -> None:
    if not path.exists():
        return
    payload = _read_lock_payload(path)
    if payload is None:
        return
    owner = payload.get("pid")
    owner_instance = payload.get("instance_id")
    pid_matches = owner == (pid or os.getpid())
    instance_matches = instance_id is None or owner_instance == instance_id
    if pid_matches and instance_matches:
        path.unlink(missing_ok=True)


def sanitize_message(value: object, *, maximum_length: int = 500) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"https://[^\s]+\.supabase\.co", "[supabase-url]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)authorization\s*:\s*bearer\s+[^\s,;]+", "Authorization: Bearer [redacted]", text)
    text = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)(bearer|apikey|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", text)
    return text[:maximum_length]


def _check(code: str, status: str, message: str) -> PreflightCheck:
    return PreflightCheck(code, status, sanitize_message(message, maximum_length=240))


def _configured_environment(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return {
        str(name): str(value).strip()
        for name, value in dotenv_values(path).items()
        if isinstance(name, str) and value is not None
    }


def run_preflight(
    *,
    env_path: Path = ENV_PATH,
    runtime_directory: Path = RUNTIME_DIRECTORY,
    python_executable: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    configured = _configured_environment(env_path)
    if not env_path.is_file():
        checks.append(_check("ENV_FILE_MISSING", "ERROR", "Brakuje worker/.env."))
    else:
        checks.append(_check("ENV_FILE", "OK", "Konfiguracja worker/.env jest dostępna."))
    missing = [name for name in REQUIRED_ENVIRONMENT if not configured.get(name) and not os.getenv(name, "").strip()]
    checks.append(
        _check(
            "ENV_VARIABLE_MISSING" if missing else "ENVIRONMENT",
            "ERROR" if missing else "OK",
            f"Brak wymaganych nazw zmiennych: {', '.join(missing)}" if missing else "Wymagane zmienne są ustawione.",
        )
    )
    try:
        runtime_directory.mkdir(parents=True, exist_ok=True)
        probe = runtime_directory / f".write-probe-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(_check("RUNTIME_DIRECTORY", "OK", "Katalog runtime jest zapisywalny."))
    except OSError as error:
        checks.append(_check("RUNTIME_DIRECTORY_ERROR", "ERROR", type(error).__name__))

    ffmpeg_value = configured.get("FFMPEG_PATH") or os.getenv("FFMPEG_PATH", "")
    ffmpeg = ffmpeg_value if ffmpeg_value and Path(ffmpeg_value).is_file() else shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    checks.append(_check("FFMPEG", "OK" if ffmpeg else "ERROR", "FFmpeg dostępny." if ffmpeg else "Nie znaleziono FFmpeg."))
    checks.append(_check("FFPROBE", "OK" if ffprobe else "ERROR", "FFprobe dostępny." if ffprobe else "Nie znaleziono FFprobe."))

    python = python_executable or sys.executable
    if importlib.util.find_spec("torch") is None:
        checks.append(_check("PYTORCH_IMPORT_FAILED", "ERROR", "Pakiet PyTorch nie jest dostępny w wybranym Pythonie."))
    else:
        try:
            result = command_runner(
                [python, "-c", "import torch; print('CUDA_OK' if torch.cuda.is_available() else 'CUDA_OFF'); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                checks.append(_check("PYTORCH_IMPORT_FAILED", "ERROR", "PyTorch nie przeszedł bezpiecznego testu importu."))
            elif "CUDA_OK" in result.stdout:
                device = next((line.strip() for line in result.stdout.splitlines()[1:] if line.strip()), "GPU CUDA")
                checks.append(_check("CUDA", "OK", f"CUDA dostępna: {device}."))
            else:
                checks.append(_check("CUDA_UNAVAILABLE", "ERROR", "PyTorch nie widzi urządzenia CUDA wymaganego przez Pose Worker."))
        except (OSError, subprocess.SubprocessError) as error:
            checks.append(_check("PYTORCH_IMPORT_FAILED", "ERROR", type(error).__name__))

    hand_model = configured.get("POSE_HAND_MODEL_PATH", "models/hand_landmarker.task")
    hand_path = Path(hand_model)
    if not hand_path.is_absolute():
        hand_path = WORKER_ROOT / hand_path
    checks.append(
        _check(
            "MODEL",
            "OK" if hand_path.is_file() else "WARNING",
            "Model dłoni jest dostępny." if hand_path.is_file() else "Model dłoni zostanie pobrany przy pierwszym uruchomieniu, jeśli sieć jest dostępna.",
        )
    )

    if missing or not READINESS_PATH.is_file():
        checks.append(_check("SUPABASE_READINESS", "ERROR", "Nie można wykonać gotowości bazy bez kompletnej konfiguracji."))
    else:
        try:
            result = command_runner(
                [python, str(READINESS_PATH)],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                check=False,
            )
            checks.append(
                _check(
                    "SUPABASE_READINESS" if result.returncode == 0 else "RPC_UNAVAILABLE",
                    "OK" if result.returncode == 0 else "ERROR",
                    "Baza, prywatne buckety i kontrakty RPC są gotowe." if result.returncode == 0 else "Kontrola gotowości Supabase/RPC nie powiodła się.",
                )
            )
        except (OSError, subprocess.SubprocessError) as error:
            checks.append(_check("SUPABASE_UNREACHABLE", "ERROR", type(error).__name__))
    return checks


def preflight_state(checks: Sequence[PreflightCheck]) -> str:
    if any(item.status == "ERROR" for item in checks):
        return "ERROR"
    if any(item.status == "WARNING" for item in checks):
        return "WARNING"
    return "OK"


class PipelineSupervisor:
    def __init__(
        self,
        settings: SupervisorSettings,
        *,
        health_path: Path = HEALTH_PATH,
        lock_path: Path = LOCK_PATH,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        stop_request_path: Path = STOP_REQUEST_PATH,
        manager_stop_path: Path = PIPELINE_MANAGER_STOP_PATH,
    ) -> None:
        self.settings = settings
        self.health_path = health_path
        self.lock_path = lock_path
        self.process_factory = process_factory
        self.stop_request_path = stop_request_path
        self.manager_stop_path = manager_stop_path
        self.instance_id = str(uuid.uuid4())
        self.child: subprocess.Popen[str] | None = None
        self.stop_requested = False
        self.started_at = utc_now()
        self.restart_count = 0
        self.crashes: deque[float] = deque()
        self.preflight: list[PreflightCheck] = []
        self.last_error: dict[str, object] | None = None
        self.last_progress_at: str | None = None
        self.analysis_id: str | None = None
        self.stage: str | None = None
        self.final_status = "offline"
        self.final_state = "stopped"
        self.runtime_status = "offline"
        self.runtime_state = "stopped"
        self.health_persistence = "healthy"
        self.last_heartbeat_attempt_at: str | None = None
        self.last_heartbeat_success_at: str | None = None
        self.health_write_failures_total = 0
        self.health_write_failures_consecutive = 0
        self.health_replace_retries_total = 0
        self.health_write_last_error: str | None = None
        self.health_write_last_error_at: str | None = None
        self._last_health_warning_monotonic: float | None = None
        self._heartbeat_lock = threading.Lock()
        self._output_thread: threading.Thread | None = None

    def consume_stop_request(self) -> bool:
        if not self.stop_request_path.exists():
            return False
        self.stop_request_path.unlink(missing_ok=True)
        self.stop_requested = True
        return True

    def _health_warning_due(self, now: float) -> bool:
        return (
            self._last_health_warning_monotonic is None
            or now - self._last_health_warning_monotonic >= HEALTH_WARNING_INTERVAL_SECONDS
        )

    @staticmethod
    def _filesystem_error_context(error: OSError) -> str:
        return sanitize_message(
            " ".join(
                (
                    f"type={type(error).__name__}",
                    f"errno={error.errno}",
                    f"winerror={getattr(error, 'winerror', None)}",
                    "operation=os.replace",
                )
            ),
            maximum_length=240,
        )

    def heartbeat(self, status: str, *, state: str | None = None) -> bool:
        """Persist diagnostic health without making it pipeline critical path."""

        with self._heartbeat_lock:
            attempt_at = utc_now()
            self.last_heartbeat_attempt_at = attempt_at
            self.runtime_status = status
            self.runtime_state = state or ("busy" if self.analysis_id else "idle")
            previous_failures = self.health_write_failures_consecutive
            log_retries = self._health_warning_due(time.monotonic())

            def retry_log(error: OSError, attempt: int, maximum: int, delay: float) -> None:
                if log_retries:
                    print(
                        "[SUPERVISOR] Heartbeat write temporarily blocked by Windows; "
                        f"retry {attempt}/{maximum} in {delay * 1000:.0f} ms "
                        f"({self._filesystem_error_context(error)}).",
                        file=sys.stderr,
                        flush=True,
                    )

            payload = {
                "schema_version": "1.0",
                "supervisor_version": SUPERVISOR_VERSION,
                "status": status,
                "state": self.runtime_state,
                "supervisor_instance_id": self.instance_id,
                "supervisor_pid": os.getpid(),
                "pipeline_pid": self.child.pid if self.child and self.child.poll() is None else None,
                "started_at": self.started_at,
                "last_heartbeat_at": attempt_at,
                "analysis_id": self.analysis_id,
                "stage": self.stage,
                "last_progress_at": self.last_progress_at,
                "restart_count": self.restart_count,
                "preflight_status": preflight_state(self.preflight),
                "preflight": [item.to_dict() for item in self.preflight],
                "last_error": self.last_error,
                "health_persistence": "healthy",
                "health_write_failures_total": self.health_write_failures_total,
                "health_write_failures_consecutive": 0,
                "health_replace_retries_total": self.health_replace_retries_total,
                "last_health_write_attempt_at": attempt_at,
                "last_health_write_success_at": attempt_at,
                "last_health_write_error": self.health_write_last_error,
                "last_health_write_error_at": self.health_write_last_error_at,
            }
            try:
                result = atomic_write_json(
                    self.health_path,
                    payload,
                    on_retry=retry_log,
                )
            except OSError as error:
                self.health_persistence = "degraded"
                self.health_write_failures_total += 1
                self.health_write_failures_consecutive += 1
                self.health_write_last_error = self._filesystem_error_context(error)
                self.health_write_last_error_at = attempt_at
                now = time.monotonic()
                if self._health_warning_due(now):
                    self._last_health_warning_monotonic = now
                    print(
                        "[SUPERVISOR] HEALTH_PERSISTENCE_DEGRADED "
                        f"{self.health_write_last_error} "
                        f"path={self.health_path} pid={os.getpid()} "
                        f"thread={threading.get_ident()} "
                        "pipeline_execution=CONTINUES",
                        file=sys.stderr,
                        flush=True,
                    )
                return False
            self.health_replace_retries_total += result.retries
            self.health_persistence = "healthy"
            self.last_heartbeat_success_at = attempt_at
            self.health_write_failures_consecutive = 0
            if previous_failures > 0:
                print(
                    "[SUPERVISOR] Health persistence restored after "
                    f"{previous_failures} failed writes.",
                    file=sys.stderr,
                    flush=True,
                )
            return True

    def _consume_output(self, stream: Any) -> None:
        analysis_pattern = re.compile(r"analysis(?:_id)?[=: ]+([0-9a-f-]{36})", re.IGNORECASE)
        stage_pattern = re.compile(r"stage[=: ]+([a-z0-9-]+)", re.IGNORECASE)
        for raw in iter(stream.readline, ""):
            line = sanitize_message(raw.rstrip())
            if line:
                print(f"[pipeline] {line}", flush=True)
            analysis_match = analysis_pattern.search(line)
            stage_match = stage_pattern.search(line)
            if analysis_match:
                self.analysis_id = analysis_match.group(1)
                self.last_progress_at = utc_now()
            if stage_match:
                self.stage = stage_match.group(1)
                self.last_progress_at = utc_now()
        stream.close()

    def start_child(self) -> subprocess.Popen[str]:
        self.manager_stop_path.unlink(missing_ok=True)
        child = self.process_factory(
            [sys.executable, "-u", str(PIPELINE_MANAGER_PATH)],
            cwd=REPOSITORY_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_utf8_child_environment(),
            bufsize=1,
        )
        self.child = child
        if child.stdout is not None:
            self._output_thread = threading.Thread(target=self._consume_output, args=(child.stdout,), daemon=True)
            self._output_thread.start()
        return child

    def stop_child(self) -> None:
        child = self.child
        if child is None or child.poll() is not None:
            return
        graceful_requested = False
        try:
            self.manager_stop_path.parent.mkdir(parents=True, exist_ok=True)
            self.manager_stop_path.write_text(f"{utc_now()}\n", encoding="utf-8")
            graceful_requested = True
        except OSError as error:
            print(
                "[SUPERVISOR] Pipeline Manager graceful-stop marker unavailable; "
                f"falling back to process termination ({self._filesystem_error_context(error)}).",
                file=sys.stderr,
                flush=True,
            )
        try:
            child.wait(timeout=self.settings.graceful_shutdown_seconds)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        finally:
            if graceful_requested:
                try:
                    self.manager_stop_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def register_crash(self, return_code: int, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        self.crashes.append(current)
        threshold = current - self.settings.crash_window_seconds
        while self.crashes and self.crashes[0] < threshold:
            self.crashes.popleft()
        self.restart_count += 1
        self.last_error = {
            "code": "PIPELINE_MANAGER_EXITED",
            "message": f"Pipeline Manager zakończył się kodem {return_code}.",
            "at": utc_now(),
        }
        return len(self.crashes) >= self.settings.crash_limit

    def run(self, *, skip_preflight: bool = False) -> int:
        acquire_lock(
            self.lock_path,
            instance_id=self.instance_id,
            repository_root=REPOSITORY_ROOT,
        )
        try:
            cleanup_stale_temp_files(self.health_path)
            self.stop_request_path.unlink(missing_ok=True)
            if not skip_preflight:
                load_dotenv(ENV_PATH, override=False)
            self.preflight = [] if skip_preflight else run_preflight()
            while not skip_preflight and preflight_state(self.preflight) == "ERROR" and not self.stop_requested:
                self.last_error = {"code": "PREFLIGHT_FAILED", "message": "Kontrola gotowości wykryła błąd.", "at": utc_now()}
                self.heartbeat("degraded", state="preflight_error")
                deadline = time.monotonic() + self.settings.preflight_retry_seconds
                while not self.stop_requested and time.monotonic() < deadline:
                    self.consume_stop_request()
                    self.heartbeat("degraded", state="preflight_error")
                    time.sleep(min(self.settings.heartbeat_interval_seconds, max(0.0, deadline - time.monotonic())))
                if not self.stop_requested:
                    self.preflight = run_preflight()
            if self.stop_requested:
                return 0
            self.last_error = None
            backoff_index = 0
            while not self.stop_requested:
                self.consume_stop_request()
                if self.stop_requested:
                    break
                child = self.start_child()
                self.heartbeat("online")
                while not self.stop_requested and child.poll() is None:
                    self.heartbeat("online")
                    deadline = time.monotonic() + self.settings.heartbeat_interval_seconds
                    while not self.stop_requested and time.monotonic() < deadline:
                        self.consume_stop_request()
                        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
                if self.stop_requested:
                    break
                return_code = child.poll()
                if return_code is None:
                    continue
                if self.register_crash(return_code):
                    self.final_status = "crash_loop"
                    self.final_state = "crash_loop"
                    self.heartbeat("crash_loop", state="crash_loop")
                    return 3
                self.heartbeat("restarting", state="recovering")
                delay = BACKOFF_SECONDS[min(backoff_index, len(BACKOFF_SECONDS) - 1)]
                backoff_index += 1
                deadline = time.monotonic() + delay
                while not self.stop_requested and time.monotonic() < deadline:
                    self.consume_stop_request()
                    time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
            return 0
        finally:
            self.stop_child()
            self.heartbeat(self.final_status, state=self.final_state)
            release_lock(self.lock_path, instance_id=self.instance_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Ergonomia AI {SUPERVISOR_VERSION}")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true", help="Tylko do izolowanych testów lokalnych")
    parser.add_argument("--heartbeat-interval", type=float, default=None)
    return parser


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    value = default if not raw else float(raw)
    if value <= 0:
        raise ValueError(name)
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    value = default if not raw else int(raw)
    if value <= 0:
        raise ValueError(name)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    load_dotenv(ENV_PATH, override=False)
    try:
        settings = SupervisorSettings(
            heartbeat_interval_seconds=(
                arguments.heartbeat_interval
                if arguments.heartbeat_interval is not None
                else _positive_float("PIPELINE_SUPERVISOR_HEARTBEAT_SECONDS", 3.0)
            ),
            preflight_retry_seconds=_positive_float("PIPELINE_SUPERVISOR_PREFLIGHT_RETRY_SECONDS", 30.0),
            crash_limit=_positive_int("PIPELINE_SUPERVISOR_CRASH_LIMIT", 5),
            crash_window_seconds=_positive_float("PIPELINE_SUPERVISOR_CRASH_WINDOW_SECONDS", 600.0),
            graceful_shutdown_seconds=_positive_float("PIPELINE_SUPERVISOR_GRACEFUL_SHUTDOWN_SECONDS", 12.0),
        )
        if settings.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval")
    except ValueError as error:
        print(f"CONFIG_ERROR={sanitize_message(error)}", file=sys.stderr)
        return 2
    if arguments.preflight_only:
        checks = run_preflight()
        for item in checks:
            print(f"{item.status} {item.code}: {item.message}")
        return 0 if preflight_state(checks) != "ERROR" else 2
    supervisor = PipelineSupervisor(settings)

    def request_stop(_signum: int, _frame: object) -> None:
        supervisor.stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    try:
        return supervisor.run(skip_preflight=arguments.skip_preflight)
    except SupervisorLockError as error:
        print(f"SUPERVISOR_ALREADY_RUNNING={sanitize_message(error)}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
