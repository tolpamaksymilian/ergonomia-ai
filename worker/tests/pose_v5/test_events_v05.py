from __future__ import annotations

from worker.src.pose_v5.events import merge_metric_events


def test_events_merge_short_gaps_and_preserve_evidence():
    frames=[{"timestamp":t,"metrics":{"trunk_inclination_deg":{"valid":True,"value":value,"quality":0.8}}} for t,value in [(0,30),(0.1,35),(0.2,0),(0.3,40)]]
    events=merge_metric_events(frames,"trunk_inclination_deg","TRUNK_DEVIATION",minimum_value=20,maximum_gap_seconds=0.25)
    assert len(events)==1; assert events[0].peak==40; assert events[0].source_metrics==("trunk_inclination_deg",)
