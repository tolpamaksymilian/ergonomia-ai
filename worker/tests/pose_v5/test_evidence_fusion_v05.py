from __future__ import annotations

from worker.src.pose_v5.graph import JointConsensus, JointEvidenceFusion


def evaluate(engine, point, timestamp, **overrides):
    values = dict(body_scale=100.0, model_quality=0.95, kinematic_quality=0.9,
        tracking_quality=0.9, visibility_quality=0.9, image_quality=0.9)
    values.update(overrides)
    return engine.evaluate("left_wrist", point, timestamp_seconds=timestamp, **values)


def test_high_quality_consensus_is_accepted():
    result=evaluate(JointEvidenceFusion(),(100.0,100.0),0.0)
    assert result.consensus is JointConsensus.ACCEPTED
    assert result.final_quality == 0.9


def test_high_model_score_does_not_override_bad_chain():
    result=evaluate(JointEvidenceFusion(),(100.0,100.0),0.0,kinematic_quality=0.1)
    assert result.consensus is JointConsensus.REJECTED


def test_jerk_teleport_is_rejected_and_does_not_update_anchor():
    engine=JointEvidenceFusion(); evaluate(engine,(100.0,100.0),0.0); evaluate(engine,(101.0,100.0),0.1)
    outlier=evaluate(engine,(800.0,100.0),0.2)
    assert outlier.consensus is JointConsensus.REJECTED
    assert "JERK_OUTLIER" in outlier.rejection_reasons
    recovered=evaluate(engine,(102.0,100.0),0.3)
    assert recovered.consensus in {JointConsensus.ACCEPTED,JointConsensus.WEAK}


def test_temporal_rates_are_dt_aware():
    fast=JointEvidenceFusion(); evaluate(fast,(100.0,100.0),0.0); fast_result=evaluate(fast,(130.0,100.0),0.01)
    slow=JointEvidenceFusion(); evaluate(slow,(100.0,100.0),0.0); slow_result=evaluate(slow,(130.0,100.0),1.0)
    assert fast_result.velocity_scale_per_second > slow_result.velocity_scale_per_second


def test_camera_translation_is_removed_from_temporal_displacement():
    engine=JointEvidenceFusion(); evaluate(engine,(100.0,100.0),0.0)
    result=evaluate(engine,(110.0,100.0),0.1,global_translation=(10.0,0.0))
    assert result.velocity_scale_per_second == 0.0


def test_missing_occluded_joint_is_not_low_or_zero_measurement():
    result=evaluate(JointEvidenceFusion(),None,0.0,occluded=True)
    assert result.consensus is JointConsensus.OCCLUDED
    assert result.final_quality == 0.0
