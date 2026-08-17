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

try:
    from scene_detection.processor import (
        DETECTION_VERSION,
        analyze_scene_geometry,
        build_detection_document,
        extract_user_annotations,
        filter_candidates_against_user_annotations,
        normalize_detections,
    )
except ModuleNotFoundError:  # Package import used by pytest and python -m.
    from worker.src.scene_detection.processor import (
        DETECTION_VERSION,
        analyze_scene_geometry,
        build_detection_document,
        extract_user_annotations,
        filter_candidates_against_user_annotations,
        normalize_detections,
    )


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


class SceneWorkerError(RuntimeError):
    def __init__(self, code: str, user_message: str, technical_message: str = "", *, transient: bool = False) -> None:
        super().__init__(technical_message or user_message)
        self.code = code
        self.user_message = user_message
        self.technical_message = sanitize_message(technical_message or user_message)
        self.transient = transient


def sanitize_message(value: object, maximum: int = 500) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    if "supabase.co" in text or "/storage/v1/" in text:
        return "Błąd usługi Supabase/Storage (adres i szczegóły żądania usunięto)."
    return text[:maximum]


def classify_scene_error(error: BaseException, stage: str) -> SceneWorkerError:
    definitions = {
        "claim": ("SCENE_JOB_CLAIM_FAILED", "Nie udało się pobrać zadania analizy sceny.", True),
        "download": ("SCENE_IMAGE_DOWNLOAD_FAILED", "Nie udało się pobrać zdjęcia sceny.", True),
        "context": ("SCENE_CONTEXT_DOWNLOAD_FAILED", "Nie udało się pobrać ręcznych danych sceny.", True),
        "decode": ("SCENE_IMAGE_DECODE_FAILED", "Nie udało się odczytać formatu zdjęcia.", False),
        "detector_init": ("SCENE_DETECTOR_INIT_FAILED", "Nie udało się uruchomić modelu detekcji sceny.", True),
        "detection": ("SCENE_DETECTION_FAILED", "Analiza obiektów na zdjęciu nie powiodła się.", True),
        "geometry": ("SCENE_GEOMETRY_FAILED", "Analiza geometrii sceny nie powiodła się.", False),
        "upload": ("SCENE_RESULT_UPLOAD_FAILED", "Nie udało się zapisać wyniku analizy sceny.", True),
        "complete": ("SCENE_COMPLETE_RPC_FAILED", "Nie udało się zakończyć zadania analizy sceny.", True),
    }
    code, message, transient = definitions.get(stage, ("SCENE_DETECTION_FAILED", "Analiza zdjęcia nie powiodła się.", False))
    return SceneWorkerError(code, message, str(error), transient=transient)


def inference_windows(width: int, height: int, *, tile_size: int = 1600, overlap: float = 0.15) -> list[tuple[int, int, int, int]]:
    """Return one full pass plus bounded overlapping tiles for genuinely large images."""
    if max(width, height) <= 2000:
        return [(0, 0, width, height)]
    stride = max(320, round(tile_size * (1 - overlap)))
    xs = list(range(0, max(1, width - tile_size + 1), stride))
    ys = list(range(0, max(1, height - tile_size + 1), stride))
    if not xs or xs[-1] != max(0, width - tile_size):
        xs.append(max(0, width - tile_size))
    if not ys or ys[-1] != max(0, height - tile_size):
        ys.append(max(0, height - tile_size))
    tiles = [(x, y, min(width, x + tile_size), min(height, y + tile_size)) for y in ys for x in xs]
    return [(0, 0, width, height), *tiles[:9]]


