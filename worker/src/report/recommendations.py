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

MANUAL_INPUTS: dict[str, tuple[str, str, str]] = {
    "handled_load": ("Masa przenoszonego przedmiotu", "high", "Wartość w kilogramach uzupełnia kompatybilne pola OWAS i EJMS. Kategorie RULA i REBA nie są z niej wyznaczane arbitralnie."),
    "rula_force_load": ("Kategoria siły lub obciążenia RULA", "high", "Informacja może zmienić zakres wyniku RULA i musi być podana zgodnie z definicją tej metody."),
    "reba_load_force": ("Kategoria siły lub obciążenia REBA", "high", "Informacja może zmienić zakres wyniku REBA i musi być podana zgodnie z definicją tej metody."),
    "coupling": ("Jakość chwytu lub uchwytu", "high", "Informacja jest potrzebna do oceny jakości chwytu w REBA."),
    "activity": ("Powtarzalność albo utrzymywanie pozycji", "medium", "Potwierdzenie jest potrzebne, gdy czasu aktywności nie da się jednoznacznie wyznaczyć z filmu."),
    "rula_muscle_use": ("Długotrwałe lub powtarzalne użycie mięśni", "medium", "Informacja może zmienić wynik RULA."),
    "balanced_weight_distribution": ("Równomierne podparcie i rozkład ciężaru", "medium", "Obraz 2D nie zawsze pozwala potwierdzić sposób podparcia nóg."),
    "foot_support": ("Podparcie stóp", "medium", "Informacja uzupełnia ocenę stabilności pozycji."),
    "weight_distribution_and_leg_support": ("Rozkład ciężaru i podparcie nóg", "medium", "Kąty nóg są wyznaczane z Pose, ale rodzaju podparcia nie należy zgadywać."),
    "shoulder_elevation": ("Uniesienie barku", "medium", "Potwierdź tylko wtedy, gdy ustawienie barku nie jest czytelne na nagraniu."),
    "arm_abduction": ("Odwiedzenie ramienia", "medium", "Widok kamery może nie dostarczać wiarygodnej geometrii czołowej."),
    "arm_support": ("Podparcie ramienia", "medium", "Podparcie nie jest zgadywane z samego szkieletu."),
    "arm_across_midline": ("Przekroczenie linii środkowej ciała przez ramię lub przedramię", "medium", "Potwierdzenie jest wymagane przy niejednoznacznym widoku kamery."),
    "radial_ulnar_deviation": ("Odchylenie nadgarstka na bok", "medium", "Obraz 2D może nie pokazywać tego ruchu wiarygodnie."),
    "wrist_pronation_supination": ("Skręt przedramienia lub nadgarstka", "medium", "Rotacja osiowa pozostaje nieznana bez jednoznacznego dowodu."),
    "neck_side_bend": ("Boczne zgięcie szyi", "medium", "Potwierdź, gdy kierunek kamery uniemożliwia wiarygodny pomiar."),
    "neck_twist": ("Skręt szyi", "medium", "Rotacja osiowa w obrazie 2D pozostaje niepewna."),
    "trunk_side_bend": ("Boczne zgięcie tułowia", "medium", "Potwierdź, gdy geometria czołowa nie jest dostępna."),
    "trunk_twist": ("Skręt tułowia", "medium", "Rotacja osiowa nie jest automatycznie zakładana na podstawie obrazu 2D."),
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
    # Coverage is a quality limitation, not a user-provided scoring input.
    # Asking for confirmation cannot reconstruct missing frame evidence.
    _ = valid_metric_ratio
    if isinstance(assessment, Mapping):
        for method in ("rula", "reba"):
            raw = assessment.get(method)
            if not isinstance(raw, Mapping) or raw.get("status") == "COMPLETE":
                continue
            representative = raw.get("representative")
            if isinstance(representative, Mapping) and not _score_range_can_change(representative.get("score_range")):
                continue
            missing = representative.get("missing_inputs") if isinstance(representative, Mapping) else []
            for name in missing if isinstance(missing, list) else []:
                code = str(name)
                normalized = _manual_code(code)
                definition = MANUAL_INPUTS.get(normalized)
                if definition is None:
                    continue
                label, impact, explanation = definition
                items.append({"code": normalized, "label": label, "impact": impact, "explanation": explanation})
    if isinstance(hand_activity, Mapping) and hand_activity.get("external_load_known") is not True:
        label, impact, explanation = MANUAL_INPUTS["handled_load"]
        items.append({"code": "handled_load", "label": label, "impact": impact, "explanation": explanation})
    deduplicated = {item["code"]: item for item in items}
    priority = {"high": 0, "medium": 1, "optional": 2}
    return sorted(deduplicated.values(), key=lambda item: (priority.get(item.get("impact", "optional"), 2), item["label"]))[:5]


def _manual_code(value: str) -> str:
    if value == "rula_force_load":
        return "rula_force_load"
    if value == "reba_load_force":
        return "reba_load_force"
    if value in {"load_force", "force_load", "external_load"}:
        return "handled_load"
    if value == "reba_coupling":
        return "coupling"
    if value == "reba_activity":
        return "activity"
    for side in ("left_", "right_"):
        if value.startswith(side):
            return value[len(side):]
    return value


def _score_range_can_change(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    minimum = value.get("min")
    maximum = value.get("max")
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        return True
    return float(minimum) != float(maximum)
