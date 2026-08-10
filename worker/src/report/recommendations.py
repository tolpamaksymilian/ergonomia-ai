"""Bounded deterministic recommendations and manual-confirmation prompts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


RECOMMENDATIONS = {
    "neck": "Sprawdź wysokość i położenie obserwowanego pola pracy, aby ograniczyć długotrwałe pochylenie szyi.",
    "trunk": "Zweryfikuj wysokość i zasięg obszaru pracy oraz możliwość utrzymania bardziej neutralnej pozycji tułowia.",
    "left_upper_limb": "Sprawdź zasięg pracy lewej kończyny i możliwość przybliżenia obsługiwanych elementów.",
    "right_upper_limb": "Sprawdź zasięg pracy prawej kończyny i możliwość przybliżenia obsługiwanych elementów.",
    "left_hand": "Zweryfikuj sposób chwytu lewą dłonią oraz możliwość ograniczenia utrzymywania nadgarstka poza pozycją neutralną.",
    "right_hand": "Zweryfikuj sposób chwytu prawą dłonią oraz możliwość ograniczenia utrzymywania nadgarstka poza pozycją neutralną.",
}


def build_recommendations(findings: Sequence[Mapping[str, Any]], *, enabled: bool = True, maximum: int = 5) -> list[dict[str, Any]]:
    if not enabled:
        return []
    output: list[dict[str, Any]] = []
    for finding in findings:
        zone = finding.get("zone")
        if not isinstance(zone, str) or zone not in RECOMMENDATIONS:
            continue
        if finding.get("data_quality") not in {"sufficient", "limited"}:
            continue
        output.append({
            "recommendation_id": f"review:{zone}",
            "zone": zone,
            "priority": finding.get("level"),
            "text": RECOMMENDATIONS[zone],
            "evidence": {
                "finding_id": finding.get("finding_id"),
                "metric_names": list(finding.get("metric_names", [])),
                "duration_seconds": finding.get("duration_seconds"),
                "timestamp_seconds": finding.get("timestamp_seconds"),
            },
            "requires_specialist_review": True,
        })
        if len(output) >= maximum:
            break
    return output


def build_manual_confirmation(
    assessment: Mapping[str, Any] | None,
    *,
    valid_metric_ratio: float,
    hand_activity: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if valid_metric_ratio < 0.65:
        items.append({"code": "limited_data_coverage", "label": "Potwierdź pozycję w fragmentach o ograniczonej widoczności."})
    if isinstance(assessment, Mapping):
        for method in ("rula", "reba"):
            raw = assessment.get(method)
            if not isinstance(raw, Mapping) or raw.get("status") == "COMPLETE":
                continue
            representative = raw.get("representative")
            missing = representative.get("missing_inputs") if isinstance(representative, Mapping) else []
            for name in missing if isinstance(missing, list) else []:
                code = str(name)
                items.append({"code": f"{method}_{code}", "label": f"Uzupełnij ręcznie parametr {code.replace('_', ' ')} dla metody {method.upper()}."})
    if isinstance(hand_activity, Mapping) and hand_activity.get("external_load_known") is not True:
        items.append({"code": "external_load_unknown", "label": "Potwierdź masę i charakter obciążenia zewnętrznego; system ich nie estymuje."})
    deduplicated = {item["code"]: item for item in items}
    return list(deduplicated.values())
