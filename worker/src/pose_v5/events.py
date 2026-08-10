"""Deterministic posture event aggregation without threshold scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PostureEvent:
    event_type: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    peak: float | None
    median: float | None
    quality: float
    source_metrics: tuple[str, ...]

    def to_dict(self)->dict[str,object]:
        return {"event_type":self.event_type,"start_seconds":round(self.start_seconds,6),"end_seconds":round(self.end_seconds,6),"duration_seconds":round(self.duration_seconds,6),"peak":self.peak,"median":self.median,"quality":round(self.quality,6),"source_metrics":list(self.source_metrics)}


def merge_metric_events(frames: Sequence[Mapping[str,Any]], metric_name:str, event_type:str, *, minimum_value:float, maximum_gap_seconds:float=0.25)->list[PostureEvent]:
    samples=[]
    for frame in frames:
        metrics=frame.get("metrics"); metric=metrics.get(metric_name) if isinstance(metrics,Mapping) else None
        timestamp=frame.get("source_timestamp_seconds",frame.get("timestamp",frame.get("output_timestamp_seconds")))
        if isinstance(metric,Mapping) and metric.get("valid") is True and isinstance(metric.get("value"),(int,float)) and isinstance(timestamp,(int,float)):
            value=float(metric["value"]); quality=float(metric.get("quality",0.0))
            if abs(value)>=minimum_value: samples.append((float(timestamp),value,max(0.0,min(1.0,quality))))
    groups=[]
    for sample in samples:
        if not groups or sample[0]-groups[-1][-1][0]>maximum_gap_seconds: groups.append([sample])
        else: groups[-1].append(sample)
    output=[]
    for group in groups:
        values=sorted(item[1] for item in group); median=values[len(values)//2]
        output.append(PostureEvent(event_type,group[0][0],group[-1][0],max(0.0,group[-1][0]-group[0][0]),max(values,key=abs),median,min(item[2] for item in group),(metric_name,)))
    return output
