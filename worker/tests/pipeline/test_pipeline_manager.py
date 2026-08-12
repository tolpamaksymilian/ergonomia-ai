from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "pipeline_manager.py"
SPEC = importlib.util.spec_from_file_location("pipeline_manager", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline_manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline_manager
SPEC.loader.exec_module(pipeline_manager)


def test_default_worker_order() -> None:
    assert [worker.name for worker in pipeline_manager.select_workers(None)] == [
        "preprocessing", "pose", "ergonomics", "risk", "report", "scene"
    ]


def test_selected_worker_order_is_preserved() -> None:
    selected = pipeline_manager.select_workers("risk,report")
    assert [worker.name for worker in selected] == ["risk", "report"]


def test_unknown_worker_is_rejected() -> None:
    with pytest.raises(ValueError, match="Nieznane workery"):
        pipeline_manager.select_workers("pose,unknown")


def test_duplicate_worker_is_rejected() -> None:
    with pytest.raises(ValueError, match="dwukrotnie"):
        pipeline_manager.select_workers("pose,pose")


@pytest.mark.parametrize("worker", pipeline_manager.WORKERS)
def test_no_work_output_is_not_failure(worker: object) -> None:
    marker = worker.no_work_markers[0]
    result = pipeline_manager.classify_once_result(0, marker.upper(), worker)
    assert result is pipeline_manager.StageResult.NO_WORK


def test_zero_exit_without_marker_is_success() -> None:
    worker = pipeline_manager.WORKERS[0]
    assert pipeline_manager.classify_once_result(0, "done", worker) is pipeline_manager.StageResult.SUCCESS


def test_nonzero_exit_is_failure() -> None:
    worker = pipeline_manager.WORKERS[0]
    assert pipeline_manager.classify_once_result(1, "runtime failed", worker) is pipeline_manager.StageResult.FAILED


def test_configuration_error_is_distinguished() -> None:
    worker = pipeline_manager.WORKERS[0]
    assert pipeline_manager.classify_once_result(1, "BŁĄD KONFIGURACJI", worker) is pipeline_manager.StageResult.CONFIG_ERROR


def test_once_stops_before_workers_when_preflight_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_manager, "check_environment", lambda _selected: False)
    called = False

    def fake_run(_worker: object) -> object:
        nonlocal called
        called = True
        return pipeline_manager.StageResult.SUCCESS

    monkeypatch.setattr(pipeline_manager, "run_worker_once", fake_run)
    assert pipeline_manager.run_once(pipeline_manager.WORKERS) == 2
    assert called is False


def test_once_accepts_no_work_for_every_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_manager, "check_environment", lambda _selected: True)
    monkeypatch.setattr(
        pipeline_manager,
        "run_worker_once",
        lambda _worker: pipeline_manager.StageResult.NO_WORK,
    )
    assert pipeline_manager.run_once(pipeline_manager.WORKERS) == 0


def test_once_returns_failure_for_failed_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_manager, "check_environment", lambda _selected: True)
    monkeypatch.setattr(
        pipeline_manager,
        "run_worker_once",
        lambda worker: pipeline_manager.StageResult.FAILED if worker.name == "risk" else pipeline_manager.StageResult.SUCCESS,
    )
    assert pipeline_manager.run_once(pipeline_manager.WORKERS) == 1


def test_stop_processes_terminates_and_waits() -> None:
    events: list[str] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: float) -> int:
            events.append("wait")
            return 0

    pipeline_manager.stop_processes({"pose": FakeProcess()})
    assert events == ["terminate", "wait"]


def test_database_check_uses_current_python_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="DATABASE_READY=true\n")

    monkeypatch.setattr(pipeline_manager.subprocess, "run", fake_run)
    assert pipeline_manager.run_database_check() == 0
    assert captured["command"][0] == pipeline_manager.sys.executable
    assert captured["kwargs"]["check"] is False


def test_continuous_respects_restart_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    starts: list[str] = []

    class ExitedProcess:
        pid = 1
        stdout = None

        def poll(self) -> int:
            return 1

    monkeypatch.setattr(pipeline_manager, "check_environment", lambda _selected: True)
    monkeypatch.setattr(
        pipeline_manager,
        "start_worker",
        lambda worker: starts.append(worker.name) or ExitedProcess(),
    )
    monkeypatch.setattr(pipeline_manager.time, "sleep", lambda _delay: None)
    settings = pipeline_manager.ManagerSettings(1, 2, "test-manager")
    result = pipeline_manager.run_continuous(
        (pipeline_manager.WORKERS[0],), settings, restart=True
    )
    assert result == 1
    assert starts == ["preprocessing", "preprocessing", "preprocessing"]


def test_no_restart_starts_worker_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    starts = 0

    class ExitedProcess:
        pid = 1
        stdout = None

        def poll(self) -> int:
            return 1

    def fake_start(_worker: object) -> ExitedProcess:
        nonlocal starts
        starts += 1
        return ExitedProcess()

    monkeypatch.setattr(pipeline_manager, "check_environment", lambda _selected: True)
    monkeypatch.setattr(pipeline_manager, "start_worker", fake_start)
    monkeypatch.setattr(pipeline_manager.time, "sleep", lambda _delay: None)
    settings = pipeline_manager.ManagerSettings(1, 5, "test-manager")
    assert pipeline_manager.run_continuous(
        (pipeline_manager.WORKERS[0],), settings, restart=False
    ) == 1
    assert starts == 1


def test_keyboard_interrupt_calls_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    process = SimpleNamespace(pid=1, stdout=None, poll=lambda: None)
    cleaned: list[str] = []
    monkeypatch.setattr(pipeline_manager, "check_environment", lambda _selected: True)
    monkeypatch.setattr(pipeline_manager, "start_worker", lambda _worker: process)
    monkeypatch.setattr(
        pipeline_manager.time,
        "sleep",
        lambda _delay: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(
        pipeline_manager,
        "stop_processes",
        lambda processes: cleaned.extend(processes.keys()),
    )
    settings = pipeline_manager.ManagerSettings(1, 1, "test-manager")
    assert pipeline_manager.run_continuous(
        (pipeline_manager.WORKERS[0],), settings, restart=True
    ) == 0
    assert cleaned == ["preprocessing"]


def test_worker_process_is_started_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakePopen:
        pid = 42
        stdout = None

    def fake_popen(command: list[str], **kwargs: object) -> FakePopen:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakePopen()

    monkeypatch.setattr(pipeline_manager.subprocess, "Popen", fake_popen)
    pipeline_manager.start_worker(pipeline_manager.WORKERS[1])
    assert captured["command"][0] == pipeline_manager.sys.executable
    assert "shell" not in captured["kwargs"]


def test_manager_source_does_not_print_secret_values() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "SUPABASE_SECRET_KEY=" not in source
    assert "print(os.environ" not in source
