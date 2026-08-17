# Scene Reconstruction Worker V1

CPU-only etap `PHOTO_SCENE`, odseparowany od detekcji obrazu i wszystkich workerów `VIDEO`.

Wejściem jest zapisany stan sceny 1.5 (`regions`, obiekty, płaszczyzny i `constraintGraph`) oraz dowody z Scene Detection. Worker zapisuje prywatne artefakty `scene-reconstruction-input.json` i `scene-reconstruction.json` w buckecie `analysis-scenes`. Wynik może być `SOLVED`, `PARTIAL`, `UNDERDETERMINED` albo `INCONSISTENT`; brak wymiaru nie jest zastępowany typową wartością.

Solver używa ważonej mediany, straty Hubera i izolacji outlierów. `USER_PROVIDED` ma najwyższą wagę, a wartość `rawValue` nigdy nie jest zmieniana. Auto Repair obejmuje wyłącznie geometrię pochodną, np. kolejność punktów samoprzecinającego się wielokąta, i zawsze pozostawia wpis w audycie.

Uruchomienie jednego zadania:

```powershell
worker\.venv\Scripts\python.exe worker\src\scene_reconstruction_worker.py --once
```

Tryb ciągły:

```powershell
worker\.venv\Scripts\python.exe worker\src\scene_reconstruction_worker.py
```

Opcjonalny `SCENE_RECONSTRUCTION_WORKER_ID` rozróżnia ten proces od Scene Detection Workera. Pozostałe zmienne to `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `ANALYSIS_SCENES_BUCKET`, `WORKER_POLL_INTERVAL_SECONDS` i `KEEP_WORKER_FILES`.

Moduł nie używa GPU, modeli AI ani FFmpeg. Nie wykonuje scoringu ergonomicznego.

## Kontrakt i kolejka

W domyślnym Guided Setup jedno polecenie „Rozpoznaj i zbuduj scenę” uruchamia najpierw detekcję z kontekstem użytkownika, a po jej poprawnym zakończeniu atomowo ustawia `reconstruction_status = QUEUED`. Tryb zaawansowany zachowuje osobne polecenia detekcji i rekonstrukcji. Scene Reconstruction Worker przejmuje rekord przez `FOR UPDATE SKIP LOCKED`, ustawia `SOLVING`, raportuje heartbeat i kończy stanem `SOLVED`, `PARTIAL`, `UNDERDETERMINED` albo `INCONSISTENT`.

Worker wykorzystuje znormalizowane punkty obrazu, regiony, powiązania obiektów, jawne wymiary i zapisane dowody Scene Detection. Nie pobiera filmu ani nie uruchamia pipeline’u VIDEO. Brakujące wymiary pozostają `UNKNOWN`; wynik wskazuje jeden `NextBestMeasurement` zamiast podstawiać typową wartość.

## Model geometryczny

- `HEIGHT`, `WIDTH` i `DEPTH` są dopasowywane w osobnych grupach obiektu lub regionu.
- Tylko pionowe `HEIGHT` z segmentem obrazu mogą zasilać Human Scale V3.
- Trzy rozłożone przestrzennie wysokości mogą utworzyć odporny model `INVERSE_AFFINE_VERTICAL`; w pozostałych przypadkach używana jest ważona, odporna stała.
- Quad z dwiema znanymi osiami płaszczyzny otrzymuje rzeczywiście rozwiązaną homografię. Bez tych danych płaszczyzna pozostaje częściowa.
- Intrinsics kamery nie są zgadywane i `solvePnP` nie jest uruchamiane bez wymaganych korespondencji 3D–2D.

## Prywatne artefakty

W prywatnym buckecie `analysis-scenes` powstają:

- `{user_id}/{analysis_id}/results/scene-reconstruction-input.json`,
- `{user_id}/{analysis_id}/results/scene-reconstruction.json`.

Baza przechowuje jedynie metadane kolejki, ścieżki oraz ograniczone podsumowanie rekonstrukcji. Dane źródłowe użytkownika nie są nadpisywane przez Auto Repair.

## Testy

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\scene_reconstruction worker\tests\pipeline\test_scene_reconstruction_migration.py -q
worker\.venv\Scripts\python.exe -m compileall -q worker\src\scene_reconstruction worker\src\scene_reconstruction_worker.py
```
