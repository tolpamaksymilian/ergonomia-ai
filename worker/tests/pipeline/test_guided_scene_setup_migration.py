from pathlib import Path


MIGRATION = Path("supabase/migrations/20260816210000_guided_photo_scene_setup_v1.sql")


def test_new_photo_waits_for_guided_setup_instead_of_starting_worker():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    finalize = sql[sql.index("create or replace function public.finalize_photo_scene_upload"):sql.index("create or replace function public.request_guided_scene_build_v1")]
    assert "processing_stage = 'photo-scene-setup'" in finalize
    assert "processing_stage = 'ready-for-scene-detection'" not in finalize


def test_guided_request_validates_floor_movement_and_two_heights_atomically():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    request = sql[sql.index("create or replace function public.request_guided_scene_build_v1"):sql.index("create or replace function public.complete_scene_detection_v1")]
    assert "floor_region" in request
    assert "movement_zone" in request
    assert "v_height_count < 2" in request
    assert "for update of a, s" in request
    assert "processing_stage = 'ready-for-scene-detection'" in request


def test_detection_completion_queues_reconstruction_only_for_guided_revision():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    complete = sql[sql.index("create or replace function public.complete_scene_detection_v1"):sql.index("create or replace function public.retry_scene_detection")]
    assert "reconstruction_status = 'unsolved'" in complete
    assert "reconstruction_revision is not null" in complete
    assert "then 'queued'" in complete
    assert "security definer" in complete
    assert "set search_path = ''" in complete


def test_guided_rpc_permissions_are_authenticated_only():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "revoke all on function public.request_guided_scene_build_v1(uuid, text) from public, anon" in sql
    assert "grant execute on function public.request_guided_scene_build_v1(uuid, text) to authenticated" in sql
    assert "notify pgrst, 'reload schema'" in sql
