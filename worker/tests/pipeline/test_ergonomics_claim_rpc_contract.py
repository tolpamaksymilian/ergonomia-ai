from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPOSITORY_ROOT
    / "supabase"
    / "migrations"
    / "20260806221000_fix_ergonomics_claim_return_types.sql"
)


def _normalized_columns(block: str) -> list[str]:
    return [" ".join(column.strip().split()) for column in block.split(",")]


def test_ergonomics_claim_return_types_match_declared_contract() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    declared_match = re.search(
        r"returns\s+table\s*\((.*?)\)\s*language\s+plpgsql",
        migration,
        flags=re.IGNORECASE | re.DOTALL,
    )
    returned_match = re.search(
        r"returning\s+(.*?);\s*end;",
        migration,
        flags=re.IGNORECASE | re.DOTALL,
    )

    assert declared_match is not None
    assert returned_match is not None
    assert _normalized_columns(declared_match.group(1)) == [
        "id uuid",
        "user_id uuid",
        "title text",
        "status public.analysis_status",
        "progress integer",
        "result_json_path text",
        "processing_stage text",
        "worker_id text",
    ]
    assert _normalized_columns(returned_match.group(1)) == [
        "a.id::uuid",
        "a.user_id::uuid",
        "a.title::text",
        "a.status::public.analysis_status",
        "a.progress::integer",
        "a.result_json_path::text",
        "a.processing_stage::text",
        "a.worker_id::text",
    ]


def test_ergonomics_claim_keeps_atomicity_and_permissions() -> None:
    migration = " ".join(MIGRATION_PATH.read_text(encoding="utf-8").lower().split())

    assert "create or replace function public.claim_next_ergonomics_analysis(p_worker_id text)" in migration
    assert "for update skip locked" in migration
    assert "security definer" in migration
    assert "set search_path = ''" in migration
    assert "revoke all on function public.claim_next_ergonomics_analysis(text) from public;" in migration
    assert "revoke all on function public.claim_next_ergonomics_analysis(text) from anon;" in migration
    assert "revoke all on function public.claim_next_ergonomics_analysis(text) from authenticated;" in migration
    assert "grant execute on function public.claim_next_ergonomics_analysis(text) to service_role;" in migration
    assert "notify pgrst, 'reload schema';" in migration
