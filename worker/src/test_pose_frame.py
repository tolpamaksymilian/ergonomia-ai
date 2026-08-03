from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

# Import torch musi znajdować się przed onnxruntime,
# aby biblioteki CUDA i cuDNN zostały załadowane.
import onnxruntime as ort

from dotenv import load_dotenv
from rtmlib import Wholebody, draw_skeleton
from supabase import Client, create_client


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"

TEMP_DIRECTORY = (
    WORKER_DIRECTORY
    / "data"
    / "pose-test"
)

OUTPUT_DIRECTORY = (
    WORKER_DIRECTORY
    / "outputs"
    / "pose-test"
)

FRAME_RATIOS = (
    0.20,
    0.35,
    0.50,
    0.65,
    0.80,
)


def get_required_environment_variable(
    name: str,
) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Brakuje wymaganej zmiennej środowiskowej: {name}"
        )

    return value


def create_supabase_client() -> Client:
    return create_client(
        get_required_environment_variable(
            "SUPABASE_URL"
        ),
        get_required_environment_variable(
            "SUPABASE_SECRET_KEY"
        ),
    )


def get_ready_analysis(
    supabase: Client,
) -> dict[str, Any] | None:
    response = (
        supabase.table("analyses")
        .select(
            """
            id,
            title,
            source_video_path,
            source_file_name,
            source_frame_count,
            source_width,
            source_height,
            processing_stage,
            created_at
            """
        )
        .eq(
            "processing_stage",
            "ready-for-ai",
        )
        .order(
            "created_at",
            desc=False,
        )
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def download_video(
    supabase: Client,
    analysis: dict[str, Any],
) -> Path:
    bucket_name = os.getenv(
        "ANALYSIS_BUCKET",
        "analysis-videos",
    ).strip()

    source_path = str(
        analysis["source_video_path"]
    )

    source_name = str(
        analysis.get("source_file_name")
        or "source.mp4"
    )

    suffix = Path(source_name).suffix.lower()

    if suffix not in {
        ".mp4",
        ".mov",
        ".webm",
    }:
        suffix = ".mp4"

    TEMP_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        TEMP_DIRECTORY
        / f"{analysis['id']}{suffix}"
    )

    print("Pobieranie prywatnego filmu...")

    content = (
        supabase.storage
        .from_(bucket_name)
        .download(source_path)
    )

    destination.write_bytes(content)

    if destination.stat().st_size <= 0:
        raise RuntimeError(
            "Pobrany film jest pusty."
        )

    print(
        "Pobrano:",
        f"{destination.stat().st_size / 1024 / 1024:.2f} MB",
    )

    return destination


def read_frame_at_ratio(
    capture: cv2.VideoCapture,
    frame_count: int,
    ratio: float,
) -> np.ndarray:
    frame_index = min(
        frame_count - 1,
        max(
            0,
            int(frame_count * ratio),
        ),
    )

    capture.set(
        cv2.CAP_PROP_POS_FRAMES,
        frame_index,
    )

    success, frame = capture.read()

    if (
        not success
        or frame is None
        or frame.size == 0
    ):
        raise RuntimeError(
            f"Nie udało się odczytać klatki {frame_index}."
        )

    return frame


def count_confident_keypoints(
    scores: np.ndarray,
    threshold: float = 0.35,
) -> int:
    if scores.size == 0:
        return 0

    return int(
        np.count_nonzero(
            scores >= threshold
        )
    )


