from __future__ import annotations

from worker.src.pose_v5.config import PoseV5Config,RefinementConfig
from worker.src.pose_v5.integration import augment_pose_document_v5


def test_v4_document_is_augmented_without_removing_old_fields():
    frame={"output_timestamp_seconds":0.0,"tracking_state":"TRACKED","tracking":{"state":"TRACKED","identity_score":.9},"body":{"scale":100.0,"quality":.9},"body_quality":{"joints":{"left_wrist":{"coordinates":[10,10],"confidence":.9,"quality":.9,"visibility":.9,"occlusion_state":"VISIBLE"}}},"frame_quality":{"score":.9},"left_hand":{"graph_v2":{"quality":.9}},"right_hand":{"graph_v2":{"quality":.9}}}
    document={"schema_version":"4.0","pose_version":"pose-v4.0-beta.1","source":{"fps":10},"configuration":{"old":True},"summary":{},"frames":[frame]}
    result=augment_pose_document_v5(document,config=PoseV5Config(refinement=RefinementConfig(enabled=False)))
    assert result["schema_version"]=="5.1"; assert result["pose_version"]=="pose-v5.1-beta.1"
    assert result["configuration"]["old"] is True; assert "left_wrist" in result["frames"][0]["joint_evidence_v5"]
    assert result["configuration"]["pose_v5"]["force_estimation_enabled"] is False


def test_real_pose_v4_joint_list_is_normalized_to_v5_evidence():
    frame={"output_timestamp_seconds":0.0,"body_quality":{"quality":.9,"joints":[{"name":"left_wrist","coordinates":[10.0,20.0],"confidence":.9,"quality":.8,"visibility":1.0,"occlusion_state":"VISIBLE"}]},"body":{"scale":100.0,"quality":.9},"tracking":{"state":"TRACKED","identity_score":.9},"frame_quality":{"score":.9}}
    document={"schema_version":"4.0","source":{"fps":25},"configuration":{},"summary":{},"frames":[frame]}
    result=augment_pose_document_v5(document,config=PoseV5Config())
    assert "left_wrist" in result["frames"][0]["joint_evidence_v5"]
    assert result["frames"][0]["joint_evidence_v5"]["left_wrist"]["final_quality"]>0
