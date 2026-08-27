# Pose Pipeline V6.5 — deep offline analysis and production hardening

Pose V6 extends the existing YOLOX-X, RTMW WholeBody, MediaPipe hand and
biomechanical validation pipeline. It does not change the AI models. Its role
is to preserve the identity and visual continuity of the locked worker during
short detector/keypoint gaps while keeping analytical provenance explicit.

## Quality contract

Each body point is labelled `MEASURED`, `REFINED_MEASUREMENT`, `INTERPOLATED`,
`FLOW_TRACKED`, `KINEMATIC_RECONSTRUCTED`, `KINEMATIC_PREDICTED`, `REJECTED`
or `MISSING`.
`KINEMATIC_PREDICTED` and render `HELD` geometry are visualization-only.
Ergonomic calculations may only consume points whose `analysis_usable` flag is
true. Render coverage is therefore not accuracy and does not increase raw
measurement coverage.

Pose 6.1 additionally fuses the normal and hard-frame RTMW results per joint.
A fallback joint replaces the primary one only when it is materially better
and spatially consistent with body scale. Layer-level timeline states and
coverage KPIs are documented in `TIMELINE_CONTRACT.md`.

Pose 6.2 runs a precision pass after temporal reconstruction. A
`CanonicalBodyProfile` learns median/MAD bone proportions divided by current
body scale from strong model observations only. A dt-aware, velocity-adaptive
state estimator stabilizes the torso first, then constrained two-bone chains.
An isolated elbow or knee can be recovered from the two circle intersections;
the temporally consistent branch is labelled `KINEMATIC_RECONSTRUCTED`, never
`MEASURED`. `SkeletonGeometryValidator` reports bone, jump, side-identity,
crossing, body-region and torso-scale anomalies.

Angle Engine V3 computes provenance/quality for 2D projected angles and only
reconstructs an isolated temporal excursion whose neighbouring samples agree;
a sustained fast turn is retained. It reports robust temporal angle uncertainty
without claiming 3D accuracy. Grip V5 keeps MediaPipe geometry normalized
to the palm, exposes per-finger and thumb features, checks RTMW/MediaPipe wrist
alignment and confirms grip/release transitions with time-based hysteresis.
Confidence, stability and landmark coverage are separate. Object proximity
contributes evidence but does not prove a grip.

Pose 6.3 adds a conservative offline fixed-lag pass before anatomical
projection. It uses two future/previous frames to repair only isolated joint
drift when the bracketing trajectory agrees; sustained fast motion, scene cuts
and hard loss are protected. Hard-frame fusion now ranks every candidate joint
by confidence, temporal continuity, local topology and primary-source
hysteresis rather than raw confidence alone.

Pose 6.4 treats Pass 1 as an initial hypothesis. A whole-track self-audit maps
joint jumps, low confidence, bone instability, angle glitches, hand dropouts,
old predictions and flow disagreement into padded hard segments. Pass 2 runs
RTMW on several person-context ROI scales and fuses all hypotheses per joint.
The worst bounded 1-5% left by its audit can enter a deeper Pass 3. Each stage
must produce a material quality gain; regression is rolled back and convergence
stops further compute. A robust, confidence/source-weighted bidirectional
trajectory optimizer then repairs isolated jerk across each continuous track,
while scene cuts, hard loss, sustained fast motion and strong measurements are
anchors. The final state is the best accepted state, never merely the last one.
After anatomical projection, the final audit may run one more repair only on
the reported hard segment plus configured temporal padding. It never retries a
scene cut, hard-lost/out-of-frame interval or an unobserved image, and it is
bounded to three iterations with convergence and rollback.

Pose 6.5 formalizes final-audit array boundaries. Prediction age is canonical
per joint; only documented `(joint,)` and historical `(joint, 1|2)` layouts are
accepted. The real crash caused by indexing a 1-D vector with a multi-element
tuple is covered by regression tests. `FinalSkeletonContract` validates frame
and joint counts, finite usable/render geometry, score ranges and identity
before artifact writing. A supported optional audit-input mismatch can degrade
only final diagnostics and reuse the last valid audit; invalid geometry still
fails loudly.

