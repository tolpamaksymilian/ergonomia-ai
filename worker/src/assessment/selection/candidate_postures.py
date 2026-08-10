"""Select a small, diverse set of representative postures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..quality import frame_quality
from ..schemas import CandidatePosture, finite_number, integer_or_none
from .ranking import rank_candidates, ranking_score


POSTURE_METRICS = (
    "trunk_inclination_deg", "neck_flexion_deg",
    "left_upper_arm_elevation_deg", "right_upper_arm_elevation_deg",
    "left_wrist_flexion_deg", "right_wrist_flexion_deg",
)
NORMALIZERS = {"trunk_inclination_deg": 60.0, "neck_flexion_deg": 30.0,
    "left_upper_arm_elevation_deg": 90.0, "right_upper_arm_elevation_deg": 90.0,
    "left_wrist_flexion_deg": 30.0, "right_wrist_flexion_deg": 30.0}


def select_candidate_postures(
    ergonomics: Mapping[str, Any],
    pose: Mapping[str, Any] | None = None,
    *,
    maximum_candidates: int = 12,
    minimum_quality: float = 0.55,
    minimum_spacing_seconds: float = 0.75,
) -> list[CandidatePosture]:
    frames=ergonomics.get("frames")
    if not isinstance(frames,list) or not frames: return []
    pose_frames=pose.get("frames") if isinstance(pose,Mapping) and isinstance(pose.get("frames"),list) else []
    raw: list[CandidatePosture]=[]
    severities=[_severity(frame) if isinstance(frame,Mapping) else 0.0 for frame in frames]
    for index, frame in enumerate(frames):
        if not isinstance(frame,Mapping): continue
        pose_frame=pose_frames[index] if index<len(pose_frames) and isinstance(pose_frames[index],Mapping) else None
        quality=frame_quality(frame,pose_frame)
        if quality<minimum_quality: continue
        previous=severities[index-1] if index else -1.0; following=severities[index+1] if index+1<len(frames) else -1.0
        holding=_holding(frame)
        if severities[index] < previous or severities[index] < following:
            if not holding: continue
        timestamp=_timestamp(frame,index,ergonomics)
        duration=_duration_context(frames,index,severities[index])
        events=_events(frame,severities[index],holding,duration)
        raw.append(CandidatePosture(
            candidate_id=f"posture-{index:06d}",frame_position=index,
            source_frame_index=integer_or_none(frame.get("source_frame_index")),output_frame_index=integer_or_none(frame.get("output_frame_index")),
            timestamp_seconds=timestamp,duration_context_seconds=duration,source_events=events,body_side="bilateral",
            quality=quality,severity=severities[index],frequency=1,
        ))
    if not raw:
        valid=[(index,frame) for index,frame in enumerate(frames) if isinstance(frame,Mapping)]
        for index,frame in valid[:1]:
            pose_frame=pose_frames[index] if index<len(pose_frames) and isinstance(pose_frames[index],Mapping) else None
            quality=frame_quality(frame,pose_frame)
            if quality>=minimum_quality:
                raw.append(CandidatePosture(f"posture-{index:06d}",index,integer_or_none(frame.get("source_frame_index")),integer_or_none(frame.get("output_frame_index")),_timestamp(frame,index,ergonomics),0.0,("representative_valid_frame",),"bilateral",quality,severities[index]))
    selected: list[CandidatePosture]=[]
    for candidate in rank_candidates(raw):
        if any(abs(candidate.timestamp_seconds-item.timestamp_seconds)<minimum_spacing_seconds for item in selected): continue
        selected.append(candidate)
        if len(selected)>=maximum_candidates: break
    return sorted(selected,key=lambda item:item.timestamp_seconds)


def _severity(frame: object)->float:
    if not isinstance(frame,Mapping): return 0.0
    metrics=frame.get("metrics")
    if not isinstance(metrics,Mapping): return 0.0
    values=[]
    for name in POSTURE_METRICS:
        metric=metrics.get(name)
        value=finite_number(metric.get("value")) if isinstance(metric,Mapping) and metric.get("valid") is True else None
        if value is not None: values.append(min(abs(value)/NORMALIZERS[name],1.5)/1.5)
    return max(values,default=0.0)


def _holding(frame:Mapping[str,Any])->bool:
    activity=frame.get("hand_activity")
    if not isinstance(activity,Mapping): return False
    return any(isinstance(activity.get(side),Mapping) and "HOLDING" in str(activity[side].get("state",activity[side].get("holding_state",""))).upper() for side in ("left","right"))


def _events(frame:Mapping[str,Any],severity:float,holding:bool,duration:float)->tuple[str,...]:
    events=["local_postural_deviation"]
    if holding: events.append("holding")
    if duration>=1.0: events.append("prolonged_posture")
    if severity>=0.75: events.append("postural_peak")
    return tuple(events)


def _duration_context(frames:Sequence[object],index:int,severity:float)->float:
    if severity<=0.0:return 0.0
    threshold=max(0.0,severity-0.12); start=index; end=index
    while start>0 and _severity(frames[start-1])>=threshold:start-=1
    while end+1<len(frames) and _severity(frames[end+1])>=threshold:end+=1
    first=frames[start] if isinstance(frames[start],Mapping) else {}; last=frames[end] if isinstance(frames[end],Mapping) else {}
    a=finite_number(first.get("timestamp")); b=finite_number(last.get("timestamp"))
    return max(0.0,(b-a)) if a is not None and b is not None else 0.0


def _timestamp(frame:Mapping[str,Any],index:int,document:Mapping[str,Any])->float:
    for key in ("timestamp","output_timestamp_seconds","source_timestamp_seconds"):
        value=finite_number(frame.get(key))
        if value is not None and value>=0:return value
    fps=finite_number(document.get("fps")) or finite_number(document.get("output_fps"))
    return index/fps if fps and fps>0 else float(index)
