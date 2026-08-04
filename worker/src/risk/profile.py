"""Parsing and strict validation of explicit Risk Engine profiles."""

from __future__ import annotations

import math
from collections.abc import Mapping

from .schemas import (
    METRIC_DIRECTIONS,
    PROFILE_STATUSES,
    RISK_LEVELS,
    RISK_SEVERITY,
    KeyFrameRule,
    MetricDirection,
    MetricProfile,
    OverallBand,
    OverallRule,
    PeakGuard,
    PreferredRange,
    ProfileStatus,
    ProfileValidationError,
    RiskProfile,
    SummaryRule,
    ThresholdBand,
)


SUPPORTED_PROFILE_SCHEMAS = frozenset({"1.0"})
SUPPORTED_AGGREGATIONS = frozenset({"weighted_average_with_peak_guard"})


def load_risk_profile(document: object) -> RiskProfile:
    root = _mapping(document, "profile")
    schema_version = _string(root, "schema_version", "profile")
    if schema_version not in SUPPORTED_PROFILE_SCHEMAS:
        raise ProfileValidationError(
            f"Nieobsługiwana schema_version profilu: {schema_version!r}."
        )

    profile_id = _string(root, "profile_id", "profile")
    profile_name = _string(root, "profile_name", "profile")
    profile_version = _string(root, "profile_version", "profile")
    description = _string(root, "description", "profile")
    disclaimer = _string(root, "disclaimer", "profile")

    raw_status = _string(root, "status", "profile")
    if raw_status not in PROFILE_STATUSES:
        raise ProfileValidationError(f"Nieznany status profilu: {raw_status!r}.")
    status: ProfileStatus = raw_status  # type: ignore[assignment]

    normative_method_value = _required(root, "normative_method", "profile")
    if normative_method_value is not None and (
        not isinstance(normative_method_value, str)
        or not normative_method_value.strip()
    ):
        raise ProfileValidationError(
            "profile.normative_method musi być niepustym tekstem albo null."
        )
    normative_method = (
        normative_method_value.strip()
        if isinstance(normative_method_value, str)
        else None
    )

    raw_metrics = _mapping(_required(root, "metrics", "profile"), "profile.metrics")
    if not raw_metrics:
        raise ProfileValidationError("profile.metrics nie może być pustym obiektem.")
    metrics: dict[str, MetricProfile] = {}
    for metric_name, raw_metric in raw_metrics.items():
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise ProfileValidationError("Nazwa metryki w profilu nie może być pusta.")
        normalized_name = metric_name.strip()
        if normalized_name in metrics:
            raise ProfileValidationError(f"Powtórzona metryka profilu: {normalized_name}.")
        metrics[normalized_name] = _parse_metric(normalized_name, raw_metric)

    zones = _parse_zones(
        _mapping(_required(root, "zones", "profile"), "profile.zones"),
        metrics,
    )
    summary_rule = _parse_summary_rule(
        _mapping(
            _required(root, "summary_rule", "profile"),
            "profile.summary_rule",
        )
    )
    overall = _parse_overall(
        _mapping(_required(root, "overall", "profile"), "profile.overall")
    )
    key_frames = _parse_key_frames(
        _mapping(
            _required(root, "key_frames", "profile"),
            "profile.key_frames",
        )
    )

    return RiskProfile(
        schema_version=schema_version,
        profile_id=profile_id,
        profile_name=profile_name,
        profile_version=profile_version,
        status=status,
        normative_method=normative_method,
        description=description,
        disclaimer=disclaimer,
        metrics=metrics,
        zones=zones,
        summary_rule=summary_rule,
        overall=overall,
        key_frames=key_frames,
    )


def select_band(metric: MetricProfile, value: float) -> ThresholdBand:
    for index, band in enumerate(metric.bands):
        above_minimum = band.minimum is None or value >= band.minimum
        below_maximum = (
            band.maximum is None
            or value < band.maximum
            or (index == len(metric.bands) - 1 and value == band.maximum)
        )
        if above_minimum and below_maximum:
            return band
    raise ProfileValidationError(
        f"Wartość {value!r} nie pasuje do żadnego pasma metryki {metric.name}."
    )


def level_for_normalized_score(rule: OverallRule, score: float) -> str:
    bounded = min(1.0, max(0.0, score))
    for index, band in enumerate(rule.score_bands):
        if bounded >= band.minimum and (
            bounded < band.maximum
            or (index == len(rule.score_bands) - 1 and bounded <= band.maximum)
        ):
            return band.level
    raise ProfileValidationError("Ogólny wynik nie pasuje do score_bands profilu.")


