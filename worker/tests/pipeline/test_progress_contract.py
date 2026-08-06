from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_pose_completion_sets_ready_progress_to_75() -> None:
    migration = (
        REPO_ROOT
        / "supabase"
        / "migrations"
        / "20260803210000_upgrade_pose_quality_and_active_segment.sql"
    ).read_text(encoding="utf-8")
    assert "progress = 75" in migration
    assert "processing_stage = 'ready-for-ergonomics'" in migration


def test_final_progress_trigger_covers_pose_completion() -> None:
    migration = (
        REPO_ROOT
        / "supabase"
        / "migrations"
        / "20260806210500_finalize_pipeline_v021.sql"
    ).read_text(encoding="utf-8")
    assert "analyses_normalize_pipeline_progress" in migration
    assert "new.processing_stage = 'ready-for-ergonomics'" in migration
    assert "greatest(coalesce(new.progress, 0), 75)" in migration


def test_completed_is_only_after_report_completion() -> None:
    report_migration = (
        REPO_ROOT
        / "supabase"
        / "migrations"
        / "20260806203000_integrate_report_worker_v1.sql"
    ).read_text(encoding="utf-8")
    assert "status = 'completed'::public.analysis_status" in report_migration
    assert "progress = 100" in report_migration
    assert "processing_stage = 'completed'" in report_migration
