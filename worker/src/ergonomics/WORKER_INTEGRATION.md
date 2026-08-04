# Ergonomics Worker V1 — integracja

## Rola procesu

`ergonomics_worker.py` jest osobnym, lekkim etapem CPU. Nie uruchamia YOLOX,
RTMW, MediaPipe, FFmpeg ani Pose Pipeline. Atomowo przejmuje wyłącznie rekordy:

```text
status = queued
processing_stage = ready-for-ergonomics
result_json_path != null
```

Po sukcesie ustawia `processing_stage = ready-for-risk-assessment`. Nie ustawia
`status = completed` ani `progress = 100`, ponieważ Risk Engine i raport nie są
jeszcze wdrożone.

## Pliki

Worker pobiera tylko prywatny `pose-keypoints.json` wskazany przez
`result_json_path`. Nie pobiera filmu źródłowego, filmu wynikowego ani miniatury.

Wynik `ergonomics-metrics.json` jest przesyłany z `upsert` i typem
`application/json` do:

```text
{user_id}/{analysis_id}/results/ergonomics-metrics.json
```

Pełne dane klatkowe pozostają w prywatnym bucketcie `analysis-results`. Tabela
`analyses` otrzymuje wyłącznie metadane oraz ograniczone podsumowanie 14 metryk.

## Konfiguracja

Worker czyta `worker/.env` i korzysta z:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `ANALYSIS_RESULTS_BUCKET`
- `ERGONOMICS_WORKER_ID` — opcjonalny; fallback jest różny od Pose Workera
- `WORKER_ID` — służy tylko do zbudowania fallbacku identyfikatora
- `WORKER_POLL_INTERVAL_SECONDS`
- `KEEP_WORKER_FILES`

Nie należy wpisywać sekretów do repozytorium. Przykładowe wartości znajdują się
w `worker/.env.example`. Obecna migracja i polityki Storage wymagają wartości
`ANALYSIS_RESULTS_BUCKET=analysis-results`.

## Migracja

Repozytorium przechowuje migracje w `src/lib/supabase/migrations`. Dla połączonej
bazy można zastosować migrację przez `psql`, używając connection stringa ustawionego
lokalnie poza repozytorium:

```powershell
psql "$env:SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "src\lib\supabase\migrations\20260804213000_integrate_ergonomics_metrics_worker.sql"
```

Alternatywnie zawartość pliku można wykonać w Supabase SQL Editor. Migracja jest
bezpieczna dla istniejących rekordów i nie dodaje `NOT NULL` do nowych metadanych.

## Uruchomienie

Jedna analiza lub sprawdzenie pustej kolejki:

```powershell
worker\.venv\Scripts\python.exe worker\src\ergonomics_worker.py --once
```

Tryb ciągły:

```powershell
worker\.venv\Scripts\python.exe worker\src\ergonomics_worker.py
```

Log rotacyjny jest zapisywany do `worker/logs/ergonomics-worker.log`. Lokalne pliki
zadania trafiają do `worker/data/ergonomics-jobs/{analysis_id}` i są usuwane po
zakończeniu, chyba że `KEEP_WORKER_FILES=true`.

## Ponowienie tylko ergonomii

Funkcja `retry_ergonomics_analysis` zachowuje wyniki Pose V3.0 oraz
`result_json_path`, czyści tylko metadane i błędy ergonomiczne, a następnie ustawia
`ready-for-ergonomics`:

```sql
select public.retry_ergonomics_analysis('ANALYSIS_UUID'::uuid);
```

Przykład przez `psql`:

```powershell
psql "$env:SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -c "select public.retry_ergonomics_analysis('ANALYSIS_UUID'::uuid);"
```

Funkcja przyjmuje tylko rekord w `ergonomics-failed` albo
`ready-for-risk-assessment`. Nie cofa analizy do `ready-for-ai` i nie usuwa pliku
pozy. Istniejący obiekt metryk zostanie bezpiecznie zastąpiony przy kolejnym upsert.

## Pokrycie poprawnymi danymi

`ergonomics_valid_metric_ratio` to:

```text
liczba poprawnych wartości / (14 metryk × liczba klatek)
```

Jest to techniczny wskaźnik kompletności danych, nie dokładność, confidence ani
skuteczność AI. Dokument bez klatek kończy etap błędem.

## Ograniczenia

- metryki bazują na geometrii 2D i jakości zatwierdzonych punktów Pose V3.0,
- brakujące wartości nie są interpolowane przez worker integracyjny,
- błąd ergonomii nie usuwa filmu, miniatury ani danych pozy,
- Risk Engine, RULA, REBA, wykresy i raport PDF nie są częścią tego etapu.
