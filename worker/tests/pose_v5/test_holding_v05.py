from __future__ import annotations

from worker.src.pose_v5.holding import HoldingEvidenceV3,HoldingStateV3,analyze_holding_v3,bimanual_holding_v3


def item(**values):
    data=dict(grip=.9,contact_evidence=0.0,object_proximity=0.0,common_motion=0.0,temporal_persistence=.9,occlusion_pattern=0.0,release=0.0,quality=.9)
    data.update(values); return HoldingEvidenceV3(**data)


def test_closed_fist_without_object_is_not_likely_holding():
    frames=analyze_holding_v3([item() for _ in range(10)],[.1]*10)
    assert all(frame.state in {HoldingStateV3.POSSIBLE_HOLDING,HoldingStateV3.NOT_HOLDING} for frame in frames)


def test_persistent_object_grasp_becomes_likely():
    evidence=[item(contact_evidence=.9,object_proximity=.9,common_motion=.8,object_track_id=4) for _ in range(8)]
    frames=analyze_holding_v3(evidence,[.1]*8)
    assert frames[-1].state is HoldingStateV3.LIKELY_HOLDING


def test_one_frame_object_loss_does_not_split_episode():
    evidence=[item(contact_evidence=.9,object_proximity=.9,common_motion=.8,object_track_id=4) for _ in range(6)]
    evidence.append(item(quality=.2)); evidence.extend([item(contact_evidence=.9,object_proximity=.9,common_motion=.8,object_track_id=4) for _ in range(3)])
    frames=analyze_holding_v3(evidence,[.1]*len(evidence))
    assert frames[6].state in {HoldingStateV3.LIKELY_HOLDING,HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT}


def test_release_ends_episode():
    evidence=[item(contact_evidence=.9,object_proximity=.9,common_motion=.8,object_track_id=4) for _ in range(6)]
    evidence.extend([item(grip=.1,release=.9) for _ in range(4)])
    frames=analyze_holding_v3(evidence,[.1]*len(evidence))
    assert frames[-1].state is HoldingStateV3.NOT_HOLDING


def test_bimanual_requires_same_object_or_shared_contact_motion():
    left=analyze_holding_v3([item(contact_evidence=.9,object_proximity=.9,common_motion=.8,object_track_id=4) for _ in range(6)],[.1]*6)
    right=analyze_holding_v3([item(contact_evidence=.9,object_proximity=.9,common_motion=.8,object_track_id=4) for _ in range(6)],[.1]*6)
    assert bimanual_holding_v3(left,right)[-1] is True
