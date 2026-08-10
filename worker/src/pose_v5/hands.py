"""Hand Pipeline V3 primitives: shape profile, finger chains and assignment hysteresis."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
import math

import numpy as np


class FingerStateV3(StrEnum):
    VALID = "VALID"
    WEAK = "WEAK"
    INVALID = "INVALID"
    OCCLUDED = "OCCLUDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FingerChainResult:
    state: FingerStateV3
    quality: float
    valid_segments: tuple[bool, bool, bool]
    rejection_reasons: tuple[str, ...]


class HandShapeProfileV3:
    """Learns only stable per-hand segment ratios, never missing coordinates."""

    def __init__(self, maximum_samples: int = 90, minimum_update_quality: float = 0.75) -> None:
        self.maximum_samples=maximum_samples; self.minimum_update_quality=minimum_update_quality
        self._samples: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=maximum_samples)))

    def update(self, side:str, measurements:dict[str,float], quality:float)->bool:
        if quality<self.minimum_update_quality or not measurements: return False
        if any(not math.isfinite(value) or value<=0.0 for value in measurements.values()): return False
        for name,value in measurements.items(): self._samples[side][name].append(float(value))
        return True

    def reference(self, side:str, name:str)->tuple[float,float,int]|None:
        values=self._samples.get(side,{}).get(name)
        if not values: return None
        data=np.asarray(values,dtype=float); median=float(np.median(data)); mad=float(np.median(np.abs(data-median)))
        return median,mad,len(data)

    def quality(self, side:str, measurements:dict[str,float])->float:
        scores=[]
        for name,value in measurements.items():
            reference=self.reference(side,name)
            if reference is None: continue
            median,mad,_=reference; tolerance=max(4.0*mad,median*0.22,1e-6)
            scores.append(float(np.clip(1.0-abs(value-median)/tolerance,0.0,1.0)))
        return min(scores) if scores else 0.7


def validate_finger_chain(points:np.ndarray, valid:np.ndarray, *, palm_scale:float, model_quality:float, profile_quality:float, object_occluded:bool=False, previous:np.ndarray|None=None, following:np.ndarray|None=None)->FingerChainResult:
    points=np.asarray(points,dtype=float); valid=np.asarray(valid,dtype=bool)
    if points.shape!=(4,2) or valid.shape!=(4,): return FingerChainResult(FingerStateV3.UNKNOWN,0.0,(False,False,False),("INVALID_CHAIN_SHAPE",))
    segment_valid=[]; reasons=[]
    for index in range(3):
        usable=bool(valid[index] and valid[index+1] and np.isfinite(points[index:index+2]).all())
        length=float(np.linalg.norm(points[index+1]-points[index])) if usable else 0.0
        ratio=length/max(palm_scale,1e-6)
        if usable and not 0.035<=ratio<=0.75: usable=False; reasons.append(f"SEGMENT_{index}_GEOMETRY_OUTLIER")
        segment_valid.append(usable)
    temporal_quality=1.0
    if previous is not None and following is not None and previous.shape==points.shape and following.shape==points.shape:
        midpoint=(previous+following)/2.0; deviations=np.linalg.norm(points-midpoint,axis=1)/max(palm_scale,1e-6)
        if float(np.nanmax(deviations))>1.2: reasons.append("FINGER_TEMPORAL_OUTLIER"); temporal_quality=0.0
    count=sum(segment_valid); quality=float(np.clip(min(model_quality,profile_quality,temporal_quality)*count/3.0,0.0,1.0))
    if count==3 and temporal_quality>0: state=FingerStateV3.VALID if quality>=0.6 else FingerStateV3.WEAK
    elif object_occluded and count>0: state=FingerStateV3.OCCLUDED
    elif count==0 and object_occluded: state=FingerStateV3.OCCLUDED
    elif count==0: state=FingerStateV3.INVALID
    else: state=FingerStateV3.WEAK
    return FingerChainResult(state,quality,tuple(segment_valid),tuple(dict.fromkeys(reasons)))


def assignment_cost(*, wrist_distance:float, forearm_direction_error:float, palm_orientation_error:float, trajectory_error:float, scale_error:float, handedness_penalty:float, identity_change:bool, relative_depth_error:float|None=None)->float:
    depth=relative_depth_error if relative_depth_error is not None else 0.0
    return 0.28*wrist_distance+0.18*forearm_direction_error+0.12*palm_orientation_error+0.20*trajectory_error+0.10*scale_error+0.07*handedness_penalty+0.05*depth+(0.22 if identity_change else 0.0)
