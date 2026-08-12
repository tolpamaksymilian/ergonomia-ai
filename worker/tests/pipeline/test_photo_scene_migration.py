from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "20260812120000_add_photo_scene_builder_beta.sql"
UPGRADE = Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "20260812150000_upgrade_photo_scene_builder_v02.sql"


def source() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_photo_scene_migration_defaults_existing_rows_to_video_and_guards_claim():
    sql = source()
    assert "analysis_type text not null default 'video'" in sql
    assert "where a.analysis_type = 'video'" in sql
    assert "for update skip locked" in sql


def test_photo_scene_storage_and_rls_are_private_and_owned():
    sql = source()
    assert "'analysis-scenes', 'analysis-scenes', false" in sql
    assert "alter table public.photo_scenes enable row level security" in sql
    assert "(storage.foldername(name))[1] = (select auth.uid())::text" in sql


def test_scene_claim_is_service_role_only_and_atomic():
    sql = source()
    assert "claim_next_scene_analysis" in sql
    assert "revoke all on function public.claim_next_scene_analysis(text) from public, anon, authenticated" in sql
    assert "grant execute on function public.claim_next_scene_analysis(text) to service_role" in sql


def test_scene_state_has_schema_and_json_object_constraints():
    sql = source()
    assert "scene_schema_version text not null default '1.0'" in sql
    assert "photo_scenes_state_is_object" in sql
    assert "jsonb_typeof(scene_state) = 'object'" in sql


def test_scene_v02_migration_preserves_v10_and_allows_versioned_save():
    sql = UPGRADE.read_text(encoding="utf-8").lower()
    assert "scene_schema_version in ('1.0', '1.1')" in sql
    assert "alter column scene_schema_version set default '1.1'" in sql
    assert "photo-scene-builder-v0.2-beta.1" in sql
    assert "grant update (scene_state, scene_schema_version, scene_builder_version, last_saved_at)" in sql
    assert "notify pgrst, 'reload schema'" in sql
