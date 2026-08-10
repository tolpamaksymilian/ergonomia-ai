"""Public document/file API for the CPU-only Assessment Engine."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any

from .quality import frame_quality
from .reba import assess_reba_candidate
from .rula import assess_rula_candidate
from .schemas import ASSESSMENT_ENGINE_VERSION, ASSESSMENT_SCHEMA_VERSION, AssessmentInputError, REBA_VERSION, RULA_VERSION
from .selection import select_candidate_postures
from .summary import summarize_method


SUPPORTED_METRICS_SCHEMA="1.0"; SUPPORTED_METRICS_VERSION="ergonomics-metrics-v1.0"; SUPPORTED_POSE_SCHEMAS=frozenset({"4.0"})


def process_assessment_documents(ergonomics: Mapping[str,Any], pose: Mapping[str,Any] | None = None, *, user_context: Mapping[str,Any] | None = None, maximum_candidates:int=12, minimum_quality:float=0.55, calculated_at:str|None=None)->dict[str,Any]:
    started=time.perf_counter(); analysis_id=_validate_inputs(ergonomics,pose)
    frames=ergonomics["frames"]; pose_frames=pose.get("frames",[]) if isinstance(pose,Mapping) else []
    selection_started=time.perf_counter(); candidates=select_candidate_postures(ergonomics,pose,maximum_candidates=maximum_candidates,minimum_quality=minimum_quality); selection_ms=(time.perf_counter()-selection_started)*1000
    evaluated=[]; rula_started=time.perf_counter(); rula_ms=0.0; reba_ms=0.0
    for candidate in candidates:
        frame=frames[candidate.frame_position]; pose_frame=pose_frames[candidate.frame_position] if candidate.frame_position<len(pose_frames) and isinstance(pose_frames[candidate.frame_position],Mapping) else None
        quality=frame_quality(frame,pose_frame)
        rula_clock=time.perf_counter(); rula={side:assess_rula_candidate(frame,side,quality=quality,context=user_context) for side in ("left","right")}; rula_ms+=(time.perf_counter()-rula_clock)*1000
        reba_clock=time.perf_counter(); reba={side:assess_reba_candidate(frame,pose_frame,side,quality=quality,context=user_context) for side in ("left","right")}; reba_ms+=(time.perf_counter()-reba_clock)*1000
        evaluated.append({**candidate.to_dict(),"rula":rula,"reba":reba})
    limitations=["analysis_based_on_2d_video","result_is_screening_not_diagnosis","specialist_review_required"]
    if user_context is None or "rula_force_load" not in user_context: limitations.append("external_load_not_determined")
    if user_context is None or "reba_coupling" not in user_context: limitations.append("coupling_quality_not_determined")
    result={"schema_version":ASSESSMENT_SCHEMA_VERSION,"generated_by":"Ergonomia AI Evidence-Aware Assessment Engine","engine_version":ASSESSMENT_ENGINE_VERSION,"calculated_at":calculated_at or datetime.now(timezone.utc).isoformat(),"analysis_id":analysis_id,"source":{"pose_schema_version":pose.get("schema_version") if isinstance(pose,Mapping) else None,"pose_version":pose.get("pose_version") if isinstance(pose,Mapping) else None,"ergonomics_version":ergonomics.get("metrics_version")},"configuration":{"assumptions_enabled":False,"force_estimation_enabled":False,"weight_estimation_enabled":False,"maximum_candidates":maximum_candidates,"minimum_quality":minimum_quality},"method_versions":{"rula":RULA_VERSION,"reba":REBA_VERSION},"candidate_postures":evaluated,"rula":summarize_method("RULA",evaluated),"reba":summarize_method("REBA",evaluated),"limitations":limitations,"quality":{"candidate_coverage_ratio":round(len(evaluated)/len(frames),6),"minimum_candidate_quality":minimum_quality},"keyframes":[],"diagnostics":{"candidates_total":len(candidates),"candidates_evaluated":len(evaluated),"rula_complete_count":_count(evaluated,"rula","COMPLETE"),"rula_partial_count":_count(evaluated,"rula","PARTIAL"),"reba_complete_count":_count(evaluated,"reba","COMPLETE"),"reba_partial_count":_count(evaluated,"reba","PARTIAL"),"selection_ms":round(selection_ms,3),"rula_ms":round(rula_ms,3),"reba_ms":round(reba_ms,3),"processing_ms":round((time.perf_counter()-started)*1000,3)}}
    return result


def process_assessment_files(pose_path:str|Path, ergonomics_path:str|Path, output_path:str|Path, *, user_context_path:str|Path|None=None, maximum_candidates:int=12, minimum_quality:float=0.55)->dict[str,Any]:
    pose=_read_json(pose_path,"pose-keypoints.json"); ergonomics=_read_json(ergonomics_path,"ergonomics-metrics.json"); context=_read_json(user_context_path,"user context") if user_context_path else None
    result=process_assessment_documents(ergonomics,pose,user_context=context,maximum_candidates=maximum_candidates,minimum_quality=minimum_quality)
    _write_json(output_path,result); return result


def _validate_inputs(ergonomics:Mapping[str,Any],pose:Mapping[str,Any]|None)->str:
    if ergonomics.get("schema_version")!=SUPPORTED_METRICS_SCHEMA or ergonomics.get("metrics_version")!=SUPPORTED_METRICS_VERSION: raise AssessmentInputError("unsupported ergonomics metrics schema or version")
    analysis_id=ergonomics.get("analysis_id")
    if not isinstance(analysis_id,str) or not analysis_id.strip(): raise AssessmentInputError("ergonomics metrics analysis_id is required")
    frames=ergonomics.get("frames")
    if not isinstance(frames,list) or not frames: raise AssessmentInputError("ergonomics metrics frames must be a non-empty array")
    if pose is not None:
        if pose.get("schema_version") not in SUPPORTED_POSE_SCHEMAS: raise AssessmentInputError("unsupported pose schema; assessment requires Pose V4")
        pose_id=pose.get("analysis_id")
        if isinstance(pose_id,str) and pose_id and pose_id!=analysis_id: raise AssessmentInputError("pose and ergonomics analysis_id do not match")
    return analysis_id


def _read_json(path:str|Path,label:str)->dict[str,Any]:
    source=Path(path)
    if not source.is_file() or source.stat().st_size<=0: raise AssessmentInputError(f"{label} does not exist or is empty")
    try: value=json.loads(source.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as error: raise AssessmentInputError(f"{label} is not valid JSON") from error
    if not isinstance(value,dict): raise AssessmentInputError(f"{label} root must be an object")
    return value


def _write_json(path:str|Path,value:Mapping[str,Any])->None:
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); temporary:Path|None=None
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=target.parent,prefix=f".{target.name}.",suffix=".tmp",delete=False) as stream:
            temporary=Path(stream.name); json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False); stream.write("\n")
        temporary.replace(target)
    finally:
        if temporary and temporary.exists(): temporary.unlink()


def _count(candidates:list[dict[str,Any]],method:str,status:str)->int:
    return sum(result.get("status")==status for candidate in candidates for result in candidate.get(method,{}).values())