def _parse_metric(name: str, value: object) -> MetricProfile:
    path = f"profile.metrics.{name}"
    raw = _mapping(value, path)
    enabled = _boolean(raw, "enabled", path)
    raw_direction = _string(raw, "direction", path)
    if raw_direction not in METRIC_DIRECTIONS:
        raise ProfileValidationError(
            f"Nieznany direction dla {name}: {raw_direction!r}."
        )
    direction: MetricDirection = raw_direction  # type: ignore[assignment]

    weight = _number(raw, "weight", path)
    if weight < 0:
        raise ProfileValidationError(f"{path}.weight nie może być ujemne.")
    minimum_valid_ratio = _number(raw, "minimum_valid_ratio", path)
    if not 0.0 <= minimum_valid_ratio <= 1.0:
        raise ProfileValidationError(
            f"{path}.minimum_valid_ratio musi mieścić się w zakresie 0-1."
        )

    raw_bands = _required(raw, "bands", path)
    if not isinstance(raw_bands, list) or not raw_bands:
        raise ProfileValidationError(f"{path}.bands musi być niepustą tablicą.")
    bands = tuple(
        _parse_band(item, f"{path}.bands[{index}]")
        for index, item in enumerate(raw_bands)
    )
    _validate_metric_bands(name, direction, bands)

    preferred_range: PreferredRange | None = None
    preferred_value = raw.get("preferred_range")
    if direction == "outside_range_is_worse":
        preferred_raw = _mapping(preferred_value, f"{path}.preferred_range")
        preferred_minimum = _number(
            preferred_raw,
            "minimum",
            f"{path}.preferred_range",
        )
        preferred_maximum = _number(
            preferred_raw,
            "maximum",
            f"{path}.preferred_range",
        )
        if preferred_minimum >= preferred_maximum:
            raise ProfileValidationError(
                f"{path}.preferred_range.minimum musi być mniejsze od maximum."
            )
        preferred_range = PreferredRange(preferred_minimum, preferred_maximum)
        provisional = MetricProfile(
            name,
            enabled,
            direction,
            weight,
            minimum_valid_ratio,
            bands,
            preferred_range,
        )
        preferred_checks = (
            preferred_minimum,
            (preferred_minimum + preferred_maximum) / 2.0,
            math.nextafter(preferred_maximum, -math.inf),
        )
        if any(
            select_band(provisional, value).level != "low"
            for value in preferred_checks
        ):
            raise ProfileValidationError(
                f"Cały preferred_range metryki {name} musi należeć do pasma low."
            )
    elif preferred_value is not None:
        raise ProfileValidationError(
            f"{path}.preferred_range jest dozwolone tylko dla outside_range_is_worse."
        )

    return MetricProfile(
        name=name,
        enabled=enabled,
        direction=direction,
        weight=weight,
        minimum_valid_ratio=minimum_valid_ratio,
        bands=bands,
        preferred_range=preferred_range,
    )


def _parse_band(value: object, path: str) -> ThresholdBand:
    raw = _mapping(value, path)
    raw_level = _string(raw, "level", path)
    if raw_level not in RISK_LEVELS:
        raise ProfileValidationError(f"Nieznany level w {path}: {raw_level!r}.")
    minimum = _nullable_number(raw, "minimum", path)
    maximum = _nullable_number(raw, "maximum", path)
    if minimum is not None and maximum is not None and minimum >= maximum:
        raise ProfileValidationError(f"{path}.minimum musi być mniejsze od maximum.")
    score = _number(raw, "score", path)
    if score < 0:
        raise ProfileValidationError(f"{path}.score nie może być ujemny.")
    return ThresholdBand(
        level=raw_level,  # type: ignore[arg-type]
        minimum=minimum,
        maximum=maximum,
        score=score,
    )


