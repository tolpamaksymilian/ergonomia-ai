from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from worker.src import runtime_state


def _replace_failures(monkeypatch: pytest.MonkeyPatch, failure_count: int) -> list[int]:
    original = runtime_state.os.replace
    attempts: list[int] = []

    def flaky(source: Path, destination: Path) -> None:
        attempts.append(1)
        if len(attempts) <= failure_count:
            raise PermissionError(5, "Access denied")
        original(source, destination)

    monkeypatch.setattr(runtime_state.os, "replace", flaky)
    return attempts


def test_atomic_write_retries_winerror_5_then_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _replace_failures(monkeypatch, 1)
    destination = tmp_path / "worker-health.json"
    result = runtime_state.atomic_write_json(
        destination,
        {"status": "online"},
        retry_delays=(0.0, 0.0),
        jitter=lambda _start, _end: 0.0,
    )
    assert result.retries == 1
    assert len(attempts) == 2
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "online"


def test_atomic_write_multiple_retries_cleanup_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _replace_failures(monkeypatch, 3)
    destination = tmp_path / "worker-health.json"
    result = runtime_state.atomic_write_json(
        destination,
        {"generation": 4},
        retry_delays=(0.0, 0.0, 0.0, 0.0),
        jitter=lambda _start, _end: 0.0,
    )
    assert result.attempts == 4
    assert len(attempts) == 4
    assert list(tmp_path.glob("worker-health.json.*.tmp")) == []


def test_retry_exhausted_preserves_old_destination_and_raises_for_critical_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "worker-health.json"
    destination.write_text('{"generation":1}\n', encoding="utf-8")
    _replace_failures(monkeypatch, 99)
    with pytest.raises(PermissionError):
        runtime_state.atomic_write_json(
            destination,
            {"generation": 2},
            retry_delays=(0.0, 0.0),
            jitter=lambda _start, _end: 0.0,
        )
    assert json.loads(destination.read_text(encoding="utf-8")) == {"generation": 1}
    assert list(tmp_path.glob("worker-health.json.*.tmp")) == []


def test_startup_cleanup_removes_only_old_health_temp(tmp_path: Path) -> None:
    destination = tmp_path / "worker-health.json"
    old = tmp_path / "worker-health.json.old.tmp"
    fresh = tmp_path / "worker-health.json.fresh.tmp"
    unrelated = tmp_path / "other.json.old.tmp"
    for item in (old, fresh, unrelated):
        item.write_text("temp", encoding="utf-8")
    old.touch()
    fresh.touch()
    unrelated.touch()
    old_time = time.time() - 600
    runtime_state.os.utime(old, (old_time, old_time))
    runtime_state.os.utime(unrelated, (old_time, old_time))
    assert runtime_state.cleanup_stale_temp_files(destination, older_than_seconds=300.0) == 1
    assert not old.exists()
    assert fresh.exists()
    assert unrelated.exists()


def test_concurrent_atomic_writers_and_readers_never_observe_partial_json(tmp_path: Path) -> None:
    destination = tmp_path / "worker-health.json"
    runtime_state.atomic_write_json(destination, {"writer": 0, "generation": 0})
    errors: list[BaseException] = []
    stop = threading.Event()

    def writer(writer_id: int) -> None:
        try:
            for generation in range(50):
                runtime_state.atomic_write_json(destination, {"writer": writer_id, "generation": generation})
        except BaseException as error:  # captured and asserted in the main test thread
            errors.append(error)

    def reader() -> None:
        try:
            while not stop.is_set():
                try:
                    payload = json.loads(destination.read_text(encoding="utf-8"))
                except PermissionError:
                    # Windows may briefly deny the open itself. This is a read
                    # availability event, not a partial-JSON observation.
                    time.sleep(0.001)
                    continue
                assert isinstance(payload["writer"], int)
                assert isinstance(payload["generation"], int)
                time.sleep(0.0005)
        except BaseException as error:  # captured and asserted in the main test thread
            errors.append(error)

    with ThreadPoolExecutor(max_workers=8) as executor:
        readers = [executor.submit(reader) for _ in range(4)]
        writers = [executor.submit(writer, writer_id) for writer_id in range(4)]
        for future in writers:
            future.result()
        stop.set()
        for future in readers:
            future.result()
    assert errors == []
    assert list(tmp_path.glob("worker-health.json.*.tmp")) == []
