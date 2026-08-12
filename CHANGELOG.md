# Changelog

## [0.13.0-beta.1] - 2026-08-12

### Added

- Photo Scene Builder v0.2: wielopunktowa kalibracja lokalna, wiele postaci i typowane wymiary obiektów.
- Antropometrycznie ograniczone IK z czytelnym stanem przekroczenia naturalnego zasięgu.
- Sugestie brakujących wymiarów, kompletność sceny i techniczne insights bez scoringu ergonomicznego.

### Changed

- Schemat sceny 1.1 zachowuje automatyczną normalizację istniejących dokumentów 1.0.
- Edytor ma uporządkowany toolbar oraz zakładki Scena, Obiekty, Osoby, Wymiary i Sugestie.

## [0.12.0-beta.1] - 2026-08-12

### Added

- Niezależny Photo Scenario Builder z prywatnym zdjęciem, detekcją YOLOX-X, ręczną kalibracją i edytorem manekina 2D.
- Jawny `analysis_type`, historia dwóch typów analiz oraz osobny Scene Detection Worker w Pipeline Supervisorze.
- Wersjonowany stan sceny, autosave, undo/redo i ręczny fallback po błędzie detekcji.

### Safety

- Analizy `PHOTO_SCENE` nie mogą zostać przejęte przez preprocessing filmu i nie uruchamiają Risk, RULA, REBA ani OWAS.

## [0.11.1-beta.1] - 2026-08-11

- Jasny wariant sceny 3D z neutralnym tłem, grafitowym modelem i pomarańczowymi akcentami analizy.
- Status projektu, roadmapa, wersje i duże karty korzystają z neutralnych powierzchni zamiast dekoracyjnej mięty i cyan.
- Dalsza migracja aktywnych komponentów z klas legacy do semantycznych tokenów design systemu.
- Zachowane kolory success, warning, error i risk oraz istniejący Dark Mode i wydruk.

## [0.11.0-beta.1] - 2026-08-11

- Centralny system tokenów dla jasnego i ciemnego motywu; jasny pozostaje ustawieniem domyślnym.
- Zapamiętywany wybór motywu bez zależności od ustawień systemowych i bez migotania przy starcie strony.
- Ujednolicone powierzchnie, karty, przyciski, pola, focus ring i pomarańczowa identyfikacja marki.
- Odświeżone widoki publiczne, uwierzytelnianie, panel, workspace analizy, wykresy oraz raport do druku.
- Zachowane semantyczne kolory powodzenia, ostrzeżenia i błędu oraz obsługa ograniczonego ruchu.

## [0.9.0-beta.1] - 2026-08-10

- Lokalny Pipeline Supervisor uruchamiany razem z Next.js, z preflightem, heartbeat, blokadą pojedynczej instancji i kontrolowanym restartem.
- Watchdog analizy i lokalny, zabezpieczony endpoint diagnostyczny rozróżniają kolejkę, pracę, stall oraz niedostępny worker.
- Pose Pipeline `pose-v5.1-beta.1` zachowuje źródłową oś czasu, obsługuje wiele aktywnych fragmentów i ograniczony Hand Rescue.
- Report `analysis-report-v2.2-beta.1` rozdziela processing, pose, metric i region coverage oraz zachowuje semantykę braku danych.
- OWAS i EJMS `v1.1-beta.1` raportują wynik częściowy bez udawania wartości końcowej.

## [0.8.0-beta.1] - 2026-08-10

- Forensic audit sześciu arkuszy `testy.xlsx`, 159 unikalnych grafik i źródłowych anomalii.
- Wersjonowane `method-specs` współdzielone przez Python i TypeScript.
- OWAS `owas-company-v1.0-beta.1` oraz EJMS `ejms-company-v1.0-beta.1` z pełnoprawnym `UNKNOWN`.
- Prywatne dane kontekstowe i przeliczanie bez GPU.
- `analysis-report-v2.1-beta.1` z oddzielną sekcją metod zakładowych.

## [0.7.0-beta.1] - 2026-08-10

- Pose Pipeline `pose-v5.0-beta.1` ze schematem 5.0, evidence fusion i walidacją jerk zależną od czasu.
- Świadomość ruchu kamery, drgań i scene cut z resetem pamięci czasowej.
- Ograniczony Pass 2 dla trudnych segmentów, z audytem jakości i fallbackiem do Pass 1.
- Hand/Holding V3 z walidacją łańcuchów palców i dowodami kontaktu/wspólnego ruchu.
- `analysis-report-v2.0-beta.1`: krótsze wnioski, ekspozycja, dowody i deterministyczne zalecenia.

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
