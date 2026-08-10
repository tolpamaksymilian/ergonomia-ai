"""Evidence-aware REBA whole-body range evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Any

from ..quality import applicability, evidence_coverage
from ..schemas import EvidenceValue, REBA_VERSION, ScoreRange
from .components import build_components
from .schemas import REBA_METHOD_REFERENCE, REBA_REQUIRED_COMPONENTS
from .tables import risk_level, table_a, table_b, table_c


def assess_reba_candidate(frame: Mapping[str, Any], pose_frame: Mapping[str, Any] | None, side: str, *, quality: float, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if side not in {"left", "right"}: raise ValueError("REBA side must be left or right")
    components=build_components(frame,pose_frame,side,context)
    required=[components[name] for name in REBA_REQUIRED_COMPONENTS]
    coverage=evidence_coverage(required); possible=_possible_scores(components)
    score_range=ScoreRange(min(possible),max(possible)) if possible else None
    status="INSUFFICIENT_DATA" if quality < 0.5 or coverage < 0.3 else "COMPLETE" if all(item.resolved for item in components.values()) else "PARTIAL"
    final=score_range.minimum if status=="COMPLETE" and score_range and score_range.minimum==score_range.maximum else None
    missing=sorted({value for component in components.values() for value in component.missing_evidence})
    return {
        "method":"REBA","method_version":REBA_VERSION,"method_reference":REBA_METHOD_REFERENCE,"side":side,
        "status":status,"applicability":applicability(coverage,quality),"evidence_coverage_ratio":round(coverage,6),"data_quality":round(quality,6),
        "final_score":final,"score_range":score_range.to_dict() if score_range else None,
        "risk_level":risk_level(final) if final is not None else None,
        "risk_level_range":[risk_level(score_range.minimum),risk_level(score_range.maximum)] if score_range else None,
        "components":{name:component.to_dict() for name,component in components.items()},"missing_inputs":missing,
        "decision_reasons":[f"status_{status.lower()}"] + (["unresolved_required_components_propagated_to_score_range"] if missing else []),
    }


def _possible_scores(c: Mapping[str,EvidenceValue])->set[int]:
    if any(not _scores(c[name]) for name in ("neck","trunk","legs","upper_arm","lower_arm","wrist","load_force","coupling","activity")): return set()
    a={table_a(_clamp(t+ta,1,5),_clamp(n+na,1,3),legs) for t,ta,n,na,legs in product(*(_scores(c[name]) for name in ("trunk","trunk_adjustment","neck","neck_adjustment","legs")))}
    b={table_b(_clamp(ua+uaa,1,6),la,_clamp(w+wa,1,3)) for ua,uaa,la,w,wa in product(*(_scores(c[name]) for name in ("upper_arm","upper_arm_adjustment","lower_arm","wrist","wrist_adjustment")))}
    return {min(15,table_c(score_a+load,score_b+coupling)+activity) for score_a,score_b,load,coupling,activity in product(a,b,_scores(c["load_force"]),_scores(c["coupling"]),_scores(c["activity"]))}


def _scores(component:EvidenceValue)->tuple[int,...]: return (component.score,) if component.score is not None else component.possible_scores
def _clamp(value:int,minimum:int,maximum:int)->int: return max(minimum,min(maximum,value))
