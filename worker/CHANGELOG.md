# Worker changelog

## 0.13.0-beta.1

- Pose `pose-v6.5.0-beta.1` fixes the real-video final-audit crash caused by
  NumPy tuple indexing of the 1-D per-joint prediction-age vector.
- Explicit audit array contracts, a strict final-skeleton contract and a
  degraded optional-audit fallback prevent diagnostics from discarding valid
  output without allowing invalid geometry to be serialized.
- Added the opt-in `ULTRA` compute profile, seconds-based bidirectional context,
  joint-chain-aware robust optimization and best-state rollback diagnostics.
- Angle Engine V3 exposes technical uncertainty; Grip V5 exposes state
  confidence, stability and landmark coverage independently per hand.
- Added an expert-backend contract and honest local readiness assessment. No
  unbenchmarked secondary model or weights are enabled in production.
- The local real-video runner uses production core without queue/Supabase and
  writes `quality-summary.json`. Schema remains additively compatible at `6.0`.

## 0.12.0-beta.1

- Pose `pose-v6.4.0-beta.1`: whole-track self-audit, padded hard segments,
  multi-scale per-joint consensus and a bounded critical Pass 3.
- Every iterative state is quality-compared; regression rolls back, convergence
  stops compute, and the final document records the best accepted state.
- Added robust confidence/source-weighted global trajectory optimization and a
  local expanded-ROI hand re-pass for single-frame grip flicker.
- YOLOX-X, RTMW WholeBody, MediaPipe weights and additive schema `6.0` remain
  unchanged; no accuracy claim or unbenchmarked expert model was introduced.

## 0.11.0-beta.1

- Pose `pose-v6.3.0-beta.1`: conservative fixed-lag trajectory correction,
  temporal/topological joint trust and explicit hard-frame fusion decisions.
- Angle confidence includes temporal stability; Grip V4 exposes alignment and
  flicker diagnostics; the premium overlay reports collision/visibility KPIs.
- YOLOX-X, RTMW WholeBody and pose schema `6.0` remain unchanged.

## 0.10.0-beta.1

- Pose `pose-v6.2.0-beta.1`: canonical proportions normalized by body scale,
  dt-aware joint state, anatomical chain projection and geometry validation.
- Angle Engine V2 and temporal Grip V4 remain additive to pose schema `6.0`.

## 0.9.0-beta.1

- Pose `pose-v6.1.0-beta.1` scala wyniki primary/hard-frame RTMW per joint z bramką jakości i przestrzennej zgodności.
- Kontrakt `pose-timeline-coverage-v1` raportuje osiem jawnych stanów i cztery poziomy użyteczności osobno dla analizy oraz render/timeline.
- Dodano per-layer coverage, source ratios, single-frame dropout, long gaps i techniczną dostępność geometrii RULA/REBA.
- Bezpieczna rekonstrukcja po walidacji kości używa jawnego floor jakości 0.35; render-only nadal nie jest pomiarem.
- Krótka luka timeline może zostać scalona wyłącznie wizualnie, bez ustawiania `analysis_usable`.

## 0.8.1-beta.1

- Pose `pose-v6.0.1-beta.1` naprawia końcowy zapis `pose-keypoints.json` i `pose-diagnostics.json`: normalizuje typy NumPy, blokuje niestandardowe `NaN`/`Infinity` i raportuje dokładną ścieżkę nieobsługiwanego pola.
- Pipeline Supervisor `pipeline-supervisor-v1.1-beta.1` traktuje przejściowy `WinError 5` podczas zapisu heartbeat jako awarię diagnostyki, a nie błąd wykonania pipeline’u.
- Atomowy zapis runtime używa unikalnego pliku tymczasowego, `flush`, `fsync`, ograniczonych ponowień z jitterem i bezpiecznego cleanupu bez kasowania ostatniego poprawnego health JSON.
- Lock supervisora wiąże PID z UUID instancji i katalogiem repozytorium, obsługuje stale lock i nie pozwala drugiej instancji uruchomić duplikatów workerów.
- Dev Supervisor ma kontrolowany restart z backoffem, a watchdog rozróżnia `HEALTH_PERSISTENCE_DEGRADED` od rzeczywistego `OFFLINE`.
- Łagodne żądanie stopu pozwala Pipeline Managerowi posprzątać procesy potomne także na Windows.
- Pose Pipeline działa w wersji `pose-v6.0.1-beta.1`; schema pozostaje 6.0.

