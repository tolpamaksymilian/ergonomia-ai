"""Deterministic, evidence-linked findings for Analysis Report V2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SEVERITY = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "insufficient_data": 0}
ZONE_LABELS = {
    "neck": "szyi", "trunk": "tułowia", "left_upper_limb": "lewej kończyny górnej",
    "right_upper_limb": "prawej kończyny górnej", "left_hand": "lewej dłoni",
    "right_hand": "prawej dłoni",
}


def build_priority_findings(
    risk: Mapping[str, Any],
    *,
    maximum: int = 6,
) -> list[dict[str, Any]]:
    """Rank and deduplicate persistent metric findings, never inventing data."""

    metrics = risk.get("metrics")
    keyframes = risk.get("key_frames")
    if not isinstance(metrics, Mapping):
        return []
    keys = keyframes if isinstance(keyframes, list) else []
    candidates: list[dict[str, Any]] = []
    for metric_name, raw in metrics.items():
        if not isinstance(metric_name, str) or not isinstance(raw, Mapping):
            continue
        level = str(raw.get("final_level", "insufficient_data"))
        if level not in {"moderate", "high", "critical"}:
            continue
        zone = _zone_for_metric(metric_name, risk)
        exposure = raw.get("exposure") if isinstance(raw.get("exposure"), Mapping) else {}
        duration = _number(exposure.get(f"{level}_duration_seconds"))
        ratio = _number(exposure.get(f"{level}_exposure_ratio"))
        quality = str(raw.get("data_quality", "insufficient"))
        if quality == "insufficient":
            continue
        keyframe = _best_keyframe(keys, metric_name)
        timestamp = _number(keyframe.get("timestamp_seconds")) if keyframe else None
        score = _number(raw.get("weighted_score")) or 0.0
        candidates.append({
            "finding_id": f"{zone}:{metric_name}",
            "title": f"Podwyższona ekspozycja w obszarze {ZONE_LABELS.get(zone, zone)}",
            "summary": _summary(level, duration, ratio),
            "level": level,
            "zone": zone,
            "metric_names": [metric_name],
            "duration_seconds": duration,
            "exposure_ratio": ratio,
            "timestamp_seconds": timestamp,
            "keyframe": dict(keyframe) if keyframe else None,
            "data_quality": quality,
            "weighted_score": score,
            "decision_reasons": list(raw.get("decision_reasons", [])) if isinstance(raw.get("decision_reasons"), list) else [],
        })
    candidates.sort(key=lambda item: (-SEVERITY[item["level"]], -item["weighted_score"], -(item["duration_seconds"] or 0.0), item["finding_id"]))
    # One concise finding per body zone removes repeated descriptions of the
    # same posture while retaining all contributing metric names as evidence.
    merged: dict[str, dict[str, Any]] = {}
    for item in candidates:
        zone = item["zone"]
        if zone not in merged:
            merged[zone] = item
            continue
        current = merged[zone]
        current["metric_names"] = list(dict.fromkeys([*current["metric_names"], *item["metric_names"]]))
        current["decision_reasons"] = list(dict.fromkeys([*current["decision_reasons"], *item["decision_reasons"]]))
    return list(merged.values())[: max(0, maximum)]


def _zone_for_metric(metric_name: str, risk: Mapping[str, Any]) -> str:
    zones = risk.get("zones")
    if isinstance(zones, Mapping):
        for zone_name, zone in zones.items():
            if not isinstance(zone_name, str) or not isinstance(zone, Mapping):
                continue
            configured = zone.get("metric_names")
            if isinstance(configured, list) and metric_name in configured:
                return zone_name
    if metric_name.startswith("neck_"): return "neck"
    if metric_name.startswith("trunk_"): return "trunk"
    if metric_name.startswith("left_hand") or metric_name.startswith("left_pinch"): return "left_hand"
    if metric_name.startswith("right_hand") or metric_name.startswith("right_pinch"): return "right_hand"
    if metric_name.startswith("left_"): return "left_upper_limb"
    if metric_name.startswith("right_"): return "right_upper_limb"
    return "unknown"


def _best_keyframe(keyframes: list[Any], metric_name: str) -> Mapping[str, Any] | None:
    matching = [item for item in keyframes if isinstance(item, Mapping) and item.get("metric_name") == metric_name]
    if not matching: return None
    return max(matching, key=lambda item: (_number(item.get("quality")) or 0.0, _number(item.get("weighted_score")) or 0.0))


def _summary(level: str, duration: float | None, ratio: float | None) -> str:
    level_text = {"moderate": "umiarkowany", "high": "wysoki", "critical": "krytyczny"}[level]
    if duration is not None:
        return f"Zarejestrowano {level_text} poziom przez {duration:.1f} s poprawnych obserwacji."
    if ratio is not None:
        return f"Zarejestrowano {level_text} poziom w {ratio * 100:.1f}% poprawnych obserwacji."
    return f"Zarejestrowano {level_text} poziom; czas ekspozycji wymaga potwierdzenia."


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
