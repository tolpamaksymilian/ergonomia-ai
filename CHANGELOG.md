# Changelog

## [0.24.0-beta.1] - 2026-08-24

- Pose `pose-v6.1.0-beta.1` dodaje per-joint fusion podstawowego i trudnego przebiegu RTMW bez wymiany poprawnych stawów całej klatki.
- Dodano jawny kontrakt timeline `pose-timeline-coverage-v1`, rozdzielający pomiar, bezpieczną rekonstrukcję, wsparcie wyłącznie wizualne, niewidoczność i brak danych.
- Metrics Engine respektuje zatwierdzoną biomechanicznie rekonstrukcję przy osobnym konserwatywnym floor jakości; predykcja kinematyczna i render hold nadal nie trafiają do obliczeń.
- Timeline pokazuje pochodzenie rekonstrukcji i ciągłość techniczną oddzielnie od geometrycznych pasm odchylenia.
- Dodano KPI analitycznego i wizualnego pokrycia tułowia, szyi, ramion, nadgarstków i dłoni oraz diagnostykę długości luk.

## [0.23.0-beta.1] - 2026-08-24

- Pose `pose-v6.0.1-beta.1` utwardza serializację wyników NumPy/OpenCV do ścisłego JSON bez zmiany schema 6.0.
- Utwardzono lokalny runtime na Windows: przejściowa blokada `worker-health.json` nie zatrzymuje już supervisora, Pipeline Managera ani aktywnej analizy.
- Atomowy heartbeat korzysta z unikalnego temp, `flush`, `fsync`, ograniczonego backoffu z jitterem i zachowuje ostatni poprawny dokument przy wyczerpaniu retry.
- Dodano jawny stan `HEALTH_PERSISTENCE_DEGRADED`, liczniki awarii i recovery log, a frontend toleruje krótkie błędy odczytu bez fałszywego `OFFLINE`.
- Wzmocniono blokadę pojedynczej instancji przez PID, UUID i katalog repozytorium oraz usunięto race restartu pomiędzy Node i Python Supervisor.
- Pipeline Manager wykonuje kontrolowany cleanup procesów potomnych przed wymuszonym zakończeniem na Windows.
- Pose Pipeline używa wersji `pose-v6.0.1-beta.1` i niezmienionej schema 6.0.

## [0.22.0-beta.1] - 2026-08-21

- Pose Pipeline `pose-v6.0-beta.1` dodaje track-conditioned RTMW recovery po krótkim miss YOLOX oraz FPS-aware granice recovery, rekonstrukcji i HARD LOST.
- Offline pass rozdziela pomiary, bezpieczną rekonstrukcję i dane render-only; interpolacja Hermite, walidowany optical flow i predykcja kinematyczna mają jawne źródła.
- Persistent Bone Renderer usuwa pojedyncze mignięcia i przesuwa fallback razem z przewidywanym bboxem zamiast zamrażać szkielet.
- Ergonomics Metrics Engine obsługuje schema 6.0 i nigdy nie traktuje kinematycznej predykcji ani render hold jako pomiaru.
- Dodano diagnostykę motion episodes, per-bone coverage, źródeł renderu, dropoutów i czasu track-conditioned recovery.
- Zachowano modele YOLOX-X/RTMW/MediaPipe, prywatny Storage, RPC, downstream Risk/Report oraz niezależną ścieżkę PHOTO_SCENE.

## [0.21.0-beta.1] - 2026-08-16

- Przebudowano domyślne PHOTO_SCENE jako dziewięcioetapowy Guided Scene Setup: zdjęcie → podłoga i pole pracy → wysokości → opcjonalne wymiary → obiekty → Worker → weryfikacja → operator → ergonomia.
- Nowe zdjęcie nie uruchamia już automatycznie Workera. Jedno CTA „Rozpoznaj i zbuduj scenę” przekazuje kontekst użytkownika do detekcji i kolejkuje istniejącą rekonstrukcję.
- Dodano walidację minimum dwóch pionowych wysokości, poradę o ich przestrzennym rozłożeniu, polygonowe oznaczanie obiektów oraz jawne kojarzenie wcześniejszych wymiarów z obiektami.
- Scene Detection v0.3 wykorzystuje ręczne adnotacje, filtruje nakładające się kandydaty i nigdy nie zastępuje danych `USER_PROVIDED`.
- Zachowano Scene Schema 1.5, istniejący robust solver, Digital Human 3D, Scene Ergonomics oraz pełną ścieżkę VIDEO.

## [0.20.0-beta.1] - 2026-08-16

- Dodano Scene Schema 1.5 z regionami, płaszczyznami, ścianami obiektów i Constraint Graph.
- Dodano odporny Scene Geometry V2 z residuals, outlierami, konfliktami i jawnym Auto Repair pochodnej geometrii.
- Dodano osobny CPU Scene Reconstruction Worker oraz prywatny artefakt `scene-reconstruction.json`.
- Rozdzielono analizę zdjęcia od polecenia „Oblicz geometrię sceny” i dodano gotowość według celu oraz Next Best Measurement.
- Human Scale korzysta najpierw z rekonstrukcji pionowej, a stare sceny 1.0–1.4 zachowują jawny fallback Calibration V3.