The global optimizer V2 couples shoulder–elbow–wrist and hip–knee–ankle chains.
Its objective includes measurement, velocity, acceleration/jerk, bone length
and topology terms with source, motion, occlusion and prediction-age weights.
Critical context is seconds-based and bidirectional; best-state rollback remains
mandatory.

Grip flicker can trigger a local expanded-ROI MediaPipe re-pass. Angle spikes
mark their source shoulder/elbow/wrist or hip/knee/ankle joints for model
reanalysis; the worker does not hide bad geometry by editing only the derived
angle. No secondary expert model is enabled. `expert_backend.py` defines the
required inference and canonical-layout contract and assesses ViTPose-H
WholeBody, DWPose WholeBody and RTMPose-X WholeBody as locally unavailable: the
repository has no configured weights, validated canonical mapping or same-video
benchmark. Nothing is downloaded implicitly and RTMW remains primary.

Hard-frame ROI variants are submitted to the existing CUDA RTMW backend in a
single multi-bbox call per source frame. This keeps the additional compute on
GPU and bounds host memory/VRAM to one hard frame's crop set; it does not retain
an entire segment's image tensors in memory.

The presentation and grip contracts are documented in `OVERLAY_CONTRACT.md`
and `GRIP_CONTRACT.md`. A local KPI comparison can be run with:

```powershell
worker\.venv\Scripts\python.exe -m worker.src.pose_v6.quality_benchmark `
  after-pose-keypoints.json before-pose-keypoints.json
```

The production core can be exercised on a local MP4 without claim, RPC,
Supabase write or upload:

```powershell
worker\.venv\Scripts\python.exe worker\tools\analyze_local_video.py `
  --input C:\path\sample.mp4 --profile ULTRA
```

The default output is `.runtime/pose-benchmark/` and includes overlay,
keypoints, diagnostics and `quality-summary.json`. It makes no accuracy claim.

## Continuity

After lock-on, a short YOLOX miss may trigger RTMW on an FPS-aware predicted
ROI. Offline reconstruction uses bounded velocity-aware Hermite interpolation;
validated pyramidal LK flow can fill remaining short gaps. Missing elbow/knee
geometry can be reconstructed analytically only when both endpoints, canonical
lengths and the geometry validator make it safe; it remains explicitly marked
as reconstructed. Less certain prediction stays render-only. Scene
cuts, identity conflicts, prediction uncertainty and the hard-lost time limit
reset continuity.

## Environment

The defaults target the `ACCURATE` profile. The small optional surface is
documented in `worker/.env.example`: recovery/hard-lost/interpolation/render
times, optical-flow validation, fast-motion threshold, recovery ROI scale and
the bounded V6.5 pass/repair budgets. `POSE_V6_PROFILE=ACCURATE` remains the
default. `ULTRA` increases selective ROI variants, temporal context and solver
iterations without repeatedly processing the whole film. The quality score is
a technical internal data score, not accuracy.
Its analytical coverage counts only measured/refined measurements; render-only
prediction is reported separately. Explicit penalties for joint jumps, bone
instability, side ambiguity, angle outliers and model/wrist disagreement stop
coverage alone from hiding a geometry regression.

## Compute policy and diagnostics

Pass 1 covers the active video once. Pass 2 is capped at 30% hard frames; Pass
3 is capped at the worst unresolved 5%. The expert-resolution candidate budget
is capped at 0–3%, but execution remains disabled until a backend is validated.
Final repair is local to padded error segments, not a fourth whole-video pass.
Convergence and minimum gain skip work early; ACCURATE allows three optimizer
iterations and ULTRA five by default. `pose-keypoints.json` reports
pass/final quality, hard/critical segment counts, improved/unchanged/rolled-back
frames, per-joint selected pass/source/consensus/correction iteration and the
runtime split for Pass 1, Pass 2, Pass 3, expert, global optimization, hands and
render. Errors expose confidence and repairability; low-confidence errors do
not trigger heavy local repair.

## Tests

From the repository root:

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\pose_v6 -q
```

Synthetic tests validate detector gaps, bbox prediction, scene-cut/hard-lost
boundaries, interpolation, optical-flow validation, kinematic reconstruction,
fast motion, persistent per-bone rendering, geometry jumps, angle glitches and
grip hysteresis/occlusion. They do not require GPU models.
