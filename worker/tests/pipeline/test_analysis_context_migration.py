from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "20260811120000_add_analysis_context_workstations_categories.sql"


def test_analysis_context_migration_contract():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for required in (
        "create table public.workstations",
        "create table public.analysis_categories",
        "create table public.analysis_category_links",
        "analysis_context jsonb",
        "enable row level security",
        "analysis_categories_owner_normalized_name_uidx",
        "primary key (analysis_id, category_id)",
        "foreign key (workstation_id, user_id)",
        "function public.set_analysis_categories",
        "security definer",
    ):
        assert required in sql
