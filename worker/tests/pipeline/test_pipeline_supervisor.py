from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "pipeline_supervisor.py"
SPEC = importlib.util.spec_from_file_location("pipeline_supervisor", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline_supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline_supervisor
SPEC.loader.exec_module(pipeline_supervisor)


def test_atomic_heartbeat_is_sanitized_runtime_json(tmp_path: Path) -> None:
    health = tmp_path / "worker-health.json"
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(), health_path=health, lock_path=tmp_path / "lock"
    )
    supervisor.preflight = [pipeline_supervisor.PreflightCheck("ENVIRONMENT", "OK", "gotowe")]
    supervisor.heartbeat("online")
    payload = json.loads(health.read_text(encoding="utf-8"))
    assert payload["status"] == "online"
    assert payload["supervisor_version"] == "pipeline-supervisor-v1.0-beta.1"
    serialized = health.read_text(encoding="utf-8").lower()
    assert "supabase_secret_key" not in serialized
    assert "authorization" not in serialized


def test_stale_lock_is_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "pipeline-supervisor.lock"
    lock.write_text('{"pid": 987654321}', encoding="utf-8")
    monkeypatch.setattr(pipeline_supervisor, "is_process_alive", lambda _pid: False)
    pipeline_supervisor.acquire_lock(lock, pid=1234)
    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == 1234
    pipeline_supervisor.release_lock(lock, pid=1234)
    assert not lock.exists()


def test_live_lock_rejects_duplicate_supervisor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "pipeline-supervisor.lock"
    lock.write_text('{"pid": 42}', encoding="utf-8")
    monkeypatch.setattr(pipeline_supervisor, "is_process_alive", lambda _pid: True)
    with pytest.raises(pipeline_supervisor.SupervisorLockError):
        pipeline_supervisor.acquire_lock(lock, pid=1234)


def test_crash_window_enters_crash_loop_on_fifth_crash(tmp_path: Path) -> None:
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(crash_limit=5, crash_window_seconds=600),
        health_path=tmp_path / "health",
        lock_path=tmp_path / "lock",
    )
    for index in range(4):
        assert supervisor.register_crash(1, now=float(index)) is False
    assert supervisor.register_crash(1, now=4.0) is True
    assert supervisor.restart_count == 5


class _ImmediateExitProcess:
    next_pid = 9000

    def __init__(self) -> None:
        self.pid = _ImmediateExitProcess.next_pid
        _ImmediateExitProcess.next_pid += 1
        self.stdout = io.StringIO("")

    def poll(self) -> int:
        return 1

    def terminate(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        return 1

    def kill(self) -> None:
        return None


def test_child_crash_restarts_then_preserves_crash_loop_heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    starts: list[_ImmediateExitProcess] = []

    def factory(*_args, **_kwargs):
        child = _ImmediateExitProcess()
        starts.append(child)
        return child

    monkeypatch.setattr(pipeline_supervisor, "BACKOFF_SECONDS", (0.0,))
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(crash_limit=2, heartbeat_interval_seconds=0.001),
        health_path=tmp_path / "health.json",
        lock_path=tmp_path / "lock.json",
        stop_request_path=tmp_path / "stop",
        process_factory=factory,
    )
    assert supervisor.run(skip_preflight=True) == 3
    assert len(starts) == 2
    assert json.loads((tmp_path / "health.json").read_text(encoding="utf-8"))["status"] == "crash_loop"
    assert not (tmp_path / "lock.json").exists()


def test_stop_child_uses_graceful_termination(tmp_path: Path) -> None:
    class RunningProcess(_ImmediateExitProcess):
        def __init__(self) -> None:
            super().__init__()
            self.running = True
            self.terminated = False

        def poll(self) -> int | None:
            return None if self.running else 0

        def terminate(self) -> None:
            self.terminated = True
            self.running = False

    child = RunningProcess()
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(),
        health_path=tmp_path / "health",
        lock_path=tmp_path / "lock",
    )
    supervisor.child = child
    supervisor.stop_child()
    assert child.terminated is True


def test_old_crashes_do_not_trigger_crash_loop(tmp_path: Path) -> None:
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(crash_limit=2, crash_window_seconds=10),
        health_path=tmp_path / "health",
        lock_path=tmp_path / "lock",
    )
    assert supervisor.register_crash(1, now=0.0) is False
    assert supervisor.register_crash(1, now=11.0) is False


