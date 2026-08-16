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

from dotenv import load_dotenv
from supabase import Client, create_client

try:
    from scene_reconstruction.processor import (
        CONSTRAINT_GRAPH_VERSION,
        RECONSTRUCTION_VERSION,
        ReconstructionInputError,
        build_reconstruction_input,
        reconstruct_scene,
        reconstruction_summary,
    )
except ModuleNotFoundError:
    from worker.src.scene_reconstruction.processor import (
        CONSTRAINT_GRAPH_VERSION,
        RECONSTRUCTION_VERSION,
        ReconstructionInputError,
        build_reconstruction_input,
        reconstruct_scene,
        reconstruction_summary,
    )


WORKER_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_ROOT / ".env"
DATA_ROOT = WORKER_ROOT / "data" / "scene-reconstruction-jobs"
LOG_ROOT = WORKER_ROOT / "logs"


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    secret_key: str
    bucket: str
    worker_id: str
    poll_seconds: float
    keep_files: bool


class SceneReconstructionWorkerError(RuntimeError):
    def __init__(self, code: str, user_message: str, technical_message: str = "", *, transient: bool = False) -> None:
        super().__init__(technical_message or user_message)
        self.code = code
        self.user_message = user_message
        self.technical_message = sanitize_message(technical_message or user_message)
        self.transient = transient


def sanitize_message(value: object, maximum: int = 500) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    if "supabase.co" in text or "/storage/v1/" in text or "authorization" in text.lower():
        return "Błąd Supabase/Storage (adres i szczegóły żądania usunięto)."
    return text[:maximum]


def classify_error(error: BaseException, stage: str) -> SceneReconstructionWorkerError:
    definitions = {
        "claim": ("SCENE_RECONSTRUCTION_CLAIM_FAILED", "Nie udało się pobrać zadania rekonstrukcji.", True),
        "input": ("SCENE_RECONSTRUCTION_INPUT_INVALID", "Dane geometrii sceny wymagają uzupełnienia lub poprawy.", False),
        "solve": ("SCENE_RECONSTRUCTION_SOLVER_FAILED", "Nie udało się dopasować geometrii sceny.", False),
        "write": ("SCENE_RECONSTRUCTION_WRITE_FAILED", "Nie udało się przygotować artefaktu rekonstrukcji.", False),
        "upload": ("SCENE_RECONSTRUCTION_UPLOAD_FAILED", "Nie udało się zapisać wyniku rekonstrukcji.", True),
        "complete": ("SCENE_RECONSTRUCTION_LOCK_LOST", "Worker utracił blokadę zadania rekonstrukcji.", True),
    }
    code, message, transient = definitions.get(stage, ("SCENE_RECONSTRUCTION_FAILED", "Rekonstrukcja sceny nie powiodła się.", False))
    return SceneReconstructionWorkerError(code, message, str(error), transient=transient)


def settings_from_environment() -> Settings:
    load_dotenv(ENV_PATH, override=False)
    required = {name: os.getenv(name, "").strip() for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing_environment_variable:{','.join(missing)}")
    worker_id = os.getenv("SCENE_RECONSTRUCTION_WORKER_ID", "local-scene-reconstruction-worker-01").strip()
    if not worker_id:
        raise ValueError("SCENE_RECONSTRUCTION_WORKER_ID nie może być pusty")
    return Settings(
        required["SUPABASE_URL"], required["SUPABASE_SECRET_KEY"],
        os.getenv("ANALYSIS_SCENES_BUCKET", "analysis-scenes").strip() or "analysis-scenes",
        worker_id, max(1.0, float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "10"))),
        os.getenv("KEEP_WORKER_FILES", "false").strip().lower() in {"1", "true", "yes"},
    )