## [0.19.0-beta.1] - 2026-08-14

- Dodano odseparowany Scene Ergonomics Engine oparty wyłącznie na fizycznym rig 3D.
- Dodano kąty lokalne, analizę wysokości pracy, work zones, clearance, line-of-sight i grip assessment.
- Dodano evidence-aware adaptery RULA/REBA korzystające z generowanego kontraktu istniejących tabel Python.
- Dodano sekwencje zadań, próbkowanie ruchu, findings, rekomendacje oraz porównanie wariantu projektu.
- Dodano zakładkę Ergonomia oraz prywatne artefakty assessment/report bez zmiany Scene Schema 1.4.

## [0.18.0-beta.1] - 2026-08-14

- Dodano serializowalny świat 3D w centymetrach oraz proceduralny Digital Human 3D.
- Dodano rig dłoni i palców, presety chwytu, IK 3D i pole targets.
- Dodano geometryczne zasięgi, kolizje, relacje chwytu i kinematyczny test ruchu A→B.
- Dodano widoki Zdjęcie / 3D / Podzielony bez zmiany pipeline’u VIDEO.
- Scene Schema 1.4 zachowuje i migruje starszy stan człowieka 2D.

## [0.17.0-beta.1] - 2026-08-14

### Scene World Model / Calibration V3

- Rozdzielono pionową skalę człowieka od szerokości, głębokości i informacyjnych wymiarów obiektów.
- Dodano Measurement Semantics V2: kind, axis, plane, purpose, jawne `useForCalibration` i status przeglądu.
- Human Projection V4 korzysta wyłącznie z wyniku Scene World Model, a nie z surowej listy pomiarów.
- Usunięto ciche zaciskanie absurdalnej skali; niepoprawna projekcja jest teraz jawnie odrzucana.
- Dodano lokalną mapę pokrycia kalibracji, world anchors, model podłogi basic/quadrilateral i kierunek pionowy obrazu.
- Dodano Guided Calibration, instrukcje height/width/depth oraz przegląd semantyki starszych pomiarów.
- Dodano regresję 190 cm / 80 cm / 50 cm potwierdzającą izolację osi i brak skoku skali człowieka.

## [0.16.0-beta.1] - 2026-08-13

### Added

- Digital Human v1 z kanonicznym modelem fizycznym w centymetrach, osobną pozą, projekcją sceny i profesjonalnym rendererem SVG.
- Profile 160/175/190 cm, stałe segmenty, ciągły yaw 0–360°, jawne pochodzenie wymiarów i tryb `?debugHuman=1`.
- Bezpieczny self-test Scene Workera na rzeczywistym YOLOX-X/ONNX Runtime bez modyfikowania kolejki.

### Fixed

- Bucket `analysis-scenes` dopuszcza prywatne wyniki `application/json`; wcześniej poprawna detekcja kończyła się błędem 415 przy uploadzie.
- Scene Worker zapisuje stabilne kody etapów, wykonuje najwyżej jedno ponowienie błędu przejściowego i rozróżnia `SUCCESS_NO_OBJECTS`.

## [0.15.0-beta.1] - 2026-08-12

### Added

- Coordinate Engine V2 z jednym odwracalnym mapowaniem screen ↔ viewport ↔ displayed image ↔ normalized image ↔ intrinsic pixels.
- Jawna kontrola „Analizuj zdjęcie”, stany kolejki/Workera, bezpieczna ponowna analiza oraz panel wyników Scene Detection.
- Tryb diagnostyczny `?debugSceneCoordinates=1` i testy regresyjne dla formatów pionowych, ultrawide, zoomu, panowania i resize.

### Changed

- Kalibracja wymaga przestrzennego rozłożenia referencji, aby uzyskać status „Dobra”.
- Overlay obrazu, obiektów, pomiarów i postaci korzysta z jednej transformacji SVG bez niezależnego CSS scale/translate.

## [0.14.0-beta.1] - 2026-08-12

### Added

- Perspective-aware Human Model V2 z profilem antropometrycznym, stałymi długościami segmentów, stabilnym two-bone IK i jawnymi punktami kontaktu stóp.
- Geometria wymiarów z provenance, warstwy widoku, automatyczne rozmieszczanie etykiet i asystent kalibracji.
- Lekki geometry pass Scene Workera v0.2 wykorzystujący OpenCV do propozycji krawędzi, powierzchni i wymiarów bez zgadywania wartości w centymetrach.

### Changed

- Schemat sceny 1.2 normalizuje dokumenty 1.0 i 1.1 oraz zapisuje pole skali perspektywicznej, relacje człowiek–obiekt i sugestie geometrii.
- Domyślny widok edytora ogranicza nakładanie pomiarów, uchwytów i zasięgów na zdjęcie.

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
