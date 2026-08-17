from pathlib import Path

from worker.src.scene_detection_worker import classify_scene_error, inference_windows, sanitize_message


def test_scene_error_contract_has_stable_codes_and_polish_message():
    error = classify_scene_error(RuntimeError("mime type application/json is not supported"), "upload")
    assert error.code == "SCENE_RESULT_UPLOAD_FAILED"
    assert "zapisać wyniku" in error.user_message
    assert error.transient is True


def test_diagnostics_remove_storage_urls():
    sanitized = sanitize_message("https://example.supabase.co/storage/v1/object/private/file.json")
    assert "supabase.co" not in sanitized
    assert "/storage/v1/" not in sanitized


def test_worker_exposes_real_queue_safe_self_test():
    source = Path("worker/src/scene_detection_worker.py").read_text(encoding="utf-8")
    assert '"--self-test"' in source
    assert "detector_candidates(self.detector_instance(), decoded)" in source
    assert "analyze_scene_geometry(decoded, candidates)" in source
    assert "_load_user_annotations(analysis_id)" in source
    assert "filter_candidates_against_user_annotations" in source
    assert "claim()" not in source[source.index("def self_test"):source.index("def run")]


def test_scene_bucket_migration_allows_json_without_making_bucket_public():
    migration = Path("supabase/migrations/20260813200000_allow_scene_detection_json_results.sql").read_text(encoding="utf-8").lower()
    assert "application/json" in migration
    assert "where id = 'analysis-scenes'" in migration
    assert "public = false" in migration


def test_large_images_get_bounded_overlapping_tiles_but_small_images_do_not():
    assert inference_windows(1200, 900) == [(0, 0, 1200, 900)]
    windows = inference_windows(4032, 3024)
    assert windows[0] == (0, 0, 4032, 3024)
    assert 2 <= len(windows) <= 10
    assert all(0 <= left < right <= 4032 and 0 <= top < bottom <= 3024 for left, top, right, bottom in windows)
