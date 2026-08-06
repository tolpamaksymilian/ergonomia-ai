from __future__ import annotations

import re
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPOSITORY_ROOT
    / "supabase"
    / "migrations"
    / "20260806222000_fix_risk_report_claim_return_types.sql"
)

RISK_DECLARED_COLUMNS = [
    "id uuid",
    "user_id uuid",
    "title text",
    "status public.analysis_status",
    "progress integer",
    "processing_stage text",
    "ergonomics_metrics_path text",
    "worker_id text",
]
RISK_RETURNED_COLUMNS = [
    "a.id::uuid",
    "a.user_id::uuid",
    "a.title::text",
    "a.status::public.analysis_status",
    "a.progress::integer",
    "a.processing_stage::text",
    "a.ergonomics_metrics_path::text",
    "a.worker_id::text",
]
REPORT_DECLARED_COLUMNS = [
    "id uuid",
    "user_id uuid",
    "title text",
    "status public.analysis_status",
    "progress integer",
    "processing_stage text",
    "worker_id text",
    "report_worker_id text",
    "created_at timestamptz",
    "source_file_name text",
    "source_duration_seconds numeric",
    "source_width integer",
    "source_height integer",
    "pose_quality_version text",
    "pose_processed_frames integer",
    "pose_detected_frames integer",
    "pose_presence_ratio numeric",
    "ergonomics_metrics_path text",
    "ergonomics_metrics_version text",
    "ergonomics_processed_frames integer",
    "ergonomics_valid_metric_ratio numeric",
    "risk_assessment_path text",
    "risk_assessment_version text",
    "risk_profile_id text",
    "risk_profile_version text",
    "risk_profile_status text",
    "risk_processed_frames integer",
    "risk_valid_metric_ratio numeric",
    "risk_overall_level text",
]
REPORT_RETURNED_COLUMNS = [
    "a.id::uuid",
    "a.user_id::uuid",
    "a.title::text",
    "a.status::public.analysis_status",
    "a.progress::integer",
    "a.processing_stage::text",
    "a.worker_id::text",
    "a.report_worker_id::text",
    "a.created_at::timestamptz",
    "a.source_file_name::text",
    "a.source_duration_seconds::numeric",
    "a.source_width::integer",
    "a.source_height::integer",
    "a.pose_quality_version::text",
    "a.pose_processed_frames::integer",
    "a.pose_detected_frames::integer",
    "a.pose_presence_ratio::numeric",
    "a.ergonomics_metrics_path::text",
    "a.ergonomics_metrics_version::text",
    "a.ergonomics_processed_frames::integer",
    "a.ergonomics_valid_metric_ratio::numeric",
    "a.risk_assessment_path::text",
    "a.risk_assessment_version::text",
    "a.risk_profile_id::text",
    "a.risk_profile_version::text",
    "a.risk_profile_status::text",
    "a.risk_processed_frames::integer",
    "a.risk_valid_metric_ratio::numeric",
    "a.risk_overall_level::text",
]


def _function_definition(migration: str, function_name: str) -> str:
    match = re.search(
        rf"create or replace function public\.{function_name}"
        r"\(p_worker_id text\)(.*?)\$\$;",
        migration,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _normalized_columns(block: str) -> list[str]:
    return [" ".join(column.strip().split()) for column in block.split(",")]


@pytest.mark.parametrize(
    ("function_name", "declared_columns", "returned_columns"),
    [
        (
            "claim_next_risk_analysis",
            RISK_DECLARED_COLUMNS,
            RISK_RETURNED_COLUMNS,
        ),
        (
            "claim_next_report_analysis",
            REPORT_DECLARED_COLUMNS,
            REPORT_RETURNED_COLUMNS,
        ),
    ],
)
def test_claim_return_types_match_declared_contract(
    function_name: str,
    declared_columns: list[str],
    returned_columns: list[str],
) -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    definition = _function_definition(migration, function_name)
    declared_match = re.search(
        r"returns\s+table\s*\((.*?)\)\s*language\s+plpgsql",
        definition,
        flags=re.IGNORECASE | re.DOTALL,
    )
    returned_match = re.search(
        r"returning\s+(.*?);\s*end;",
        definition,
        flags=re.IGNORECASE | re.DOTALL,
    )

    assert declared_match is not None
    assert returned_match is not None
    assert _normalized_columns(declared_match.group(1)) == declared_columns
    assert _normalized_columns(returned_match.group(1)) == returned_columns


@pytest.mark.parametrize(
    "function_name",
    ["claim_next_risk_analysis", "claim_next_report_analysis"],
)
def test_claim_keeps_atomicity_security_and_permissions(function_name: str) -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    definition = " ".join(
        _function_definition(migration, function_name).lower().split()
    )
    normalized_migration = " ".join(migration.lower().split())

    assert "for update skip locked" in definition
    assert "security definer" in definition
    assert "set search_path = ''" in definition
    for role in ("public", "anon", "authenticated"):
        assert (
            f"revoke all on function public.{function_name}(text) from {role};"
            in normalized_migration
        )
    assert (
        f"grant execute on function public.{function_name}(text) to service_role;"
        in normalized_migration
    )


def test_migration_reloads_postgrest_schema() -> None:
    migration = " ".join(MIGRATION_PATH.read_text(encoding="utf-8").lower().split())

    assert "notify pgrst, 'reload schema';" in migration
