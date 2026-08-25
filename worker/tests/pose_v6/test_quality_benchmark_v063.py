from worker.src.pose_v6.quality_benchmark import collect_quality_kpis, compare_quality_documents


def test_benchmark_finds_nested_quality_kpis() -> None:
    document = {"summary": {"coverage": {"main_skeleton_render_coverage_ratio": 0.98}, "overlay": {"overlay_label_overlap_count": 2}}}
    values = collect_quality_kpis(document)
    assert values["main_skeleton_render_coverage_ratio"] == 0.98
    assert values["overlay_label_overlap_count"] == 2


def test_benchmark_reports_before_after_delta() -> None:
    before = {"summary": {"angle_usable_coverage_ratio": 0.7}}
    after = {"summary": {"angle_usable_coverage_ratio": 0.9}}
    result = compare_quality_documents(after, before)
    assert result["delta"]["angle_usable_coverage_ratio"] == 0.2
