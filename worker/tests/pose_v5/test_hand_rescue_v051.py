from worker.src.pose_v5.hand_rescue import enlarge_roi, observation_coverage, rescue_frame_indexes


def test_enlarged_roi_remains_inside_frame():
    assert enlarge_roi((10, 20, 30, 40), frame_width=100, frame_height=80, scale=2.0) == (0, 10, 40, 50)


def test_rescue_only_runs_below_minimum_coverage():
    relevant = [True] * 10
    assert rescue_frame_indexes([True] * 10, relevant, minimum_coverage=0.3, maximum_ratio=0.5) == []
    indexes = rescue_frame_indexes([False] * 10, relevant, minimum_coverage=0.3, maximum_ratio=0.5)
    assert len(indexes) == 5
    assert indexes[0] == 0 and indexes[-1] == 9


def test_observation_coverage_is_not_accuracy():
    assert observation_coverage([True, False, True], [True, True, False]) == 0.5
