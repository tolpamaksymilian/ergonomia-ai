# Changelog

## [0.6.0-beta.1] - 2026-08-10

### Added

- evidence-aware RULA i REBA oparte na zweryfikowanych źródłach metod,
- provenance składników i pełnoprawny stan `UNKNOWN`,
- deterministyczna selekcja reprezentatywnych postaw,
- zakresy wyników częściowych bez udawania przedziału ufności,
- `ergonomic-assessment.json` w prywatnym Storage,
- sekcja metod w Analysis Review Workspace i raporcie drukowanym.

### Safety and limitations

- system nie estymuje siły ani masy z obrazu,
- coupling i obciążenie pozostają nieznane bez jawnego inputu,
- RULA/REBA są screeningiem beta i nie zastępują oceny specjalisty,
- obrazy assessment keyframes pozostają kolejnym krokiem; timeline używa obecnie markerów postaw.

## [0.2.1-beta.1] - 2026-08-06

Pierwsza kompletna wersja testowa pełnego przepływu analizy.

### Added

- prywatny upload i preprocessing filmu,
- Pose Pipeline V3.0 z analizą ciała i walidacją dłoni,
- Ergonomics Metrics Engine i osobny Ergonomics Worker,
- Risk Engine oraz Risk Worker z jawnym profilem rozwojowym,
- Report Engine i Report Worker,
- zakończenie analiz stanem `completed` z postępem 100%,
- raport JSON, widok raportu i drukowanie z przeglądarki,
- jeden Pipeline Manager dla wszystkich pięciu workerów,
- automatyczne odświeżanie aktywnych analiz oraz retry bieżącego etapu dla administratora.

### Changed

- jeden centralny model statusów analizy,
- monotoniczny postęp pełnego pipeline’u,
- krótsze i bezpieczne komunikaty błędów,
- kanoniczna lokalizacja migracji i zaktualizowana roadmapa.

### Known limitations

- profil ryzyka jest rozwojowy i nie ma wartości normatywnej,
- brak RULA i REBA,
- brak automatycznego PDF,
- workery działają lokalnie,
- dokładność wymaga dalszej walidacji na zróżnicowanych nagraniach.