def main() -> int:
    print(
        "Ergonomia AI — test RTMW "
        "na pojedynczych klatkach"
    )

    if not ENV_PATH.exists():
        print(
            "BŁĄD: Nie znaleziono worker/.env",
            file=sys.stderr,
        )
        return 1

    load_dotenv(ENV_PATH)

    try:
        providers = (
            ort.get_available_providers()
        )

        print("\n=== ŚRODOWISKO ===")
        print(f"PyTorch: {torch.__version__}")
        print(
            f"ONNX Runtime: {ort.__version__}"
        )
        print(f"Dostawcy: {providers}")

        if (
            "CUDAExecutionProvider"
            not in providers
        ):
            raise RuntimeError(
                "ONNX Runtime nie wykrywa "
                "CUDAExecutionProvider."
            )

        print(
            "GPU:",
            torch.cuda.get_device_name(0),
        )

        supabase = (
            create_supabase_client()
        )

        analysis = get_ready_analysis(
            supabase
        )

        if analysis is None:
            print(
                "Brak analizy z etapem "
                "ready-for-ai."
            )
            return 0

        analysis_id = str(
            analysis["id"]
        )

        print("\n=== ANALIZA ===")
        print(f"ID: {analysis_id}")
        print(f"Tytuł: {analysis['title']}")
        print(
            "Etap:",
            analysis["processing_stage"],
        )

        video_path = download_video(
            supabase,
            analysis,
        )

        capture = cv2.VideoCapture(
            str(video_path)
        )

        if not capture.isOpened():
            raise RuntimeError(
                "OpenCV nie może otworzyć filmu."
            )

        frame_count = int(
            capture.get(
                cv2.CAP_PROP_FRAME_COUNT
            )
        )

        if frame_count <= 0:
            raise RuntimeError(
                "Film nie zawiera poprawnej "
                "liczby klatek."
            )

        print("\n=== MODEL ===")
        print(
            "Inicjalizacja modelu Wholebody "
            "w trybie balanced..."
        )
        print(
            "Pierwsze uruchomienie może pobrać "
            "modele ONNX."
        )

        initialization_start = (
            time.perf_counter()
        )

        wholebody = Wholebody(
            to_openpose=False,
            mode="balanced",
            backend="onnxruntime",
            device="cuda",
        )

        print(
            "Inicjalizacja:",
            f"{time.perf_counter() - initialization_start:.2f} s",
        )

        best_frame: np.ndarray | None = None
        best_keypoints: np.ndarray | None = None
        best_scores: np.ndarray | None = None
        best_confident_count = -1
        best_ratio = 0.0
        best_inference_time = 0.0

        print("\n=== INFERENCJA ===")

        for ratio in FRAME_RATIOS:
            frame = read_frame_at_ratio(
                capture=capture,
                frame_count=frame_count,
                ratio=ratio,
            )

            inference_start = (
                time.perf_counter()
            )

            keypoints, scores = wholebody(
                frame
            )

            inference_time = (
                time.perf_counter()
                - inference_start
            )

            keypoints_array = np.asarray(
                keypoints
            )

            scores_array = np.asarray(
                scores
            )

            confident_count = (
                count_confident_keypoints(
                    scores_array,
                )
            )

            people_count = (
                int(keypoints_array.shape[0])
                if keypoints_array.ndim >= 3
                else 0
            )

            print(
                f"Klatka {ratio:>4.0%}: "
                f"osoby={people_count}, "
                f"pewne punkty={confident_count}, "
                f"czas={inference_time:.3f} s"
            )

            if (
                confident_count
                > best_confident_count
            ):
                best_frame = frame.copy()
                best_keypoints = (
                    keypoints_array.copy()
                )
                best_scores = (
                    scores_array.copy()
                )
                best_confident_count = (
                    confident_count
                )
                best_ratio = ratio
                best_inference_time = (
                    inference_time
                )

        capture.release()

        if (
            best_frame is None
            or best_keypoints is None
            or best_scores is None
        ):
            raise RuntimeError(
                "Model nie zwrócił wyniku."
            )

        if best_confident_count <= 0:
            raise RuntimeError(
                "Nie wykryto żadnych "
                "wiarygodnych punktów ciała."
            )

        output_image = draw_skeleton(
            best_frame.copy(),
            best_keypoints,
            best_scores,
            openpose_skeleton=False,
            kpt_thr=0.35,
        )

        OUTPUT_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            OUTPUT_DIRECTORY
            / f"{analysis_id}-pose.jpg"
        )

        saved = cv2.imwrite(
            str(output_path),
            output_image,
        )

        if not saved:
            raise RuntimeError(
                "Nie udało się zapisać "
                "obrazu wynikowego."
            )

        people_count = (
            int(best_keypoints.shape[0])
            if best_keypoints.ndim >= 3
            else 0
        )

        print("\n=== NAJLEPSZY WYNIK ===")
        print(
            "Pozycja filmu:",
            f"{best_ratio:.0%}",
        )
        print(
            "Wykryte osoby:",
            people_count,
        )
        print(
            "Pewne punkty:",
            best_confident_count,
        )
        print(
            "Czas inferencji:",
            f"{best_inference_time:.3f} s",
        )
        print(
            "Kształt keypoints:",
            best_keypoints.shape,
        )
        print(
            "Kształt scores:",
            best_scores.shape,
        )
        print(
            "Zapisano obraz:",
            output_path,
        )

        print("\n=== WYNIK ===")
        print(
            "Model pozy wykrył człowieka "
            "i zapisał klatkę ze szkieletem."
        )
        print(
            "Rekord analizy w Supabase "
            "nie został zmieniony."
        )

        return 0

    except Exception as error:
        print("\n=== BŁĄD ===", file=sys.stderr)
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    finally:
        if TEMP_DIRECTORY.exists():
            shutil.rmtree(
                TEMP_DIRECTORY,
                ignore_errors=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())