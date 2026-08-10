from __future__ import annotations

import pytest

from worker.src.assessment.reba.components import leg_evidence, neck_category, trunk_category
from worker.src.assessment.reba.engine import assess_reba_candidate
from worker.src.assessment.reba.tables import risk_level, table_a, table_b, table_c


@pytest.mark.parametrize(("angle","score"),[(0,1),(20,1),(20.001,2),(80,2)])
def test_neck_boundaries(angle,score): assert neck_category(angle)[1]==score

@pytest.mark.parametrize(("angle","score"),[(0,1),(0.001,2),(20,2),(20.001,3),(60,3),(60.001,4)])
def test_trunk_boundaries(angle,score): assert trunk_category(angle)[1]==score

def test_table_reference_cells():
    assert table_a(1,1,1)==1; assert table_a(5,3,4)==9
    assert table_b(1,1,1)==1; assert table_b(6,2,3)==9
    assert table_c(1,1)==1; assert table_c(12,12)==12

@pytest.mark.parametrize(("score","level"),[(1,"negligible"),(2,"low"),(3,"low"),(4,"medium"),(7,"medium"),(8,"high"),(10,"high"),(11,"very_high"),(15,"very_high")])
def test_risk_levels(score,level): assert risk_level(score)==level

def test_straight_leg_is_derived(pose_document):
    result=leg_evidence(pose_document["frames"][0],"left")
    assert result.source.value=="derived"; assert result.score is None; assert result.raw_input==pytest.approx(0)
    assert result.possible_scores == (1, 2)
    assert result.missing_evidence == ("weight_distribution_and_leg_support",)

def test_zero_length_leg_vector_is_unknown(pose_document):
    points = pose_document["frames"][0]["smoothed_keypoints"]
    points[13] = list(points[11])
    result = leg_evidence(pose_document["frames"][0], "left")
    assert result.score is None
    assert result.source.value == "unknown"
    assert "zero_length_leg_vector" in result.notes

def test_invalid_leg_quality_is_unknown(pose_document):
    pose_document["frames"][0]["scores"][13]=0.1
    result=leg_evidence(pose_document["frames"][0],"left")
    assert result.source.value=="unknown"; assert result.score is None

def test_partial_load_and_coupling_remain_unknown(metrics_document,pose_document):
    result=assess_reba_candidate(metrics_document["frames"][0],pose_document["frames"][0],"left",quality=0.9)
    assert result["status"]=="PARTIAL"; assert result["final_score"] is None
    assert "reba_load_force" in result["missing_inputs"]; assert "reba_coupling" in result["missing_inputs"]

def test_low_quality_is_insufficient(metrics_document,pose_document):
    assert assess_reba_candidate(metrics_document["frames"][0],pose_document["frames"][0],"right",quality=0.1)["status"]=="INSUFFICIENT_DATA"

@pytest.mark.parametrize("bad",[0,6,-1,True])
def test_table_rejects_invalid_trunk(bad):
    with pytest.raises(ValueError): table_a(bad,1,1)
