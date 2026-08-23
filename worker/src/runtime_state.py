"""Cross-platform helpers for small local runtime state files.

The runtime health file is diagnostic.  Writes remain atomic, while callers
decide whether an exhausted write is critical or best-effort.
"""

from __future__ import annotations

import errno
import json
import os
import random
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ATOMIC_REPLACE_DELAYS_SECONDS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.40)
WINDOWS_TRANSIENT_ERRORS = frozenset({5, 32, 33})
POSIX_TRANSIENT_ERRORS = frozenset(
    value
    for value in (
        errno.EACCES,
        errno.EAGAIN,
        errno.EBUSY,
        getattr(errno, "ETXTBSY", None),
    )
    if value is not None
)
_ATOMIC_REPLACE_LOCK = threading.Lock()


@dataclass(frozen=True)
class AtomicWriteResult:
    attempts: int
    retries: int


RetryCallback = Callable[[OSError, int, int, float], None]


def is_transient_filesystem_error(error: OSError) -> bool:
    """Return whether a bounded retry is appropriate for the filesystem error."""

    winerror = getattr(error, "winerror", None)
    return (
        isinstance(error, PermissionError)
        or winerror in WINDOWS_TRANSIENT_ERRORS
        or error.errno in POSIX_TRANSIENT_ERRORS
    )


def atomic_write_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    retry_delays: Sequence[float] = ATOMIC_REPLACE_DELAYS_SECONDS,
    on_retry: RetryCallback | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> AtomicWriteResult:
    """Serialize, fsync and atomically replace a JSON document.

    The temporary file is always created beside the destination.  Serialization
    happens before opening it, so programmer errors cannot leave temp debris.
    Exhausted/non-transient errors are deliberately raised to the caller.
    """

    if not retry_delays:
        raise ValueError("retry_delays cannot be empty")
    if any(delay < 0.0 for delay in retry_delays):
        raise ValueError("retry delays cannot be negative")
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
        sort_keys=True,
    )
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        maximum_attempts = len(retry_delays)
        with _ATOMIC_REPLACE_LOCK:
            for attempt, base_delay in enumerate(retry_delays, start=1):
                if base_delay > 0.0:
                    sleep(base_delay + jitter(0.0, min(0.015, base_delay * 0.25)))
                try:
                    os.replace(temporary, destination)
                    return AtomicWriteResult(attempts=attempt, retries=attempt - 1)
                except OSError as error:
                    if not is_transient_filesystem_error(error) or attempt >= maximum_attempts:
                        raise
                    if on_retry is not None:
                        on_retry(
                            error,
                            attempt + 1,
                            maximum_attempts,
                            retry_delays[attempt],
                        )
        raise RuntimeError("atomic write retry loop ended unexpectedly")
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # The destination remains intact. A later startup cleanup handles a
            # temp file that an external Windows process still has open.
            pass


def cleanup_stale_temp_files(
    destination: Path,
    *,
    older_than_seconds: float = 300.0,
    now: float | None = None,
) -> int:
    """Remove only old temp files belonging to one known destination."""

    if older_than_seconds < 0.0:
        raise ValueError("older_than_seconds cannot be negative")
    parent = destination.resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    cutoff = (time.time() if now is None else now) - older_than_seconds
    removed = 0
    for temporary in parent.glob(f"{destination.name}.*.tmp"):
        try:
            if temporary.is_file() and temporary.stat().st_mtime < cutoff:
                temporary.unlink()
                removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            # Fresh runtime operation must not fail because Defender still has
            # an old temp open. It will be retried at the next startup.
            continue
    return removed
