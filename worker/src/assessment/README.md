# Evidence-Aware Ergonomic Assessment Engine

Silnik `assessment-v1.0-beta.1` interpretuje gotowe `pose-keypoints.json` (Pose V4) i `ergonomics-metrics.json`. Nie uruchamia modeli AI, nie wymaga GPU i nie korzysta z Supabase. RULA oraz REBA pozostają osobnymi metodami od istniejącego Risk Engine.

## Provenance i brak danych

Każdy składnik ma źródło `observed`, `derived`, `user_provided`, `assumed` albo `unknown`, jakość, odwołania do dowodów i listę braków. Domyślnie założenia są wyłączone. Brak siły, masy, coupling, skrętu osiowego albo informacji o podparciu pozostaje `unknown`; nie jest zamieniany na zero.

- `COMPLETE` — wszystkie wymagane składniki są rozstrzygnięte, a zakres redukuje się do jednej wartości.
- `PARTIAL` — geometria jest użyteczna, lecz brakuje co najmniej jednego składnika. Prezentowany jest deterministyczny zakres wszystkich możliwych wyników metody.
- `INSUFFICIENT_DATA` — jakość lub pokrycie danych nie pozwala na wiarygodny screening.

Zakres wyniku nie jest przedziałem ufności. To zbiór skrajnych wyników możliwych dla jawnie nierozstrzygniętych kategorii tablicowych.

## Selekcja postaw

Selector wybiera maksymalnie 12 jakościowo poprawnych, rozdzielonych czasowo kandydatów. Ranking łączy odchylenie postawy, czas epizodu, jakość i częstotliwość. Odrzuca `TRACK_LOST`, `REACQUIRING`, `INVALID` oraz klatki bez osoby. Nie uśrednia wyników RULA/REBA po filmie.

## Ograniczenia 2D

Automatycznie dostępne są głównie zgięcia szyi, tułowia, ramion, łokci i nadgarstków. REBA może dodatkowo wyprowadzić zgięcie kolana z punktów biodro–kolano–kostka Pose V4. Skręt, zgięcie boczne, podparcie, balans ciężaru, jakość coupling, obciążenie i siła wymagają osobnych dowodów lub przyszłego jawnego inputu użytkownika. Holding V2 potwierdza jedynie prawdopodobne trzymanie — nie określa masy ani jakości chwytu.

## Uruchomienie

```powershell
worker\.venv\Scripts\python.exe worker\tools\analyze_assessment.py `
  --pose "D:\wynik\pose-keypoints.json" `
  --ergonomics "D:\wynik\ergonomics-metrics.json" `
  --output "D:\wynik\ergonomic-assessment.json"
```

Testy: `worker\.venv\Scripts\python.exe -m pytest worker\tests\assessment -q`.

## Integracja raportu i klatki reprezentatywne

Report Worker uruchamia ocenę po wczytaniu istniejących wyników Pose V4 i Ergonomics Metrics. Błąd tej opcjonalnej warstwy nie unieważnia raportu bazowego. Dokument jest zapisywany pod deterministyczną ścieżką `results/ergonomic-assessment.json`, bez nowych kolumn lub RPC. Gdy dostępny jest film overlay oraz FFmpeg, worker może wyciąć maksymalnie sześć klatek reprezentatywnych do prywatnego Storage; w dokumencie pozostają tylko ścieżki i metadane.

Sterowanie integracją: `ASSESSMENT_ENABLED`, `ASSESSMENT_MAX_CANDIDATES`, `ASSESSMENT_MIN_QUALITY` i `ASSESSMENT_KEYFRAMES_ENABLED`. Wyłączenie integracji nie zmienia istniejącego pipeline'u raportowego.

Metody są screeningiem postawy i nie stanowią diagnozy, certyfikacji ani ostatecznej opinii BHP. Wersja beta wymaga przeglądu specjalisty i formalnej walidacji przed zastosowaniem produkcyjnym.
