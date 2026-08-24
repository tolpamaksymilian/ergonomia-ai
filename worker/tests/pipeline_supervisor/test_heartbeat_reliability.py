from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from worker.src import pipeline_supervisor
from worker.src import runtime_state


class _RunningWorker:
    pid = 777

    def __init__(self) -> None:
        self.terminated = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True


def test_heartbeat_permission_error_does_not_stop_supervisor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args, **_kwargs):
        raise PermissionError(5, "Access denied")

    monkeypatch.setattr(pipeline_supervisor, "atomic_write_json", blocked)
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(),
        health_path=tmp_path / "worker-health.json",
        lock_path=tmp_path / "pipeline-supervisor.lock",
    )
    assert supervisor.heartbeat("online") is False
    assert supervisor.runtime_status == "online"
    assert supervisor.health_persistence == "degraded"
    assert supervisor.health_write_failures_consecutive == 1


def test_health_write_failure_does_not_interrupt_running_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline_supervisor,
        "atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError(5, "Access denied")),
    )
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(),
        health_path=tmp_path / "worker-health.json",
        lock_path=tmp_path / "pipeline-supervisor.lock",
    )
    worker = _RunningWorker()
    supervisor.child = worker
    supervisor.analysis_id = "00000000-0000-0000-0000-000000000087"
    supervisor.stage = "pose-v6-rendering-persistent-skeleton"
    assert supervisor.heartbeat("online", state="busy") is False
    assert worker.terminated is False
    assert supervisor.runtime_state == "busy"
    assert supervisor.health_persistence == "degraded"


def test_os_replace_winerror_5_does_not_interrupt_worker_at_87_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "worker-health.json"
    destination.write_text('{"status":"online","generation":1}\n', encoding="utf-8")

    def blocked_replace(*_args, **_kwargs) -> None:
        error = PermissionError(13, "Access denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr(runtime_state.os, "replace", blocked_replace)

    def fast_atomic_write(path, payload, **kwargs):
        return runtime_state.atomic_write_json(
            path,
            payload,
            retry_delays=(0.0, 0.0, 0.0),
            jitter=lambda _start, _end: 0.0,
            **kwargs,
        )

    monkeypatch.setattr(pipeline_supervisor, "atomic_write_json", fast_atomic_write)
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(),
        health_path=destination,
        lock_path=tmp_path / "pipeline-supervisor.lock",
    )
    worker = _RunningWorker()
    supervisor.child = worker
    supervisor.analysis_id = "00000000-0000-0000-0000-000000000087"
    supervisor.stage = "pose-processing-progress-87"

    assert supervisor.heartbeat("online", state="busy") is False
    assert supervisor.runtime_status == "online"
    assert supervisor.runtime_state == "busy"
    assert supervisor.health_write_failures_consecutive == 1
    assert supervisor.health_persistence == "degraded"
    assert worker.terminated is False
    assert json.loads(destination.read_text(encoding="utf-8"))["generation"] == 1
    assert list(tmp_path.glob("worker-health.json.*.tmp")) == []


def test_heartbeat_recovery_resets_consecutive_failures_and_persists_healthy_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "worker-health.json"
    real_write = pipeline_supervisor.atomic_write_json
    calls = 0

    def fail_once(path, payload, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError(5, "Access denied")
        return real_write(path, payload, **kwargs)

    monkeypatch.setattr(pipeline_supervisor, "atomic_write_json", fail_once)
    supervisor = pipeline_supervisor.PipelineSupervisor(
        pipeline_supervisor.SupervisorSettings(),
        health_path=destination,
        lock_path=tmp_path / "pipeline-supervisor.lock",
    )
    assert supervisor.heartbeat("online") is False
    assert supervisor.heartbeat("online") is True
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert supervisor.health_write_failures_consecutive == 0
    assert supervisor.health_persistence == "healthy"
    assert payload["health_persistence"] == "healthy"
    assert payload["health_write_failures_total"] == 1
    assert payload["health_write_failures_consecutive"] == 0
    assert payload["last_health_write_error"] is not None


def test_second_supervisor_does_not_start_duplicate_workers(tmp_path: Path) -> None:
    lock = tmp_path / "pipeline-supervisor.lock"
    first_instance = "instance-first"
    pipeline_supervisor.acquire_lock(
        lock,
        pid=os.getpid(),
        instance_id=first_instance,
        repository_root=pipeline_supervisor.REPOSITORY_ROOT,
    )
    try:
        with pytest.raises(pipeline_supervisor.SupervisorLockError, match="already_running"):
            pipeline_supervisor.acquire_lock(
                lock,
                pid=os.getpid(),
                instance_id="instance-second",
                repository_root=pipeline_supervisor.REPOSITORY_ROOT,
            )
    finally:
        pipeline_supervisor.release_lock(lock, pid=os.getpid(), instance_id=first_instance)
    assert not lock.exists()


def test_release_never_removes_another_supervisor_instance_lock(tmp_path: Path) -> None:
    lock = tmp_path / "pipeline-supervisor.lock"
    pipeline_supervisor.acquire_lock(
        lock,
        pid=os.getpid(),
        instance_id="owner",
        repository_root=pipeline_supervisor.REPOSITORY_ROOT,
    )
    pipeline_supervisor.release_lock(lock, pid=os.getpid(), instance_id="other")
    assert lock.exists()
    pipeline_supervisor.release_lock(lock, pid=os.getpid(), instance_id="owner")
    assert not lock.exists()
