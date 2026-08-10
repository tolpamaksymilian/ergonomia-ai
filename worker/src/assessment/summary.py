"""Representative method summaries; never average method scores."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


STATUS_ORDER={"INSUFFICIENT_DATA":0,"PARTIAL":1,"COMPLETE":2}


def summarize_method(method: str, candidates: Sequence[Mapping[str,Any]]) -> dict[str,Any]:
    entries=[]
    key=method.lower()
    for candidate in candidates:
        assessments=candidate.get(key)
        if isinstance(assessments,Mapping):
            for side,result in assessments.items():
                if isinstance(result,Mapping): entries.append((candidate,side,result))
    usable=[item for item in entries if item[2].get("status")!="INSUFFICIENT_DATA" and isinstance(item[2].get("score_range"),Mapping)]
    if not usable:
        return {"method":method,"status":"INSUFFICIENT_DATA","applicability":"INSUFFICIENT","representative":None,"worst_complete_score":None,"analyzed_posture_count":len(candidates),"left":_side_summary(entries,"left"),"right":_side_summary(entries,"right")}
    representative=max(usable,key=lambda item:(_range_max(item[2]),float(item[2].get("data_quality",0.0)),float(item[0].get("duration_context_seconds",0.0)),-float(item[0].get("timestamp_seconds",0.0))))
    complete=[int(result["final_score"]) for _,_,result in usable if result.get("status")=="COMPLETE" and isinstance(result.get("final_score"),int)]
    status="COMPLETE" if representative[2].get("status")=="COMPLETE" else "PARTIAL"
    return {"method":method,"status":status,"applicability":representative[2].get("applicability"),"representative":{"candidate_id":representative[0].get("candidate_id"),"side":representative[1],"timestamp_seconds":representative[0].get("timestamp_seconds"),"duration_context_seconds":representative[0].get("duration_context_seconds"),"quality":representative[0].get("quality"),"evidence_coverage_ratio":representative[2].get("evidence_coverage_ratio"),"final_score":representative[2].get("final_score"),"score_range":representative[2].get("score_range"),"missing_inputs":representative[2].get("missing_inputs",[])},"worst_complete_score":max(complete) if complete else None,"analyzed_posture_count":len(candidates),"left":_side_summary(entries,"left"),"right":_side_summary(entries,"right")}


def _side_summary(entries:list[tuple[Mapping[str,Any],str,Mapping[str,Any]]],side:str)->dict[str,Any]:
    selected=[item for item in entries if item[1]==side]
    return {"complete_count":sum(item[2].get("status")=="COMPLETE" for item in selected),"partial_count":sum(item[2].get("status")=="PARTIAL" for item in selected),"insufficient_count":sum(item[2].get("status")=="INSUFFICIENT_DATA" for item in selected)}


def _range_max(result:Mapping[str,Any])->int:
    score_range=result.get("score_range")
    value=score_range.get("max") if isinstance(score_range,Mapping) else 0
    return int(value) if isinstance(value,int) else 0
