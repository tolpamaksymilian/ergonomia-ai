from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "20260816200000_add_scene_reconstruction_v1.sql"


def test_scene_reconstruction_rpc_contract_is_atomic_and_service_role_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "claim_next_scene_reconstruction" in sql
    assert "for update of s skip locked" in sql
    assert "security definer" in sql
    assert "set search_path = ''" in sql
    assert "grant execute on function public.claim_next_scene_reconstruction(text) to service_role" in sql
    assert "revoke all on function public.claim_next_scene_reconstruction(text) from public, anon, authenticated" in sql
    assert "check_scene_reconstruction_readiness_v1" in sql
    assert "heartbeat_scene_reconstruction" in sql
    assert "grant execute on function public.check_scene_reconstruction_readiness_v1() to service_role" in sql


def test_scene_reconstruction_migration_adds_only_summary_and_queue_metadata() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "scene_schema_version set default '1.5'" in sql
    assert "reconstruction_path text" in sql
    assert "reconstruction_summary jsonb" in sql
    assert "notify pgrst, 'reload schema'" in sql
    assert "alter table public.analyses add column" not in sql