def _validate_metric_bands(
    name: str,
    direction: MetricDirection,
    bands: tuple[ThresholdBand, ...],
) -> None:
    if bands[0].minimum is not None or bands[-1].maximum is not None:
        raise ProfileValidationError(
            f"Pasma metryki {name} muszą pokrywać pełny zakres od null do null."
        )

    seen_ranges: set[tuple[float | None, float | None]] = set()
    for index, band in enumerate(bands):
        range_key = (band.minimum, band.maximum)
        if range_key in seen_ranges:
            raise ProfileValidationError(
                f"Metryka {name} zawiera dwa pasma z tym samym zakresem."
            )
        seen_ranges.add(range_key)
        if index == 0:
            continue
        previous = bands[index - 1]
        if previous.maximum is None or band.minimum is None:
            raise ProfileValidationError(f"Nieprawidłowa kolejność pasm metryki {name}.")
        if band.minimum < previous.maximum:
            raise ProfileValidationError(f"Nakładające się pasma metryki {name}.")
        if band.minimum > previous.maximum:
            raise ProfileValidationError(f"Luka pomiędzy pasmami metryki {name}.")

    severities = [RISK_SEVERITY[band.level] for band in bands]
    if direction == "higher_is_worse" and severities != sorted(severities):
        raise ProfileValidationError(
            f"Poziomy metryki {name} nie rosną zgodnie z higher_is_worse."
        )
    if direction == "lower_is_worse" and severities != sorted(
        severities,
        reverse=True,
    ):
        raise ProfileValidationError(
            f"Poziomy metryki {name} nie maleją zgodnie z lower_is_worse."
        )
    if direction == "outside_range_is_worse":
        lowest_index = min(
            range(len(bands)),
            key=lambda index: RISK_SEVERITY[bands[index].level],
        )
        left = severities[: lowest_index + 1]
        right = severities[lowest_index:]
        if left != sorted(left, reverse=True) or right != sorted(right):
            raise ProfileValidationError(
                f"Poziomy metryki {name} nie rosną na zewnątrz preferred_range."
            )

    score_by_level: dict[str, float] = {}
    for band in bands:
        previous_score = score_by_level.setdefault(band.level, band.score)
        if not math.isclose(previous_score, band.score):
            raise ProfileValidationError(
                f"Powtórzony level {band.level} metryki {name} musi mieć ten sam score."
            )
    ordered_levels = sorted(score_by_level, key=lambda level: RISK_SEVERITY[level])
    ordered_scores = [score_by_level[level] for level in ordered_levels]
    if ordered_scores != sorted(ordered_scores):
        raise ProfileValidationError(
            f"Wyniki score metryki {name} muszą rosnąć wraz z poziomem."
        )


def _parse_zones(
    raw: Mapping[str, object],
    metrics: Mapping[str, MetricProfile],
) -> dict[str, tuple[str, ...]]:
    if not raw:
        raise ProfileValidationError("profile.zones nie może być pustym obiektem.")
    zones: dict[str, tuple[str, ...]] = {}
    assigned: dict[str, str] = {}
    for zone_name, raw_names in raw.items():
        if not isinstance(zone_name, str) or not zone_name.strip():
            raise ProfileValidationError("Nazwa strefy nie może być pusta.")
        if not isinstance(raw_names, list) or not raw_names:
            raise ProfileValidationError(
                f"profile.zones.{zone_name} musi być niepustą tablicą."
            )
        metric_names: list[str] = []
        for raw_name in raw_names:
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise ProfileValidationError(
                    f"Strefa {zone_name} zawiera nieprawidłową nazwę metryki."
                )
            metric_name = raw_name.strip()
            if metric_name not in metrics:
                raise ProfileValidationError(
                    f"Strefa {zone_name} odwołuje się do nieznanej metryki {metric_name}."
                )
            if metric_name in assigned:
                raise ProfileValidationError(
                    f"Metryka {metric_name} występuje w więcej niż jednej strefie."
                )
            assigned[metric_name] = zone_name
            metric_names.append(metric_name)
        zones[zone_name.strip()] = tuple(metric_names)

    missing_enabled = [
        name
        for name, metric in metrics.items()
        if metric.enabled and name not in assigned
    ]
    if missing_enabled:
        raise ProfileValidationError(
            "Aktywne metryki bez strefy: " + ", ".join(sorted(missing_enabled))
        )
    return zones


def _parse_summary_rule(raw: Mapping[str, object]) -> SummaryRule:
    sequence = _number(raw, "minimum_sequence_seconds", "profile.summary_rule")
    exposure = _number(raw, "minimum_exposure_ratio", "profile.summary_rule")
    percentile = _number(raw, "percentile_for_summary", "profile.summary_rule")
    if sequence < 0:
        raise ProfileValidationError("minimum_sequence_seconds nie może być ujemne.")
    if not 0.0 <= exposure <= 1.0:
        raise ProfileValidationError("minimum_exposure_ratio musi być w zakresie 0-1.")
    if not 0.0 < percentile <= 100.0:
        raise ProfileValidationError("percentile_for_summary musi być w zakresie (0, 100].")
    return SummaryRule(sequence, exposure, percentile)


