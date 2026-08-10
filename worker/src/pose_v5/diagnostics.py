"""Region coverage and Pose V5 diagnostics helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


REGIONS={"body":("left_shoulder","right_shoulder","left_hip","right_hip"),"neck":("nose","left_shoulder","right_shoulder"),"left_arm":("left_shoulder","left_elbow","left_wrist"),"right_arm":("right_shoulder","right_elbow","right_wrist"),"legs":("left_hip","left_knee","left_ankle","right_hip","right_knee","right_ankle")}


def region_quality_coverage(frames:Sequence[Mapping[str,Any]], *, fps:float)->dict[str,dict[str,float]]:
    duration=1.0/fps if fps>0 else 0.0; output={}
    for region,names in REGIONS.items():
        relevant=valid=0.0
        for frame in frames:
            qualities=frame.get("region_quality")
            if not isinstance(qualities,Mapping):
                evidence=frame.get("joint_evidence_v5")
                qualities={name:item.get("quality") for name,item in evidence.items() if isinstance(name,str) and isinstance(item,Mapping)} if isinstance(evidence,Mapping) else {}
            relevant+=duration
            values=[qualities.get(name) for name in names]
            numeric=[float(value) for value in values if isinstance(value,(int,float)) and not isinstance(value,bool)]
            if numeric and min(numeric)>=0.55: valid+=duration
        output[region]={"valid_observation_seconds":round(valid,6),"total_relevant_seconds":round(relevant,6),"coverage_ratio":round(valid/relevant,6) if relevant else 0.0}
    for side in ("left", "right"):
        valid=0.0; relevant=0.0
        for frame in frames:
            hand=frame.get(f"{side}_hand")
            if not isinstance(hand,Mapping): continue
            relevant+=duration
            graph=hand.get("graph_v2")
            quality=graph.get("quality") if isinstance(graph,Mapping) else None
            if isinstance(quality,(int,float)) and not isinstance(quality,bool) and quality>=0.55: valid+=duration
        output[f"{side}_hand"]={"valid_observation_seconds":round(valid,6),"total_relevant_seconds":round(relevant,6),"coverage_ratio":round(valid/relevant,6) if relevant else 0.0}
    return output
