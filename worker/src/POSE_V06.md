# Pose Pipeline V6 — High Motion Accuracy i Temporal Continuity

Wersje: worker `0.12.0-beta.1`, Pose `pose-v6.4.0-beta.1`, schema `6.0`.
Wersja aplikacji nie jest zmieniana przez iterację worker-only.

Minor `6.4` dodaje sterowany mapą błędów Pass 2 i Pass 3, wieloskalowy konsensus
per joint, porównanie jakości z rollbackiem i warunkiem zbieżności, ograniczony
repair loop, globalną robust trajectory optimization oraz lokalny re-pass dłoni
po wykryciu grip flicker. Wynik zachowuje najlepszy zaakceptowany stan, a nowe
pola diagnostyczne są addytywne względem schema `6.0`.

Pass 1 obejmuje cały aktywny fragment. Pass 2 ma domyślny limit 30% klatek,
Pass 3 wybiera najwyżej 5% nierozwiązanych klatek, a końcowy repair dotyka
wyłącznie wskazanych segmentów wraz z paddingiem. Scene cut, HARD LOST, brak
obrazu i monotoniczny szybki ruch są twardymi granicami. Minimalny przyrost
jakości, epsilon zbieżności i limit trzech iteracji kontrolują koszt.

Minor `6.3` dodaje fixed-lag offline trajectory refinement, kompozytowy per-joint
trust w hard-frame fusion, stabilność confidence Angle Engine oraz mierzalny,
antykolizyjny overlay. Modele bazowe i schema `6.0` pozostają bez zmian.

Minor `6.2` dodaje precision pass: znormalizowany profil kanoniczny osoby,
root-first state estimator, constrained limb-chain projection, walidator
geometrii, Angle Engine V2 i temporalny Grip V4. Schema `6.0` pozostaje
kompatybilna; nowe pola diagnostyczne są addytywne.

Minor `6.1` dodaje per-joint fusion trudnego przebiegu RTMW oraz kontrakt
`pose-timeline-coverage-v1`. Pełny format stanów i KPI opisuje
`pose_v6/TIMELINE_CONTRACT.md`. Jest to rozszerzenie addytywne schema 6.0.

Patch `6.0.1` utwardza granicę serializacji artefaktów Pose: zatwierdzone
skalary NumPy, tablice, enumy i ścieżki są jawnie normalizowane do typów JSON,
a nieznany typ zatrzymuje zapis z dokładną ścieżką pola. Wartości `NaN`/`Inf`
oznaczające brak pomiaru są zapisywane jako `null`; schema pozostaje `6.0`.

## Architektura

V6 rozszerza, a nie kopiuje pipeline V3–V5. Initial acquisition pozostaje
`YOLOX-X → wybrany person bbox → RTMW WholeBody`. Po stabilnym lock-on krótki
miss YOLOX może użyć przewidywanego bboxa ze stanem center/size i ich
prędkościami. RTMW nadal dostaje wyłącznie ograniczony ROI; nigdy całą klatkę.
Identity gate nadal uwzględnia IoU, środek, skalę i sygnaturę barki–biodra.

Pass 1 zapisuje surowe obserwacje, bbox source, motion state, obrazową jakość i
decyzje trackera. Trudne segmenty mogą przejść bounded Pass 2 na cropie
detektora, predicted cropie lub jednym powiększonym cropie. Scene cut resetuje
tracker, bbox estimator, motion analyzer, flow i renderer.

Po Pass 2 offline Temporal Reconstruction korzysta z obu stron luki. Krótkie
luki otrzymują ograniczoną interpolację Hermite z malejącą jakością. Pozostałe
krótkie luki mogą przejść pyramidal Lucas–Kanade z forward-backward check,
kontrolą bboxa i maksymalnego przemieszczenia. Brakujący środkowy joint
shoulder–elbow–wrist lub hip–knee–ankle może zostać odtworzony z przecięcia
okręgów o stabilnych długościach. W V6.2 bezpieczne rozwiązanie z dwoma
analitycznymi końcami łańcucha może być `analysis_usable`, ale zawsze zachowuje
provenance `KINEMATIC_RECONSTRUCTED`; pozostałe predykcje są render-only.

## Kontrakt jakości

- `MEASURED` i `REFINED_MEASUREMENT`: obserwacje modelu po walidacji.
- `INTERPOLATED`, `FLOW_TRACKED` i `KINEMATIC_RECONSTRUCTED`: jawna
  rekonstrukcja; do ergonomii trafia
  tylko przy `analysis_usable=true`, poprawnej kości i wymaganej jakości.
- `KINEMATIC_PREDICTED`: wsparcie wizualne, nigdy pomiar ergonomiczny.
- `HELD`: motion-aware per-bone fallback renderera, nigdy pomiar.
- `REJECTED` i `MISSING`: brak poprawnej geometrii analitycznej.

Measurement coverage, reconstructed coverage i render coverage są raportowane
oddzielnie. Coverage nie jest accuracy ani confidence względem ground truth.

## Test na prawdziwym filmie

1. Zachowaj kopię aktualnych artefaktów analizy jako BEFORE.
2. Ustaw w `worker/.env` tylko wtedy, gdy chcesz odejść od domyślnych wartości;
   pełna lista V6 jest w `.env.example`.
3. Ponów wyłącznie etap Pose zgodnie z istniejącą procedurą projektu i uruchom
   lokalny Pipeline Manager albo `pose_worker.py --once`.
4. Pobierz `pose-overlay.mp4`, `pose-keypoints.json` i `pose-diagnostics.json`.
5. Porównaj: measurement coverage, analysis usable coverage, render bone
   coverage, single-frame bone/full-skeleton dropout, recovery attempts,
   per-bone source counts, track losses, hand valid ratio i runtime breakdown.
6. Obejrzyj szybki wyprost ręki, pochylenie, obrót tułowia, wejście/wyjście z
   kadru, drugą osobę i każdą granicę sceny. Sprawdź, czy `HELD` podąża za bboxem
   oraz czy po HARD LOST nic nie pozostaje w pustym miejscu.

Repo nie zawiera fixture prawdziwego filmu z ground truth, dlatego nie podajemy
procentowej poprawy accuracy. Syntetyczne testy mierzą ciągłość, provenance i
bezpieczne granice, nie dokładność biomechaniczną na realnym nagraniu.