## 0.8.0-beta.1

- Pose `pose-v6.0-beta.1`, schema 6.0: przewidywany bbox, track-conditioned RTMW, motion modes i natychmiastowe bezpieczne podparcie krótkich missów detektora.
- Offline reconstruction rozdziela `MEASURED`, `REFINED_MEASUREMENT`, `INTERPOLATED`, `FLOW_TRACKED`, `KINEMATIC_PREDICTED`, `REJECTED` i `MISSING`.
- Per-bone persistent renderer korzysta z ruchu i skali bboxa; scene cut i HARD LOST są twardymi granicami.
- Ergonomics zachowuje data honesty: render-only nie jest wejściem do metryk.
- Dodano syntetyczne testy dropoutów, szybkiego ruchu, optical flow, identity oraz ciągłości renderu bez GPU.

## 0.7.0-beta.1

- Pipeline Supervisor `pipeline-supervisor-v1.0-beta.1` z preflightem, heartbeat, blokadą pojedynczej instancji i ochroną przed crash loop.
- Pose `pose-v5.1-beta.1`, schema 5.1: wiele aktywnych fragmentów, źródłowe znaczniki czasu, jawne coverage i ograniczony Hand Rescue.
- Report `analysis-report-v2.2-beta.1` z poprawioną semantyką braków danych, deduplikacją kluczowych momentów i spójnymi ograniczeniami.
- Company Methods `v1.1-beta.1`: OWAS zachowuje rozpoznaną posturę bez masy, a EJMS pokazuje known score i możliwy zakres.

## 0.6.0-beta.1

- Company Methods Engine `company-methods-v1.0-beta.1` oparty na wersjonowanych specyfikacjach JSON.
- Automatyczne cechy wideo dla OWAS/EJMS bez estymowania kg, N, cm lub metrów.
- Report Worker zapisuje prywatny `company-method-assessment.json` i Report V2.1.

## 0.5.0-beta.1

- Pose V5 schema 5.0 z evidence fusion, dt-aware jerk i global camera-motion signal.
- Ograniczony Pass 2 z bramką biomechaniczną oraz audytem before/after.
- Hand Shape/assignment i Holding V3 bez automatycznego uznawania pięści za chwyt.
- Report V2 z rankingiem, deduplikacją, ekspozycją i bezpiecznymi zaleceniami.

## 0.4.0-beta.1

### Improved

- global biomechanical validation and person-specific body scale
- independent limb tracking, occlusion reasoning and confirmed reacquisition
- hand assignment, palm/finger stability and adaptive ROI
- overlay continuity and metric robustness without carrying missing measurements

### Added

- Pose Graph and limb state machines
- optional relative-depth soft reasoning
- Holding V2 with hysteresis, release, episode merge and bimanual evidence
- lightweight object motion association
- non-normative color-coded geometric overlay and angle labels
- render transitions with a hard long-line safety guard
- hierarchical Quality V2 diagnostics and warning codes
- local validation summary, optional QA frames and diagnostics comparison tool

### Limitations

- no force, object weight or muscle-load estimation
- no normative risk claim in overlay colors
- 2D occlusion reasoning remains heuristic and requires real-video QA

## 0.3.0-beta.1

### Improved

- person tracking and confirmed reacquisition
- out-of-frame stability and partial-body handling
- per-joint and per-bone skeleton validation
- forward/backward temporal smoothing
- hand and finger validation
- stable left/right hand association

### Added

- hand-object interaction using cached YOLOX detections
- deterministic grip states
- holding episodes and duration for left, right and bimanual interaction
- frame, segment and video quality diagnostics
- ergonomics dependency graph and temporal features
- compact `pose-diagnostics.json`
- local validation tool without Supabase

### Limitations

- no force estimation
- no object weight estimation
- unknown industrial objects may remain unclassified
- holding detection is probabilistic and requires specialist interpretation