def configure_logging() -> logging.Logger:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("scene-reconstruction-worker")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(LOG_ROOT / "scene-reconstruction-worker.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class SceneReconstructionWorker:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger
        self.client: Client = create_client(settings.supabase_url, settings.secret_key)

    def claim(self) -> Mapping[str, Any] | None:
        try:
            response = self.client.rpc("claim_next_scene_reconstruction", {"p_worker_id": self.settings.worker_id}).execute()
        except Exception as error:
            raise classify_error(error, "claim") from error
        rows = response.data if isinstance(response.data, list) else []
        return rows[0] if rows and isinstance(rows[0], Mapping) else None

    def process(self, job: Mapping[str, Any]) -> bool:
        analysis_id = str(job.get("id", ""))
        title = sanitize_message(job.get("title", ""), 120)
        job_dir = DATA_ROOT / analysis_id
        job_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        try:
            for attempt in range(2):
                try:
                    self._process_once(job, job_dir, started, title)
                    return True
                except SceneReconstructionWorkerError as error:
                    if error.transient and attempt == 0:
                        self.logger.warning("analysis_id=%s stage=retry code=%s retry=1", analysis_id, error.code)
                        time.sleep(.25)
                        continue
                    self._fail(analysis_id, title, error)
                    return False
        finally:
            if not self.settings.keep_files:
                shutil.rmtree(job_dir, ignore_errors=True)

    def _process_once(self, job: Mapping[str, Any], job_dir: Path, started: float, title: str) -> None:
        analysis_id = str(job.get("id", ""))
        user_id = str(job.get("user_id", ""))
        revision = str(job.get("scene_revision", ""))
        scene_state = job.get("scene_state")
        detection_result = job.get("detection_result")
        if not isinstance(scene_state, Mapping):
            raise classify_error(ReconstructionInputError("scene_state_missing"), "input")
        try:
            input_document = build_reconstruction_input(
                scene_state,
                detection_result if isinstance(detection_result, Mapping) else None,
                scene_revision=revision,
                image_width=int(job.get("image_width") or 0),
                image_height=int(job.get("image_height") or 0),
            )
        except (ReconstructionInputError, TypeError, ValueError) as error:
            raise classify_error(error, "input") from error
        try:
            result = reconstruct_scene(input_document)
        except (ArithmeticError, ReconstructionInputError, TypeError, ValueError) as error:
            raise classify_error(error, "solve") from error
        self._heartbeat(analysis_id)
        input_file = job_dir / "scene-reconstruction-input.json"
        output_file = job_dir / "scene-reconstruction.json"
        try:
            input_file.write_text(json.dumps(input_document, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        except (OSError, TypeError, ValueError) as error:
            raise classify_error(error, "write") from error
        input_path = f"{user_id}/{analysis_id}/results/scene-reconstruction-input.json"
        result_path = f"{user_id}/{analysis_id}/results/scene-reconstruction.json"
        try:
            self.client.storage.from_(self.settings.bucket).upload(input_path, input_file.read_bytes(), {"content-type": "application/json", "upsert": "true"})
            self.client.storage.from_(self.settings.bucket).upload(result_path, output_file.read_bytes(), {"content-type": "application/json", "upsert": "true"})
        except Exception as error:
            raise classify_error(error, "upload") from error
        self._heartbeat(analysis_id)
        try:
            response = self.client.rpc("complete_scene_reconstruction_v1", {
                "p_analysis_id": analysis_id,
                "p_worker_id": self.settings.worker_id,
                "p_input_path": input_path,
                "p_result_path": result_path,
                "p_reconstruction_version": RECONSTRUCTION_VERSION,
                "p_scene_revision": revision,
                "p_result_status": result["status"],
                "p_reconstruction_summary": reconstruction_summary(result),
            }).execute()
            if response.data is not True:
                raise RuntimeError("worker_lock_lost")
        except Exception as error:
            raise classify_error(error, "complete") from error
        self.logger.info(
            "analysis_id=%s title=%s stage=%s regions=%d objects=%d constraints=%d outliers=%d repairs=%d duration=%.3fs path=%s",
            analysis_id, title, result["status"], result["input"]["regionCount"], result["input"]["objectCount"],
            result["input"]["constraintCount"], len(result["outlierConstraintIds"]), len(result["autoRepairs"]),
            time.perf_counter() - started, result_path,
        )

    def _heartbeat(self, analysis_id: str) -> None:
        try:
            response = self.client.rpc("heartbeat_scene_reconstruction", {"p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id}).execute()
            if response.data is not True:
                raise RuntimeError("worker_lock_lost")
        except Exception as error:
            raise classify_error(error, "complete") from error

    def _fail(self, analysis_id: str, title: str, error: SceneReconstructionWorkerError) -> None:
        self.logger.error("analysis_id=%s title=%s stage=failed code=%s details=%s", analysis_id, title, error.code, error.technical_message)
        try:
            response = self.client.rpc("fail_scene_reconstruction", {
                "p_analysis_id": analysis_id, "p_worker_id": self.settings.worker_id,
                "p_error_code": error.code, "p_error_message": error.user_message,
            }).execute()
            if response.data is not True:
                self.logger.error("analysis_id=%s stage=fail-rpc code=SCENE_RECONSTRUCTION_LOCK_LOST", analysis_id)
        except Exception as rpc_error:
            self.logger.error("analysis_id=%s stage=fail-rpc code=SCENE_RECONSTRUCTION_FAIL_RPC details=%s", analysis_id, sanitize_message(rpc_error))

    def run(self, once: bool) -> int:
        while True:
            try:
                job = self.claim()
            except SceneReconstructionWorkerError as error:
                self.logger.error("stage=claim code=%s details=%s", error.code, error.technical_message)
                if once:
                    return 1
                time.sleep(self.settings.poll_seconds)
                continue
            if job is None:
                self.logger.info("Brak scen gotowych do rekonstrukcji.")
                if once:
                    return 0
                time.sleep(self.settings.poll_seconds)
                continue
            succeeded = self.process(job)
            if once:
                return 0 if succeeded else 1


def run_self_test() -> int:
    point = lambda x, y: {"raw": {"x": x, "y": y}, "snapped": None, "effective": {"x": x, "y": y}, "snapSourceId": None, "snapDistancePx": None}
    scene = {
        "schema_version": "1.5", "objects": [{"id": "table", "name": "Blat", "status": "USER_CONFIRMED", "shapeAssumptions": ["RECTANGULAR", "PLANAR"]}],
        "regions": [{"id": "floor", "type": "FLOOR_REGION", "quality": "HIGH", "polygonImageNormalized": [point(.1, .7), point(.9, .7), point(.95, .95), point(.05, .95)]}, {"id": "top", "type": "WORK_SURFACE", "associatedObjectId": "table", "quality": "HIGH", "polygonImageNormalized": [point(.2, .3), point(.8, .3), point(.7, .5), point(.25, .5)]}],
        "planes": [], "calibration": {"references": []},
        "constraintGraph": {"version": CONSTRAINT_GRAPH_VERSION, "nodes": [], "constraints": [
            {"id": "h", "type": "HEIGHT", "objectId": "table", "rawValue": 80, "effectiveValue": 80, "source": "USER_PROVIDED", "weight": 1, "useForSolver": True, "status": "ACTIVE", "imageSegment": {"start": {"x": .3, "y": .8}, "end": {"x": .3, "y": .6}}},
            {"id": "w", "type": "WIDTH", "objectId": "table", "rawValue": 160, "effectiveValue": 160, "source": "USER_PROVIDED", "weight": 1, "useForSolver": True, "status": "ACTIVE", "imageSegment": None},
            {"id": "d", "type": "DEPTH", "objectId": "table", "rawValue": 70, "effectiveValue": 70, "source": "USER_PROVIDED", "weight": 1, "useForSolver": True, "status": "ACTIVE", "imageSegment": None},
        ]},
    }
    source = build_reconstruction_input(scene, None, scene_revision="self-test", image_width=1200, image_height=900)
    result = reconstruct_scene(source)
    if result["derivedDimensions"]["table"] != {"heightCm": 80.0, "widthCm": 160.0, "depthCm": 70.0}:
        raise SceneReconstructionWorkerError("SCENE_RECONSTRUCTION_SELF_TEST_FAILED", "Self-test rekonstrukcji nie przeszedł.")
    print(f"SELF_TEST=OK ENGINE={RECONSTRUCTION_VERSION} STATUS={result['status']} DEVICE=cpu")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Ergonomia AI {RECONSTRUCTION_VERSION}")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.self_test:
            return run_self_test()
        return SceneReconstructionWorker(settings_from_environment(), configure_logging()).run(arguments.once)
    except (OSError, ValueError, SceneReconstructionWorkerError) as error:
        print(f"Błąd konfiguracji Scene Reconstruction Workera: {sanitize_message(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
