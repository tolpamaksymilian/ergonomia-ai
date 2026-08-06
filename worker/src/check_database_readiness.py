"""Read-only Supabase readiness check for the complete local pipeline."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv
from supabase import Client, create_client


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
ENV_PATH = WORKER_DIRECTORY / ".env"
READINESS_RPC = "check_pipeline_readiness_v021"
FLAG_NAMES = (
    "DATABASE_READY",
    "ERGONOMICS_SCHEMA_READY",
    "RISK_SCHEMA_READY",
    "REPORT_SCHEMA_READY",
    "RPC_PERMISSIONS_READY",
    "STORAGE_READY",
)


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing_environment_variable:{name}")
    return value


def create_admin_client() -> Client:
    load_dotenv(ENV_PATH, override=False)
    return create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_SECRET_KEY"),
    )


def fetch_readiness(client: Client) -> Mapping[str, Any]:
    response = client.rpc(READINESS_RPC, {}).execute()
    if not isinstance(response.data, Mapping):
        raise RuntimeError("invalid_readiness_response")
    return response.data


def _as_bool(value: Any) -> bool:
    return value is True


def format_readiness(result: Mapping[str, Any]) -> list[str]:
    key_map = {
        "DATABASE_READY": "database_ready",
        "ERGONOMICS_SCHEMA_READY": "ergonomics_schema_ready",
        "RISK_SCHEMA_READY": "risk_schema_ready",
        "REPORT_SCHEMA_READY": "report_schema_ready",
        "RPC_PERMISSIONS_READY": "rpc_permissions_ready",
        "STORAGE_READY": "storage_ready",
    }
    lines = [
        f"{label}={'true' if _as_bool(result.get(key)) else 'false'}"
        for label, key in key_map.items()
    ]
    for key in (
        "missing_columns",
        "missing_rpcs",
        "missing_execute",
        "missing_buckets",
        "public_buckets",
    ):
        values = result.get(key)
        if isinstance(values, list):
            lines.extend(f"MISSING={key}:{value}" for value in values)
    return lines


def main() -> int:
    try:
        result = fetch_readiness(create_admin_client())
    except (RuntimeError, ValueError, OSError) as error:
        for flag in FLAG_NAMES:
            print(f"{flag}=false")
        print(f"MISSING=readiness_check:{type(error).__name__}")
        return 1
    except Exception as error:  # Supabase client errors share no stable base class.
        for flag in FLAG_NAMES:
            print(f"{flag}=false")
        error_text = str(error).lower()
        reason = "readiness_rpc_not_available" if READINESS_RPC in error_text else "database_connection_failed"
        print(f"MISSING=readiness_check:{reason}")
        return 1

    for line in format_readiness(result):
        print(line)
    return 0 if result.get("database_ready") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
