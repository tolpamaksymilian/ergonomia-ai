# Worker changelog

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
