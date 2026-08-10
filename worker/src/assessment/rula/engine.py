"""Evidence-aware, side-specific RULA range evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Any

from ..quality import applicability, evidence_coverage
from ..schemas import EvidenceValue, RULA_VERSION, ScoreRange
from .components import build_components
from .schemas import RULA_METHOD_REFERENCE, RULA_REQUIRED_COMPONENTS
from .tables import action_level, table_a, table_b, table_c


def assess_rula_candidate(
    frame: Mapping[str, Any],
    side: str,
    *,
    quality: float,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if side not in {"left", "right"}:
        raise ValueError("RULA side must be left or right")
    components = build_components(frame, side, context)
    required = [components[name] for name in RULA_REQUIRED_COMPONENTS]
    coverage = evidence_coverage(required)
    possible = _possible_scores(components)
    score_range = ScoreRange(min(possible), max(possible)) if possible else None
    status = "INSUFFICIENT_DATA" if quality < 0.5 or coverage < 0.3 else "COMPLETE" if all(item.resolved for item in components.values()) else "PARTIAL"
    final_score = score_range.minimum if status == "COMPLETE" and score_range and score_range.minimum == score_range.maximum else None
    missing = sorted({evidence for component in components.values() for evidence in component.missing_evidence})
    return {
        "method": "RULA",
        "method_version": RULA_VERSION,
        "method_reference": RULA_METHOD_REFERENCE,
        "side": side,
        "status": status,
        "applicability": applicability(coverage, quality),
        "evidence_coverage_ratio": round(coverage, 6),
        "data_quality": round(quality, 6),
        "final_score": final_score,
        "score_range": score_range.to_dict() if score_range else None,
        "action_level": action_level(final_score) if final_score is not None else None,
        "action_level_range": [action_level(score_range.minimum), action_level(score_range.maximum)] if score_range else None,
        "components": {name: component.to_dict() for name, component in components.items()},
        "missing_inputs": missing,
        "decision_reasons": _decision_reasons(status, missing),
    }


def _possible_scores(components: Mapping[str, EvidenceValue]) -> set[int]:
    required = ("upper_arm", "lower_arm", "wrist", "wrist_twist", "neck", "trunk", "legs")
    if any(not _scores(components[name]) for name in required):
        return set()
    scores_a = {
        table_a(_clamp(ua + ua_adj, 1, 6), _clamp(la + la_adj, 1, 3), _clamp(w + w_adj, 1, 4), wt)
        for ua, ua_adj, la, la_adj, w, w_adj, wt in product(*(_scores(components[name]) for name in ("upper_arm", "upper_arm_adjustment", "lower_arm", "lower_arm_adjustment", "wrist", "wrist_adjustment", "wrist_twist")))
    }
    scores_b = {
        table_b(_clamp(n + na, 1, 6), _clamp(t + ta, 1, 6), legs)
        for n, na, t, ta, legs in product(*(_scores(components[name]) for name in ("neck", "neck_adjustment", "trunk", "trunk_adjustment", "legs")))
    }
    muscle = _scores(components["muscle_use"]); force = _scores(components["force_load"])
    if not muscle or not force:
        return set()
    return {table_c(a + use + load, b + use + load) for a, b, use, load in product(scores_a, scores_b, muscle, force)}


def _scores(component: EvidenceValue) -> tuple[int, ...]:
    return (component.score,) if component.score is not None else component.possible_scores


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _decision_reasons(status: str, missing: list[str]) -> list[str]:
    reasons = [f"status_{status.lower()}"]
    if missing: reasons.append("unresolved_required_components_propagated_to_score_range")
    return reasons