def test_stop_request_is_consumed_for_graceful_shutdown(tmp_path: Path) -> None:
    request = tmp_path / "pipeline-supervisor.stop"
    request.write_text("stop\n", encoding="utf-8")
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(),
        health_path=tmp_path / "health",
        lock_path=tmp_path / "lock",
        stop_request_path=request,
    )
    assert supervisor.consume_stop_request() is True
    assert supervisor.stop_requested is True
    assert not request.exists()


def test_missing_environment_preflight_reports_error(tmp_path: Path) -> None:
    checks = pipeline_supervisor.run_preflight(
        env_path=tmp_path / "missing.env",
        runtime_directory=tmp_path / "runtime",
    )
    codes = {item.code: item.status for item in checks}
    assert codes["ENV_FILE_MISSING"] == "ERROR"
    assert codes["ENV_VARIABLE_MISSING"] == "ERROR"


def test_sanitize_message_redacts_credentials_and_url() -> None:
    value = pipeline_supervisor.sanitize_message(
        "Authorization: Bearer abc token=xyz https://project.supabase.co"
    ).lower()
    assert "abc" not in value
    assert "xyz" not in value
    assert "project" not in value


def test_supervisor_numeric_environment_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_SUPERVISOR_CRASH_LIMIT", "7")
    assert pipeline_supervisor._positive_int("PIPELINE_SUPERVISOR_CRASH_LIMIT", 5) == 7
    monkeypatch.setenv("PIPELINE_SUPERVISOR_HEARTBEAT_SECONDS", "0")
    with pytest.raises(ValueError):
        pipeline_supervisor._positive_float("PIPELINE_SUPERVISOR_HEARTBEAT_SECONDS", 3.0)


def test_preflight_reports_missing_binaries_torch_and_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://example.invalid\nSUPABASE_SECRET_KEY=test\nANALYSIS_BUCKET=source\nANALYSIS_RESULTS_BUCKET=results\nRISK_PROFILE_PATH=profile.json\nPOSE_HAND_MODEL_PATH=missing.task\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline_supervisor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(pipeline_supervisor.importlib.util, "find_spec", lambda _name: None)
    checks = pipeline_supervisor.run_preflight(env_path=env, runtime_directory=tmp_path / "runtime")
    states = {item.code: item.status for item in checks}
    assert states["FFMPEG"] == "ERROR"
    assert states["FFPROBE"] == "ERROR"
    assert states["PYTORCH_IMPORT_FAILED"] == "ERROR"
    assert states["MODEL"] == "WARNING"


def test_preflight_reports_cuda_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _complete_env(tmp_path)
    monkeypatch.setattr(pipeline_supervisor.shutil, "which", lambda name: name)
    monkeypatch.setattr(pipeline_supervisor.importlib.util, "find_spec", lambda _name: object())

    def runner(command, **_kwargs):
        stdout = "CUDA_OFF\n" if "-c" in command else "READY\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    checks = pipeline_supervisor.run_preflight(
        env_path=env,
        runtime_directory=tmp_path / "runtime",
        command_runner=runner,
    )
    states = {item.code: item.status for item in checks}
    assert states["CUDA_UNAVAILABLE"] == "ERROR"


def test_preflight_reports_database_readiness_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _complete_env(tmp_path)
    monkeypatch.setattr(pipeline_supervisor.shutil, "which", lambda name: name)
    monkeypatch.setattr(pipeline_supervisor.importlib.util, "find_spec", lambda _name: object())

    def runner(command, **_kwargs):
        if "-c" in command:
            return subprocess.CompletedProcess(command, 0, "CUDA_OK\nTest GPU\n", "")
        return subprocess.CompletedProcess(command, 1, "", "not ready")

    checks = pipeline_supervisor.run_preflight(
        env_path=env,
        runtime_directory=tmp_path / "runtime",
        command_runner=runner,
    )
    states = {item.code: item.status for item in checks}
    assert states["RPC_UNAVAILABLE"] == "ERROR"


def _complete_env(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://example.invalid\nSUPABASE_SECRET_KEY=test\nANALYSIS_BUCKET=source\nANALYSIS_RESULTS_BUCKET=results\nRISK_PROFILE_PATH=profile.json\nPOSE_HAND_MODEL_PATH=missing.task\n",
        encoding="utf-8",
    )
    return env
