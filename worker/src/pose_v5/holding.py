"""Holding V3: grip is necessary evidence, never sufficient by itself."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence


class HoldingStateV3(StrEnum):
    NOT_HOLDING="NOT_HOLDING"
    POSSIBLE_HOLDING="POSSIBLE_HOLDING"
    LIKELY_HOLDING="LIKELY_HOLDING"
    LIKELY_HOLDING_UNKNOWN_OBJECT="LIKELY_HOLDING_UNKNOWN_OBJECT"
    UNKNOWN="UNKNOWN"


@dataclass(frozen=True)
class HoldingEvidenceV3:
    grip:float
    contact_evidence:float
    object_proximity:float
    common_motion:float
    temporal_persistence:float
    occlusion_pattern:float
    release:float
    quality:float
    object_track_id:int|None=None
    object_class:str|None=None

    def score(self)->float:
        return _clip(0.24*self.grip+0.20*self.contact_evidence+0.14*self.object_proximity+0.18*self.common_motion+0.12*self.temporal_persistence+0.07*self.occlusion_pattern+0.05*self.quality-0.35*self.release)


@dataclass(frozen=True)
class HoldingFrameV3:
    state:HoldingStateV3
    technical_quality:float
    evidence:HoldingEvidenceV3
    holding_score:float
    reasons:tuple[str,...]

    def to_dict(self)->dict[str,object]:
        return {"state":self.state.value,"technical_quality":round(self.technical_quality,6),"holding_score":round(self.holding_score,6),"contact_evidence":round(self.evidence.contact_evidence,6),"common_motion":round(self.evidence.common_motion,6),"release_evidence":round(self.evidence.release,6),"object_track_id":self.evidence.object_track_id,"object_class":self.evidence.object_class,"external_load_known":False,"reasons":list(self.reasons)}


def analyze_holding_v3(evidence:Sequence[HoldingEvidenceV3],durations:Sequence[float], *, confirmation_seconds:float=0.4,release_seconds:float=0.25,unknown_gap_seconds:float=0.2)->list[HoldingFrameV3]:
    if len(evidence)!=len(durations): raise ValueError("evidence and durations must have equal length")
    output=[]; active=False; pending=release_time=unknown_time=0.0
    for item,duration in zip(evidence,durations):
        score=item.score(); reasons=[]
        object_backed=item.object_track_id is not None and item.object_proximity>=0.45
        contact_backed=item.contact_evidence>=0.55 and (item.common_motion>=0.45 or item.occlusion_pattern>=0.65)
        holding_evidence=object_backed or contact_backed
        if item.quality<0.35:
            unknown_time+=duration
            state=HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT if active and unknown_time<=unknown_gap_seconds else HoldingStateV3.UNKNOWN
            if unknown_time>unknown_gap_seconds: active=False; pending=0.0
            output.append(HoldingFrameV3(state,item.quality,item,score,("LOW_HAND_QUALITY",))); continue
        unknown_time=0.0
        if not active:
            candidate=holding_evidence and score>=0.56 and item.release<0.65
            pending=pending+duration if candidate else 0.0
            if pending>=confirmation_seconds:
                active=True; release_time=0.0; state=HoldingStateV3.LIKELY_HOLDING if object_backed else HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT
            elif item.grip>=0.65 or score>=0.38:
                state=HoldingStateV3.POSSIBLE_HOLDING; reasons.append("GRIP_WITHOUT_CONFIRMED_CONTACT" if not holding_evidence else "PERSISTENCE_NOT_CONFIRMED")
            else: state=HoldingStateV3.NOT_HOLDING
        else:
            release_candidate=item.release>=0.65 or score<0.34 or not holding_evidence
            release_time=release_time+duration if release_candidate else 0.0
            if release_time>=release_seconds:
                active=False; pending=0.0; state=HoldingStateV3.NOT_HOLDING; reasons.append("RELEASE_CONFIRMED")
            else: state=HoldingStateV3.LIKELY_HOLDING if object_backed else HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT
        output.append(HoldingFrameV3(state,item.quality,item,score,tuple(reasons)))
    return output


def bimanual_holding_v3(left:Sequence[HoldingFrameV3],right:Sequence[HoldingFrameV3])->list[bool]:
    if len(left)!=len(right): raise ValueError("left and right frame counts must match")
    likely={HoldingStateV3.LIKELY_HOLDING,HoldingStateV3.LIKELY_HOLDING_UNKNOWN_OBJECT}; output=[]
    for a,b in zip(left,right):
        same=a.evidence.object_track_id is not None and a.evidence.object_track_id==b.evidence.object_track_id
        shared_unknown=a.evidence.contact_evidence>=0.65 and b.evidence.contact_evidence>=0.65 and min(a.evidence.common_motion,b.evidence.common_motion)>=0.65
        output.append(bool(a.state in likely and b.state in likely and (same or shared_unknown)))
    return output


def _clip(value:float)->float:return max(0.0,min(1.0,float(value)))