def detector_candidates(detector: YOLOX, image: np.ndarray[Any, Any]) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], int]:
    all_boxes: list[np.ndarray[Any, Any]] = []
    all_ids: list[np.ndarray[Any, Any]] = []
    height, width = image.shape[:2]
    windows = inference_windows(width, height)
    for left, top, right, bottom in windows:
        result = detector(image[top:bottom, left:right])
        boxes, class_ids = result if isinstance(result, tuple) and len(result) == 2 else ([], [])
        box_array = np.asarray(boxes).reshape(-1, 4) if np.asarray(boxes).size else np.empty((0, 4), dtype=float)
        id_array = np.asarray(class_ids).reshape(-1) if np.asarray(class_ids).size else np.empty((0,), dtype=int)
        if box_array.size:
            box_array = box_array.astype(float, copy=True)
            box_array[:, [0, 2]] += left
            box_array[:, [1, 3]] += top
            all_boxes.append(box_array)
            all_ids.append(id_array)
    return (
        np.concatenate(all_boxes) if all_boxes else np.empty((0, 4), dtype=float),
        np.concatenate(all_ids) if all_ids else np.empty((0,), dtype=int),
        len(windows),
    )


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
        try:
            response = self.client.rpc("claim_next_scene_analysis", {"p_worker_id": self.settings.worker_id}).execute()
        except Exception as error:
            raise classify_scene_error(error, "claim") from error
        rows = response.data if isinstance(response.data, list) else []
        return rows[0] if rows and isinstance(rows[0], Mapping) else None

    def detector_instance(self) -> YOLOX:
        if self.detector is None:
            try:
                self.detector = YOLOX(onnx_model=MODEL_URL, model_input_size=(640, 640), mode="multiclass", nms_thr=0.45, score_thr=0.35, backend="onnxruntime", device="cpu")
            except Exception as error:
                raise classify_scene_error(error, "detector_init") from error
        return self.detector

    def process(self, job: Mapping[str, Any]) -> None:
        analysis_id = str(job["id"])
        title = sanitize_message(job.get("title", ""), 120)
        job_dir = DATA_ROOT / analysis_id
        job_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        try:
            for attempt in range(2):
                try:
                    self._process_once(job, job_dir, started, title)
                    return
                except SceneWorkerError as error:
                    if error.transient and attempt == 0:
                        self.logger.warning("analysis_id=%s stage=retry code=%s retry=1", analysis_id, error.code)
                        time.sleep(0.25)
                        continue
                    self._fail(analysis_id, title, error)
                    return
        finally:
            if not self.settings.keep_files:
                shutil.rmtree(job_dir, ignore_errors=True)

    def _process_once(self, job: Mapping[str, Any], job_dir: Path, started: float, title: str) -> None:
        analysis_id = str(job["id"])
        user_id = str(job["user_id"])
        source_path = str(job.get("source_image_path") or "").strip()
        if not source_path:
            raise SceneWorkerError("SCENE_IMAGE_PATH_MISSING", "Brakuje ścieżki zdjęcia źródłowego.")
        try:
            payload = self.client.storage.from_(self.settings.bucket).download(source_path)
        except Exception as error:
            raise classify_scene_error(error, "download") from error
        try:
            if not payload:
                raise ValueError("empty_image_payload")
            (job_dir / "source-image").write_bytes(payload)
            image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None or image.size == 0:
                raise ValueError("invalid_image")
        except (OSError, ValueError, cv2.error) as error:
            raise classify_scene_error(error, "decode") from error
        height, width = image.shape[:2]
        try:
            user_annotations = self._load_user_annotations(analysis_id)
        except Exception as error:
            raise classify_scene_error(error, "context") from error
        try:
            boxes, class_ids, inference_passes = detector_candidates(self.detector_instance(), image)
            candidates = normalize_detections(boxes, class_ids, image_width=width, image_height=height)
            candidates = filter_candidates_against_user_annotations(candidates, user_annotations)
        except SceneWorkerError:
            raise
        except Exception as error:
            raise classify_scene_error(error, "detection") from error
        try:
            geometry = analyze_scene_geometry(image, candidates)
            document = build_detection_document(analysis_id, width, height, candidates, geometry, user_annotations)
            detection_file = job_dir / "scene-detection.json"
            detection_file.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError, cv2.error) as error:
            raise classify_scene_error(error, "geometry") from error
        try:
            preview = image
            if max(width, height) > 1600:
                ratio = 1600 / max(width, height)
                preview = cv2.resize(image, (round(width * ratio), round(height * ratio)), interpolation=cv2.INTER_AREA)
            preview_file = job_dir / "scene-preview.jpg"
            if not cv2.imwrite(str(preview_file), preview, [cv2.IMWRITE_JPEG_QUALITY, 86]):
                raise OSError("preview_write_failed")
            result_path = f"{user_id}/{analysis_id}/results/scene-detection.json"
            preview_path = f"{user_id}/{analysis_id}/preview/scene-preview.jpg"
            self.client.storage.from_(self.settings.bucket).upload(result_path, detection_file.read_bytes(), {"content-type": "application/json", "upsert": "true"})
            self.client.storage.from_(self.settings.bucket).upload(preview_path, preview_file.read_bytes(), {"content-type": "image/jpeg", "upsert": "true"})
        except Exception as error:
            raise classify_scene_error(error, "upload") from error
        try:
            completed = self.client.rpc("complete_scene_detection_v1", {
                "p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id,
                "p_detection_result_path": result_path, "p_preview_image_path": preview_path,
                "p_detection_result": document, "p_detection_version": DETECTION_VERSION,
            }).execute()
            if completed.data is not True:
                raise RuntimeError("worker_lock_lost")
        except Exception as error:
            raise classify_scene_error(error, "complete") from error
        self.logger.info(
            "analysis_id=%s title=%s stage=scene-ready result=%s candidates=%d geometry=%d suggestions=%d inference_passes=%d duration=%.3fs path=%s",
            analysis_id, title, document.get("result_status"), len(candidates), len(document.get("geometry_candidates", [])),
            len(document.get("dimension_suggestions", [])), inference_passes, time.perf_counter() - started, result_path,
        )

    def _load_user_annotations(self, analysis_id: str) -> dict[str, Any]:
        response = self.client.table("photo_scenes").select("scene_state,reconstruction_revision").eq("analysis_id", analysis_id).limit(1).execute()
        rows = response.data if isinstance(response.data, list) else []
        row = rows[0] if rows and isinstance(rows[0], Mapping) else None
        if row is None or not isinstance(row.get("scene_state"), Mapping):
            raise ValueError("scene_state_missing")
        revision = str(row.get("reconstruction_revision") or "").strip() or None
        return extract_user_annotations(row["scene_state"], revision)

    def _fail(self, analysis_id: str, title: str, error: SceneWorkerError) -> None:
        self.logger.error("analysis_id=%s title=%s stage=scene-detection-failed code=%s details=%s", analysis_id, title, error.code, error.technical_message)
        try:
            failed = self.client.rpc("fail_scene_detection", {
                "p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id,
                "p_error_code": error.code, "p_error_message": error.user_message,
            }).execute()
            if failed.data is not True:
                self.logger.error("analysis_id=%s stage=fail-rpc code=SCENE_COMPLETE_RPC_FAILED", analysis_id)
        except Exception as rpc_error:
            self.logger.error("analysis_id=%s stage=fail-rpc code=SCENE_COMPLETE_RPC_FAILED details=%s", analysis_id, sanitize_message(rpc_error))

    def self_test(self) -> int:
        started = time.perf_counter()
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(image, (80, 250), (560, 340), (220, 220, 220), 4)
        encoded_ok, encoded = cv2.imencode(".jpg", image)
        if not encoded_ok:
            raise SceneWorkerError("SCENE_IMAGE_DECODE_FAILED", "Self-test nie zakodował obrazu.")
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if decoded is None:
            raise SceneWorkerError("SCENE_IMAGE_DECODE_FAILED", "Self-test nie odczytał obrazu.")
        boxes, class_ids, _passes = detector_candidates(self.detector_instance(), decoded)
        candidates = normalize_detections(boxes, class_ids, image_width=640, image_height=480)
        geometry = analyze_scene_geometry(decoded, candidates)
        document = build_detection_document("self-test", 640, 480, candidates, geometry)
        self.logger.info("analysis_id=self-test stage=self-test-ok candidates=%d geometry=%d duration=%.3fs", len(candidates), len(document.get("geometry_candidates", [])), time.perf_counter() - started)
        print(f"SELF_TEST=OK DETECTOR=YOLOX-X BACKEND=onnxruntime DEVICE=cpu GEOMETRY={len(document.get('geometry_candidates', []))}")
        return 0

    def run(self, once: bool) -> int:
        while True:
            try:
                job = self.claim()
            except SceneWorkerError as error:
                self.logger.error("stage=claim code=%s details=%s", error.code, error.technical_message)
                if once:
                    return 1
                time.sleep(self.settings.poll_seconds)
                continue
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
    parser.add_argument("--self-test", action="store_true", help="Sprawdź konfigurację, model, decode, inference i geometrię bez kolejki")
    arguments = parser.parse_args(argv)
    try:
        worker = SceneWorker(settings_from_environment(), configure_logging())
        return worker.self_test() if arguments.self_test else worker.run(arguments.once)
    except (OSError, ValueError, SceneWorkerError) as error:
        print(f"Błąd konfiguracji Scene Workera: {sanitize_message(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
