from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from dotenv import load_dotenv
from rtmlib import YOLOX
from supabase import Client, create_client

from scene_detection.processor import DETECTION_VERSION, analyze_scene_geometry, build_detection_document, normalize_detections


WORKER_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_ROOT / ".env"
DATA_ROOT = WORKER_ROOT / "data" / "scene-jobs"
LOG_ROOT = WORKER_ROOT / "logs"
MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_x.onnx"


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    secret_key: str
    bucket: str
    worker_id: str
    poll_seconds: float
    keep_files: bool


def settings_from_environment() -> Settings:
    load_dotenv(ENV_PATH, override=False)
    required = {name: os.getenv(name, "").strip() for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing_environment_variable:{','.join(missing)}")
    worker_id = os.getenv("SCENE_WORKER_ID", "local-scene-worker-01").strip()
    if not worker_id:
        raise ValueError("SCENE_WORKER_ID nie może być pusty")
    return Settings(
        required["SUPABASE_URL"], required["SUPABASE_SECRET_KEY"],
        os.getenv("ANALYSIS_SCENES_BUCKET", "analysis-scenes").strip() or "analysis-scenes",
        worker_id, max(1.0, float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "10"))),
        os.getenv("KEEP_WORKER_FILES", "false").strip().lower() in {"1", "true", "yes"},
    )


def configure_logging() -> logging.Logger:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("scene-worker")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(LOG_ROOT / "scene-worker.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class SceneWorker:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger
        self.client: Client = create_client(settings.supabase_url, settings.secret_key)
        self.detector: YOLOX | None = None

    def claim(self) -> Mapping[str, Any] | None:
        response = self.client.rpc("claim_next_scene_analysis", {"p_worker_id": self.settings.worker_id}).execute()
        rows = response.data if isinstance(response.data, list) else []
        return rows[0] if rows and isinstance(rows[0], Mapping) else None

    def detector_instance(self) -> YOLOX:
        if self.detector is None:
            self.detector = YOLOX(onnx_model=MODEL_URL, model_input_size=(640, 640), mode="multiclass", nms_thr=0.45, score_thr=0.35, backend="onnxruntime", device="cpu")
        return self.detector

    def process(self, job: Mapping[str, Any]) -> None:
        analysis_id = str(job["id"])
        user_id = str(job["user_id"])
        source_path = str(job["source_image_path"])
        job_dir = DATA_ROOT / analysis_id
        job_dir.mkdir(parents=True, exist_ok=True)
        source_file = job_dir / "source-image"
        detection_file = job_dir / "scene-detection.json"
        preview_file = job_dir / "scene-preview.jpg"
        started = time.perf_counter()
        try:
            payload = self.client.storage.from_(self.settings.bucket).download(source_path)
            if not payload:
                raise RuntimeError("EMPTY_IMAGE")
            source_file.write_bytes(payload)
            encoded = np.frombuffer(payload, dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if image is None or image.size == 0:
                raise RuntimeError("INVALID_IMAGE")
            height, width = image.shape[:2]
            result = self.detector_instance()(image)
            boxes, class_ids = result if isinstance(result, tuple) and len(result) == 2 else ([], [])
            candidates = normalize_detections(np.asarray(boxes).reshape(-1, 4) if np.asarray(boxes).size else [], np.asarray(class_ids).reshape(-1), image_width=width, image_height=height)
            geometry_analysis = analyze_scene_geometry(image, candidates)
            document = build_detection_document(analysis_id, width, height, candidates, geometry_analysis)
            detection_file.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            preview = image.copy()
            maximum = 1600
            if max(width, height) > maximum:
                ratio = maximum / max(width, height)
                preview = cv2.resize(preview, (round(width * ratio), round(height * ratio)), interpolation=cv2.INTER_AREA)
            if not cv2.imwrite(str(preview_file), preview, [cv2.IMWRITE_JPEG_QUALITY, 86]):
                raise RuntimeError("PREVIEW_WRITE_FAILED")
            result_path = f"{user_id}/{analysis_id}/results/scene-detection.json"
            preview_path = f"{user_id}/{analysis_id}/preview/scene-preview.jpg"
            self.client.storage.from_(self.settings.bucket).upload(result_path, detection_file.read_bytes(), {"content-type": "application/json", "upsert": "true"})
            self.client.storage.from_(self.settings.bucket).upload(preview_path, preview_file.read_bytes(), {"content-type": "image/jpeg", "upsert": "true"})
            completed = self.client.rpc("complete_scene_detection_v1", {
                "p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id,
                "p_detection_result_path": result_path, "p_preview_image_path": preview_path,
                "p_detection_result": document, "p_detection_version": DETECTION_VERSION,
            }).execute()
            if completed.data is not True:
                raise RuntimeError("WORKER_LOCK_LOST")
            self.logger.info("analysis_id=%s stage=scene-ready candidates=%d geometry=%d suggestions=%d duration=%.3fs path=%s", analysis_id, len(candidates), len(document.get("geometry_candidates", [])), len(document.get("dimension_suggestions", [])), time.perf_counter() - started, result_path)
        except (OSError, ValueError, RuntimeError, cv2.error) as error:
            self.logger.error("analysis_id=%s stage=scene-detection-failed code=%s", analysis_id, type(error).__name__)
            self.client.rpc("fail_scene_detection", {"p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id, "p_error_code": type(error).__name__.upper(), "p_error_message": str(error)[:500]}).execute()
        except Exception as error:  # Supabase and RTMLib expose no shared stable exception base.
            self.logger.exception("analysis_id=%s stage=scene-detection-failed", analysis_id)
            self.client.rpc("fail_scene_detection", {"p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id, "p_error_code": "SCENE_WORKER_ERROR", "p_error_message": type(error).__name__}).execute()
        finally:
            if not self.settings.keep_files:
                shutil.rmtree(job_dir, ignore_errors=True)

    def run(self, once: bool) -> int:
        while True:
            job = self.claim()
            if job is None:
                self.logger.info("Brak analiz PHOTO_SCENE gotowych do detekcji.")
                if once:
                    return 0
                time.sleep(self.settings.poll_seconds)
                continue
            self.process(job)
            if once:
                return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Ergonomia AI {DETECTION_VERSION}")
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        return SceneWorker(settings_from_environment(), configure_logging()).run(arguments.once)
    except (OSError, ValueError) as error:
        print(f"Błąd konfiguracji Scene Workera: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
