# Analysis Report V2

`analysis-report-v2.2-beta.1` jest deterministycznym, krótkim widokiem istniejących wyników Pose, Metrics, Risk i Assessment. Nie przelicza RULA/REBA i nie używa modelu językowego.

## Sekcje

- `executive_summary` — maksymalnie sześć krótkich zdań;
- `priority_findings` — maksymalnie sześć wniosków po rankingu i deduplikacji obszaru, z metryką, ekspozycją, timestampem i klatką, jeśli istnieje;
- `exposures` — czasy wyłącznie z poprawnych obserwacji;
- `hand_summary` — lewa, prawa i oburęczna aktywność, bez estymacji ciężaru i siły;
- `assessment_summary` — RULA i REBA osobno, z zachowaniem `PARTIAL` i braków;
- `recommendations` — maksymalnie pięć deterministycznych kierunków do weryfikacji, zawsze związanych z dowodem;
- `manual_confirmation` — parametry i fragmenty wymagające decyzji człowieka;
- `quality_summary` — techniczne pokrycie danymi, nie accuracy;
- `technical_appendix` — szczegółowe obszary, metryki, kluczowe momenty i powody decyzji.

Wnioski o jakości `insufficient` nie generują zaleceń. Recommendation Engine można wyłączyć, a jego brak nie usuwa pozostałych sekcji raportu. Nie ma medycznych twierdzeń, certyfikacji, estymacji masy ani siły.

Frontend rozpoznaje historyczny `analysis-report-v1.0` oraz V2. Pola V1 pozostają w dokumencie V2 jako zgodna warstwa prezentacyjna, a szczegóły są dodatkowo dostępne w appendix.

## Testy

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\report -q
```

Raport wymaga fachowej interpretacji. Jakość obrazu 2D, zasłonięcia i brak danych kontekstowych ograniczają zakres wniosków.