def _parse_overall(raw: Mapping[str, object]) -> OverallRule:
    coverage = _number(raw, "minimum_data_coverage", "profile.overall")
    if not 0.0 <= coverage <= 1.0:
        raise ProfileValidationError("overall.minimum_data_coverage musi być w zakresie 0-1.")
    aggregation = _string(raw, "aggregation", "profile.overall")
    if aggregation not in SUPPORTED_AGGREGATIONS:
        raise ProfileValidationError(f"Nieobsługiwana strategia agregacji: {aggregation!r}.")

    peak_raw = _mapping(
        _required(raw, "peak_guard", "profile.overall"),
        "profile.overall.peak_guard",
    )
    peak_enabled = _boolean(peak_raw, "enabled", "profile.overall.peak_guard")
    peak_level = _string(peak_raw, "minimum_level", "profile.overall.peak_guard")
    if peak_level not in RISK_LEVELS:
        raise ProfileValidationError(f"Nieznany peak_guard.minimum_level: {peak_level!r}.")
    peak_ratio = _number(
        peak_raw,
        "minimum_exposure_ratio",
        "profile.overall.peak_guard",
    )
    if not 0.0 <= peak_ratio <= 1.0:
        raise ProfileValidationError(
            "peak_guard.minimum_exposure_ratio musi być w zakresie 0-1."
        )

    raw_bands = _required(raw, "score_bands", "profile.overall")
    if not isinstance(raw_bands, list) or not raw_bands:
        raise ProfileValidationError("overall.score_bands musi być niepustą tablicą.")
    score_bands: list[OverallBand] = []
    for index, item in enumerate(raw_bands):
        path = f"profile.overall.score_bands[{index}]"
        band = _mapping(item, path)
        level = _string(band, "level", path)
        if level not in RISK_LEVELS:
            raise ProfileValidationError(f"Nieznany level w {path}: {level!r}.")
        minimum = _number(band, "minimum", path)
        maximum = _number(band, "maximum", path)
        if not 0.0 <= minimum < maximum <= 1.0:
            raise ProfileValidationError(
                f"{path} musi mieć zakres 0 <= minimum < maximum <= 1."
            )
        score_bands.append(OverallBand(level, minimum, maximum))  # type: ignore[arg-type]
    if not math.isclose(score_bands[0].minimum, 0.0) or not math.isclose(
        score_bands[-1].maximum,
        1.0,
    ):
        raise ProfileValidationError("overall.score_bands musi pokrywać zakres 0-1.")
    for previous, current in zip(score_bands, score_bands[1:]):
        if current.minimum < previous.maximum:
            raise ProfileValidationError("Nakładające się overall.score_bands.")
        if current.minimum > previous.maximum:
            raise ProfileValidationError("Luka pomiędzy overall.score_bands.")
    severities = [RISK_SEVERITY[band.level] for band in score_bands]
    if severities != sorted(severities):
        raise ProfileValidationError("Poziomy overall.score_bands muszą rosnąć.")

    return OverallRule(
        minimum_data_coverage=coverage,
        aggregation="weighted_average_with_peak_guard",
        peak_guard=PeakGuard(
            peak_enabled,
            peak_level,  # type: ignore[arg-type]
            peak_ratio,
        ),
        score_bands=tuple(score_bands),
    )


def _parse_key_frames(raw: Mapping[str, object]) -> KeyFrameRule:
    separation = _number(
        raw,
        "minimum_time_separation_seconds",
        "profile.key_frames",
    )
    if separation < 0:
        raise ProfileValidationError(
            "key_frames.minimum_time_separation_seconds nie może być ujemne."
        )
    return KeyFrameRule(separation)


def _required(mapping: Mapping[str, object], key: str, path: str) -> object:
    if key not in mapping:
        raise ProfileValidationError(f"Brak wymaganego pola: {path}.{key}.")
    return mapping[key]


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ProfileValidationError(f"{path} musi być obiektem JSON.")
    return value


def _string(mapping: Mapping[str, object], key: str, path: str) -> str:
    value = _required(mapping, key, path)
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(f"{path}.{key} musi być niepustym tekstem.")
    return value.strip()


def _boolean(mapping: Mapping[str, object], key: str, path: str) -> bool:
    value = _required(mapping, key, path)
    if not isinstance(value, bool):
        raise ProfileValidationError(f"{path}.{key} musi być wartością boolean.")
    return value


def _number(mapping: Mapping[str, object], key: str, path: str) -> float:
    value = _required(mapping, key, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileValidationError(f"{path}.{key} musi być liczbą.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ProfileValidationError(f"{path}.{key} musi być liczbą skończoną.")
    return numeric


def _nullable_number(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> float | None:
    value = _required(mapping, key, path)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileValidationError(f"{path}.{key} musi być liczbą albo null.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ProfileValidationError(f"{path}.{key} musi być liczbą skończoną.")
    return numeric
