# Report Engine V2

Report Engine jest deterministyczną warstwą prezentacyjną istniejących wyników.
Nie uruchamia ponownie Pose Pipeline, Ergonomics Metrics Engine ani Risk Engine i
nie pobiera filmu.

## Wejście i wyjście

Engine przyjmuje metadane rekordu analizy oraz dwa prywatne dokumenty:

- `ergonomics-metrics.json` w schemacie `1.0`,
- `risk-assessment.json` w schemacie `1.0`.

Weryfikuje wersje i zgodność `analysis_id`, a następnie tworzy
`analysis-report.json` w wersji `analysis-report-v2.1-beta.1`. Raport zawiera metadane
analizy, informacje o przetwarzaniu i jakości danych, podsumowanie ryzyka,
obszary ciała, ograniczoną listę metryk, kluczowe momenty, deterministyczne
obserwacje, ograniczenia oraz jeden disclaimer. Nie powiela danych klatkowych.

Pełny raport trafia do prywatnego bucketa `analysis-results` pod ścieżką:

```text
{user_id}/{analysis_id}/results/analysis-report.json
```

Do tabeli `analyses` zapisywane jest wyłącznie małe `report_summary`, bez serii
klatkowych, punktów pozy i pełnych wyników źródłowych.

## Report Worker

Worker atomowo przejmuje analizę w stanie `ready-for-report`, pobiera wyłącznie
dwa wejściowe pliki JSON, buduje i wysyła raport, a następnie kończy analizę:

```text
ready-for-report -> report-processing -> completed
```

Stan końcowy to `status = completed`, `processing_stage = completed` i
`progress = 100`. Błąd raportu nie usuwa wyników Pose, Ergonomics ani Risk.

Wymagane zmienne środowiskowe:

- `SUPABASE_URL`,
- `SUPABASE_SECRET_KEY`,
- `ANALYSIS_RESULTS_BUCKET`,
- `REPORT_WORKER_ID`,
- `WORKER_POLL_INTERVAL_SECONDS`,
- `WORKER_LOG_LEVEL`,
- `KEEP_WORKER_FILES`.

Tryb jednorazowy z katalogu głównego repozytorium:

```powershell
worker\.venv\Scripts\python.exe worker\src\report_worker.py --once
```

Tryb ciągły:

```powershell
worker\.venv\Scripts\python.exe worker\src\report_worker.py
```

Testy:

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\report -q
```

Ponowienie samego raportu wykonuje chronione RPC `retry_report_analysis` wyłącznie
z kontekstu `service_role`. Zachowuje ono wcześniejsze pliki i przywraca analizę
do `ready-for-report` z postępem 97.

## Ograniczenia

Raport porządkuje dane z analizy 2D i jawnego profilu Risk Engine. Nie jest
diagnozą, certyfikacją ani automatyczną decyzją BHP. Nie zawiera RULA, REBA,
generatywnych rekomendacji ani produkcyjnego profilu progów. Projekt nie tworzy
automatycznego pliku PDF; stronę raportu można wydrukować z przeglądarki.

System wspiera analizę ergonomii i nie zastępuje oceny specjalisty.
