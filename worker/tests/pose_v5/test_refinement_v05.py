from __future__ import annotations

from worker.src.pose_v5.config import RefinementConfig
from worker.src.pose_v5.refinement import detect_difficult_segments, refine_frames, summarize_refinement


def frames(count=20,quality=0.9):
    return [{"timestamp_seconds":i/10,"quality":quality,"tracking_state":"TRACKED","reasons":[]} for i in range(count)]


def test_good_segment_is_not_refined():
    segments,summary=detect_difficult_segments(frames(),fps=10,config=RefinementConfig())
    assert segments==[]; assert summary["refinable_frames"]==0


def test_low_quality_frames_merge_with_padding():
    source=frames(); source[8]["quality"]=0.5; source[9]["quality"]=0.45
    segments,_=detect_difficult_segments(source,fps=10,config=RefinementConfig(padding_seconds=0.2,maximum_refinement_ratio=1.0))
    assert len(segments)==1; assert segments[0].start_frame==6; assert segments[0].end_frame==11


def test_worse_pass2_is_rejected():
    source=frames(3,0.5); segment=detect_difficult_segments(source,fps=10,config=RefinementConfig(maximum_refinement_ratio=1.0,padding_seconds=0))[0][0]
    results=refine_frames(segment,source,lambda index,frame:{"quality":0.4,"biomechanical_valid":True},config=RefinementConfig(maximum_refinement_ratio=1.0))
    assert not any(item.accepted for item in results)


def test_better_pass2_requires_biomechanical_validation():
    source=frames(2,0.5); config=RefinementConfig(maximum_refinement_ratio=1.0,padding_seconds=0,minimum_quality_gain=0.05)
    segment=detect_difficult_segments(source,fps=10,config=config)[0][0]
    rejected=refine_frames(segment,source,lambda i,f:{"quality":0.8,"biomechanical_valid":False},config=config)
    accepted=refine_frames(segment,source,lambda i,f:{"quality":0.8,"biomechanical_valid":True},config=config)
    assert not any(item.accepted for item in rejected); assert all(item.accepted for item in accepted)


def test_maximum_refinement_ratio_is_enforced():
    source=frames(100,0.5); segments,summary=detect_difficult_segments(source,fps=10,config=RefinementConfig(maximum_refinement_ratio=0.25,padding_seconds=0))
    assert summary["limit_applied"] is True
    assert sum(item.frame_count for item in segments if item.refinable)<=25
    assert summary["video_quality_limited"] is True


def test_long_difficult_segment_is_bounded_instead_of_skipped():
    source=frames(100,0.5)
    segments,summary=detect_difficult_segments(source,fps=10,config=RefinementConfig(maximum_refinement_ratio=0.25,padding_seconds=0))
    selected=[item for item in segments if item.refinable]
    assert len(selected)==1
    assert selected[0].frame_count==25
    assert summary["refinable_frames"]==25


def test_refinement_summary_reports_quality_gain():
    source=frames(2,0.5); config=RefinementConfig(maximum_refinement_ratio=1.0,padding_seconds=0)
    segment=detect_difficult_segments(source,fps=10,config=config)[0][0]
    results=refine_frames(segment,source,lambda i,f:{"quality":0.7,"biomechanical_valid":True},config=config)
    summary=summarize_refinement([segment],results,len(source))
    assert summary["frames_improved"]==2; assert summary["mean_quality_gain"]==0.2
