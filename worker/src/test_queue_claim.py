from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"


def get_required_environment_variable(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Brakuje wymaganej zmiennej środowiskowej: {name}"
        )

    return value


def create_supabase_client() -> Client:
    return create_client(
        get_required_environment_variable("SUPABASE_URL"),
        get_required_environment_variable(
            "SUPABASE_SECRET_KEY"
        ),
    )


def claim_next_analysis(
    supabase: Client,
    worker_id: str,
) -> dict[str, Any] | None:
    response = supabase.rpc(
        "claim_next_analysis",
        {
            "p_worker_id": worker_id,
        },
    ).execute()

    rows = response.data or []

    if not rows:
        return None

    return rows[0]


def update_progress(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
) -> None:
    response = supabase.rpc(
        "update_analysis_progress",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
            "p_progress": 7,
            "p_processing_stage": "queue-test",
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Worker nie zaktualizował postępu przejętej analizy."
        )


def requeue_analysis(
    supabase: Client,
    analysis_id: str,
    worker_id: str,
) -> None:
    response = supabase.rpc(
        "requeue_analysis",
        {
            "p_analysis_id": analysis_id,
            "p_worker_id": worker_id,
        },
    ).execute()

    if response.data is not True:
        raise RuntimeError(
            "Nie udało się zwrócić analizy do kolejki."
        )


def main() -> int:
    print("Ergonomia AI — test atomowej kolejki")

    if not ENV_PATH.exists():
        print(
            "BŁĄD: Nie znaleziono worker/.env",
            file=sys.stderr,
        )
        return 1

    load_dotenv(ENV_PATH)

    worker_id = os.getenv(
        "WORKER_ID",
        "local-worker-01",
    ).strip()

    claimed_analysis_id: str | None = None
    supabase: Client | None = None

    try:
        supabase = create_supabase_client()

        print(f"Worker ID: {worker_id}")
        print("Pobieranie najstarszego zadania queued...")

        analysis = claim_next_analysis(
            supabase,
            worker_id,
        )

        if analysis is None:
            print("Brak analiz oczekujących w kolejce.")
            return 0

        claimed_analysis_id = str(analysis["id"])

        print("\n=== PRZEJĘTE ZADANIE ===")
        print(f"ID: {claimed_analysis_id}")
        print(f"Tytuł: {analysis['title']}")
        print(f"Status: {analysis['status']}")
        print(f"Postęp: {analysis['progress']}%")
        print(f"Worker: {analysis['worker_id']}")
        print(f"Próba numer: {analysis['attempts']}")

        update_progress(
            supabase,
            claimed_analysis_id,
            worker_id,
        )

        print("\nPostęp został zmieniony na 7%.")
        print("Etap został zmieniony na queue-test.")

        requeue_analysis(
            supabase,
            claimed_analysis_id,
            worker_id,
        )

        claimed_analysis_id = None

        print("\n=== WYNIK ===")
        print("Atomowe przejęcie zadania działa.")
        print("Aktualizacja postępu działa.")
        print("Analiza została zwrócona do kolejki queued.")

        return 0

    except Exception as error:
        print("\n=== BŁĄD ===", file=sys.stderr)
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        return 1

    finally:
        if (
            supabase is not None
            and claimed_analysis_id is not None
        ):
            try:
                requeue_analysis(
                    supabase,
                    claimed_analysis_id,
                    worker_id,
                )

                print(
                    "\nAnaliza została awaryjnie "
                    "zwrócona do kolejki."
                )
            except Exception as cleanup_error:
                print(
                    "\nUWAGA: Nie udało się awaryjnie "
                    "zwrócić analizy do kolejki:",
                    cleanup_error,
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())