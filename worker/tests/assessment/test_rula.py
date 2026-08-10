from __future__ import annotations

import pytest

from worker.src.assessment.rula.components import lower_arm_category, neck_category, trunk_category, upper_arm_category, wrist_category
from worker.src.assessment.rula.engine import assess_rula_candidate
from worker.src.assessment.rula.tables import action_level, table_a, table_b, table_c


@pytest.mark.parametrize(("angle","expected"),[(0,("minus_20_to_20",1)),(20,("minus_20_to_20",1)),(20.001,("20_to_45",2)),(45,("20_to_45",2)),(45.001,("45_to_90",3)),(90,("45_to_90",3)),(90.001,("over_90",4))])
def test_upper_arm_boundaries(angle,expected): assert upper_arm_category(angle)==expected

@pytest.mark.parametrize(("angle","score"),[(59.999,2),(60,1),(100,1),(100.001,2)])
def test_lower_arm_boundaries(angle,score): assert lower_arm_category(angle)[1]==score

@pytest.mark.parametrize(("angle","score"),[(0,1),(0.001,2),(15,2),(15.001,3)])
def test_wrist_boundaries(angle,score): assert wrist_category(angle)[1]==score

@pytest.mark.parametrize(("angle","score"),[(10,1),(10.001,2),(20,2),(20.001,3)])
def test_neck_boundaries(angle,score): assert neck_category(angle)[1]==score

@pytest.mark.parametrize(("angle","score"),[(0,1),(0.001,2),(20,2),(20.001,3),(60,3),(60.001,4)])
def test_trunk_boundaries(angle,score): assert trunk_category(angle)[1]==score

def test_original_table_examples():
    assert table_a(1,1,1,1)==1; assert table_a(6,3,4,2)==9
    assert table_b(1,1,1)==1; assert table_b(6,6,2)==9
    assert table_c(1,1)==1; assert table_c(8,7)==7

@pytest.mark.parametrize(("score","level"),[(1,1),(2,1),(3,2),(4,2),(5,3),(6,3),(7,4)])
def test_action_levels(score,level): assert action_level(score)==level

def test_partial_unknown_is_range(metrics_document):
    result=assess_rula_candidate(metrics_document["frames"][0],"left",quality=0.9)
    assert result["status"]=="PARTIAL"; assert result["final_score"] is None
    assert result["score_range"]["min"]<=result["score_range"]["max"]
    assert "rula_force_load" in result["missing_inputs"]

def test_low_quality_is_insufficient(metrics_document):
    assert assess_rula_candidate(metrics_document["frames"][0],"left",quality=0.2)["status"]=="INSUFFICIENT_DATA"

def test_left_does_not_use_right_wrist(metrics_document):
    frame=metrics_document["frames"][0]; frame["metrics"]["right_wrist_flexion_deg"]["valid"]=False
    result=assess_rula_candidate(frame,"left",quality=0.9)
    assert result["components"]["wrist"]["raw_input"]==10.0

@pytest.mark.parametrize("bad",[0,7,-1,True])
def test_table_rejects_invalid_category(bad):
    with pytest.raises(ValueError): table_a(bad,1,1,1)
