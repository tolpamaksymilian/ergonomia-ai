from __future__ import annotations

import logging
from pathlib import Path

from worker.src import scene_reconstruction_worker


def test_self_test_runs_without_gpu_or_database() -> None:
    assert scene_reconstruction_worker.run_self_test() == 0


def test_once_returns_failure_when_claimed_job_fails() -> None:
    worker = object.__new__(scene_reconstruction_worker.SceneReconstructionWorker)
    worker.settings = scene_reconstruction_worker.Settings("https://example.invalid", "redacted", "analysis-scenes", "test-worker", 1, False)
    worker.logger = logging.getLogger("scene-reconstruction-test")
    worker.claim = lambda: {"id": "00000000-0000-0000-0000-000000000001"}
    worker.process = lambda _job: False
    assert worker.run(True) == 1


def test_sensitive_storage_error_is_redacted() -> None:
    message = scene_reconstruction_worker.sanitize_message("Authorization: Bearer secret https://project.supabase.co/storage/v1/object")
    assert "secret" not in message
    assert "supabase.co" not in message


def test_worker_has_no_gpu_or_video_runtime_imports() -> None:
    source = Path(scene_reconstruction_worker.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("import torch", "import cv2", "onnxruntime", "ffmpeg", "mediapipe"):
        assert forbidden not in source
