# Pipeline Manager v0.7.0-beta.1

`pipeline_manager.py` uruchamia istniejące workery jako oddzielne procesy. Nie importuje modeli GPU i nie kopiuje logiki etapów.

Kolejność cyklu:

`preprocessing → Pose V3.0 → ergonomics → risk → report`

## Uruchomienie

```powershell
worker\.venv\Scripts\python.exe worker\src\pipeline_manager.py --check
worker\.venv\Scripts\python.exe worker\src\pipeline_manager.py --once
worker\.venv\Scripts\python.exe worker\src\pipeline_manager.py
```

Wybrany podzbiór bez automatycznego restartu:

```powershell
worker\.venv\Scripts\python.exe worker\src\pipeline_manager.py --workers ergonomics,risk,report --no-restart
```

W trybie ciągłym każdy etap ma dokładnie jeden proces. Po nieoczekiwanym zakończeniu manager stosuje ograniczony liniowy backoff. `Ctrl+C` najpierw kończy procesy potomne, a po przekroczeniu limitu oczekiwania wymusza zamknięcie.

## Preflight bazy

Migracje muszą być wdrożone chronologicznie z `supabase/migrations`, a na końcu:

1. `20260806120000_integrate_risk_worker_v1.sql`,
2. `20260806203000_integrate_report_worker_v1.sql`,
3. `20260806210500_finalize_pipeline_v021.sql`.

Read-only check:

```powershell
worker\.venv\Scripts\python.exe worker\src\check_database_readiness.py
```

Skrypt wypisuje tylko flagi gotowości i nazwy brakujących elementów. Nie wypisuje URL, kluczy ani danych analiz.

## Ręczny test jednego nowego filmu

1. Uruchom `scripts/start-test-environment.ps1`.
2. Zaloguj się i prześlij nowy film bez dodawania go do Git.
3. Pozostaw stronę szczegółów otwartą.
4. Potwierdź przejścia: kolejka, preprocessing, Pose, ergonomics, risk, report, `completed`.
5. Potwierdź monotoniczny postęp: 0–5, 5–20, 20–75, 75–90, 90–97, 97–100.
6. Sprawdź film wynikowy, kartę metryk, ocenę techniczną i raport.
7. Sprawdź pobranie JSON oraz drukowanie raportu.
8. Dla kontrolowanego błędu potwierdź, że administrator może ponowić tylko bieżący etap, a wcześniejsze wyniki pozostają dostępne.

Zapytanie kontrolne (uruchamiane ręcznie wyłącznie we właściwym środowisku testowym):

```sql
select
  id, title, status, progress, processing_stage,
  ergonomics_metrics_path, risk_assessment_path, risk_overall_level,
  report_path, report_version, report_completed_at,
  error_code, error_message,
  ergonomics_error_code, ergonomics_error_message,
  risk_error_code, risk_error_message,
  report_error_code, report_error_message
from public.analyses
order by created_at desc
limit 1;
```

Pełny test wymaga lokalnego Supabase, prywatnych bucketów, FFmpeg, modeli Pose oraz — dla Pose — skonfigurowanego środowiska GPU/CPU. Testy jednostkowe managera nie uruchamiają żadnego z tych zasobów.
