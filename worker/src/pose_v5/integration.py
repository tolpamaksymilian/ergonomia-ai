"""Schema V5 augmentation over validated Pose V4 analytical geometry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import POSE_SCHEMA_VERSION, POSE_VERSION, WORKER_VERSION
from .config import PoseV5Config
from .graph import JointEvidenceFusion
from .refinement import detect_difficult_segments, summarize_refinement


def augment_pose_document_v5(document:dict[str,Any], *, config:PoseV5Config, refinement_results:list|None=None)->dict[str,Any]:
    frames=document.get("frames")
    if not isinstance(frames,list): raise ValueError("pose document frames must be an array")
    fps=_fps(document); fusion=JointEvidenceFusion(config.evidence)
    difficult_input=[]; scene_cuts=0
    for index,frame in enumerate(frames):
        if not isinstance(frame,dict): continue
        camera=frame.get("camera_motion") if isinstance(frame.get("camera_motion"),Mapping) else {}
        if camera.get("scene_cut") is True: fusion.reset(); scene_cuts+=1
        translation=camera.get("translation")
        global_translation=(float(translation[0]),float(translation[1])) if isinstance(translation,list) and len(translation)>=2 and all(isinstance(v,(int,float)) for v in translation[:2]) else (0.0,0.0)
        body_quality=frame.get("body_quality") if isinstance(frame.get("body_quality"),Mapping) else {}
        raw_joints=body_quality.get("joints")
        if isinstance(raw_joints,Mapping):
            joints=raw_joints
        elif isinstance(raw_joints,list):
            joints={str(item.get("name")):item for item in raw_joints if isinstance(item,Mapping) and isinstance(item.get("name"),str)}
        else:
            joints={}
        body=frame.get("body") if isinstance(frame.get("body"),Mapping) else {}
        body_scale=float(body.get("scale",1.0)) if isinstance(body.get("scale"),(int,float)) else 1.0
        tracking=frame.get("tracking") if isinstance(frame.get("tracking"),Mapping) else {}
        tracking_quality=float(tracking.get("identity_score",0.0)) if isinstance(tracking.get("identity_score"),(int,float)) else 0.0
        frame_quality=frame.get("frame_quality") if isinstance(frame.get("frame_quality"),Mapping) else {}
        image_quality=float(frame_quality.get("score",0.0)) if isinstance(frame_quality.get("score"),(int,float)) else 0.0
        evidence={}
        for name,value in joints.items():
            if not isinstance(name,str) or not isinstance(value,Mapping): continue
            coordinates=value.get("coordinates"); point=tuple(coordinates[:2]) if isinstance(coordinates,list) and len(coordinates)>=2 and all(isinstance(v,(int,float)) for v in coordinates[:2]) else None
            occlusion=str(value.get("occlusion_state","")).upper()
            result=fusion.evaluate(name,point,timestamp_seconds=_timestamp(frame,index,fps),body_scale=body_scale,
                model_quality=float(value.get("confidence",0.0)) if isinstance(value.get("confidence"),(int,float)) else 0.0,
                kinematic_quality=float(value.get("quality",0.0)) if isinstance(value.get("quality"),(int,float)) else 0.0,
                tracking_quality=tracking_quality,visibility_quality=float(value.get("visibility",0.0)) if isinstance(value.get("visibility"),(int,float)) else 0.0,
                image_quality=image_quality,global_translation=global_translation,occluded="OCCLUDED" in occlusion,out_of_frame=occlusion=="OUT_OF_FRAME")
            evidence[name]=result.to_dict()
        frame["joint_evidence_v5"]=evidence
        reasons=_difficulty_reasons(frame,evidence)
        difficult_input.append({"timestamp_seconds":_timestamp(frame,index,fps),"quality":image_quality if image_quality else _body_quality(body),"tracking_state":tracking.get("state",frame.get("tracking_state")),"camera_shake":camera.get("camera_shake") is True,"reasons":reasons})
    segments,limit=detect_difficult_segments(difficult_input,fps=fps,config=config.refinement)
    refinement=summarize_refinement(segments,refinement_results or [],len(frames)); refinement.update(limit)
    document["schema_version"]=POSE_SCHEMA_VERSION; document["pose_schema_version"]=POSE_SCHEMA_VERSION
    document["pose_version"]=POSE_VERSION; document["worker_version"]=WORKER_VERSION; document["generated_by"]="Ergonomia AI Worker V0.5"
    configuration=document.setdefault("configuration",{})
    if isinstance(configuration,dict): configuration["pose_v5"]={"robust_evidence_fusion":True,"camera_motion_enabled":config.camera.enabled,"refinement_enabled":config.refinement.enabled,"maximum_refinement_ratio":config.refinement.maximum_refinement_ratio,"minimum_quality_gain":config.refinement.minimum_quality_gain,"force_estimation_enabled":False,"weight_estimation_enabled":False}
    summary=document.setdefault("summary",{})
    if isinstance(summary,dict): summary["refinement"]=refinement; summary.setdefault("tracking",{}); summary["scene_cut_count"]=scene_cuts
    document["refinement"]=refinement
    return document


def _difficulty_reasons(frame:Mapping[str,Any],evidence:Mapping[str,Any])->list[str]:
    reasons=[]; tracking=str(frame.get("tracking_state","")).upper()
    if tracking in {"LOST","TRACK_LOST"}: reasons.append("TRACK_LOST")
    if tracking=="REACQUIRING": reasons.append("REACQUIRING")
    if any(isinstance(item,Mapping) and "JERK_OUTLIER" in item.get("rejection_reasons",[]) for item in evidence.values()): reasons.append("BONE_OUTLIER")
    for side in ("left_hand","right_hand"):
        hand=frame.get(side)
        graph=hand.get("graph_v2") if isinstance(hand,Mapping) else None
        if isinstance(graph,Mapping) and isinstance(graph.get("quality"),(int,float)) and graph["quality"]<0.45: reasons.append("LOW_HAND_QUALITY")
    return list(dict.fromkeys(reasons))


def _fps(document:Mapping[str,Any])->float:
    source=document.get("source"); value=source.get("fps") if isinstance(source,Mapping) else None
    return float(value) if isinstance(value,(int,float)) and value>0 else 30.0


def _timestamp(frame:Mapping[str,Any],index:int,fps:float)->float:
    for name in ("source_timestamp_seconds","timestamp","output_timestamp_seconds"):
        value=frame.get(name)
        if isinstance(value,(int,float)) and value>=0:return float(value)
    return index/fps


def _body_quality(body:Mapping[str,Any])->float:
    value=body.get("quality"); return float(value) if isinstance(value,(int,float)) else 0.0
