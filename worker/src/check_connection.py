from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import cv2
import torch
from dotenv import load_dotenv
from supabase import Client, create_client


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"
DATA_DIRECTORY = WORKER_DIRECTORY / "data" / "connection-test"


def get_required_environment_variable(name: str) -> str:
    """Pobiera wymaganą zmienną środowiskową."""

    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Brakuje wymaganej zmiennej środowiskowej: {name}"
        )

    return value


def create_supabase_client() -> Client:
    """Tworzy serwerowego klienta Supabase."""

    supabase_url = get_required_environment_variable(
        "SUPABASE_URL"
    )

    supabase_secret_key = get_required_environment_variable(
        "SUPABASE_SECRET_KEY"
    )

    return create_client(
        supabase_url,
        supabase_secret_key,
    )


def print_gpu_information() -> None:
    """Sprawdza dostępność akceleracji CUDA."""

    print("\n=== GPU ===")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA runtime: {torch.version.cuda}")
    print(f"CUDA dostępna: {torch.cuda.is_available()}")

    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(
            "Capability:",
            torch.cuda.get_device_capability(0),
        )
    else:
        print("GPU: BRAK")


def get_next_queued_analysis(
    supabase: Client,
) -> dict[str, Any] | None:
    """
    Pobiera najstarszą analizę oczekującą w kolejce.

    Funkcja niczego nie blokuje i nie zmienia w bazie.
    Jest przeznaczona wyłącznie do pierwszego testu.
    """

    response = (
        supabase.table("analyses")
        .select(
            """
            id,
            user_id,
            title,
            status,
            source_video_path,
            source_file_name,
            source_mime_type,
            source_size_bytes,
            created_at
            """
        )
        .eq("status", "queued")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def download_analysis_video(
    supabase: Client,
    analysis: dict[str, Any],
    bucket_name: str,
) -> Path:
    """Pobiera prywatny film do lokalnego katalogu workera."""

    analysis_id = str(analysis["id"])
    source_video_path = str(
        analysis["source_video_path"]
    )

    original_file_name = str(
        analysis.get("source_file_name")
        or "source-video.mp4"
    )

    suffix = Path(original_file_name).suffix.lower()

    if not suffix:
        suffix = ".mp4"

    DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_path = (
        DATA_DIRECTORY
        / f"{analysis_id}{suffix}"
    )

    print("\n=== STORAGE ===")
    print(f"Bucket: {bucket_name}")
    print(f"Ścieżka: {source_video_path}")
    print("Pobieranie filmu...")

    file_content = (
        supabase.storage
        .from_(bucket_name)
        .download(source_video_path)
    )

    destination_path.write_bytes(file_content)

    print(f"Zapisano: {destination_path}")
    print(
        "Rozmiar lokalny:",
        f"{destination_path.stat().st_size / 1024 / 1024:.2f} MB",
    )

    return destination_path


def read_video_metadata(
    video_path: Path,
) -> dict[str, int | float | None]:
    """Odczytuje techniczne parametry filmu przez OpenCV."""

    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise RuntimeError(
            "OpenCV nie może otworzyć pobranego filmu."
        )

    try:
        fps = float(
            capture.get(cv2.CAP_PROP_FPS)
        )

        frame_count = int(
            capture.get(cv2.CAP_PROP_FRAME_COUNT)
        )

        width = int(
            capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        )

        height = int(
            capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        )

        duration_seconds = (
            frame_count / fps
            if fps > 0
            else None
        )

        return {
            "fps": round(fps, 3),
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration_seconds": (
                round(duration_seconds, 3)
                if duration_seconds is not None
                else None
            ),
        }
    finally:
        capture.release()


def main() -> int:
    """Uruchamia test infrastruktury workera."""

    print("Ergonomia AI — test połączenia workera")
    print(f"Plik konfiguracji: {ENV_PATH}")

    if not ENV_PATH.exists():
        print(
            "BŁĄD: Nie znaleziono worker/.env",
            file=sys.stderr,
        )

        return 1

    load_dotenv(ENV_PATH)

    try:
        print_gpu_information()

        bucket_name = os.getenv(
            "ANALYSIS_BUCKET",
            "analysis-videos",
        ).strip()

        supabase = create_supabase_client()

        print("\n=== SUPABASE ===")
        print("Klient Supabase utworzony.")

        analysis = get_next_queued_analysis(
            supabase
        )

        if analysis is None:
            print(
                "Brak analiz ze statusem queued."
            )
            print(
                "Utwórz analizę przez panel użytkownika "
                "i uruchom test ponownie."
            )

            return 0

        print("Połączenie z bazą działa.")
        print(f"ID analizy: {analysis['id']}")
        print(f"Tytuł: {analysis['title']}")
        print(f"Status: {analysis['status']}")

        local_video_path = download_analysis_video(
            supabase=supabase,
            analysis=analysis,
            bucket_name=bucket_name,
        )

        metadata = read_video_metadata(
            local_video_path
        )

        print("\n=== WIDEO ===")
        print(
            "Rozdzielczość:",
            f"{metadata['width']} × {metadata['height']}",
        )
        print(f"FPS: {metadata['fps']}")
        print(
            "Liczba klatek:",
            metadata["frame_count"],
        )
        print(
            "Długość:",
            f"{metadata['duration_seconds']} s",
        )

        print("\n=== WYNIK ===")
        print(
            "Worker połączył się z Supabase, "
            "pobrał prywatny film i odczytał jego parametry."
        )
        print(
            "Status analizy nie został zmieniony."
        )

        return 0

    except Exception as error:
        print("\n=== BŁĄD ===", file=sys.stderr)
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())