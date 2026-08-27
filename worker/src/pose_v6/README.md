# Pose Pipeline V6 — temporal continuity

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

Angle Engine V2 computes provenance/quality for 2D projected angles and only
reconstructs an isolated temporal excursion whose neighbouring samples agree;
a sustained fast turn is retained. Grip V4 keeps MediaPipe geometry normalized
to the palm, exposes per-finger and thumb features, checks RTMW/MediaPipe wrist
alignment and confirms grip/release transitions with time-based hysteresis.
Object proximity contributes evidence but does not prove a grip.

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

Grip flicker can trigger a local expanded-ROI MediaPipe re-pass. Angle spikes
mark their source shoulder/elbow/wrist or hip/knee/ankle joints for model
reanalysis; the worker does not hide bad geometry by editing only the derived
angle. No expert model was enabled: the repository has no reviewed weights,
license record and ground-truth benchmark proving a safe improvement over the
current RTMW primary model.

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
the bounded V6.4 pass/repair budgets. `POSE_V6_PROFILE=ACCURATE` remains the
default. The quality score is a technical internal data score, not accuracy.
Its analytical coverage counts only measured/refined measurements; render-only
prediction is reported separately. Explicit penalties for joint jumps, bone
instability, side ambiguity, angle outliers and model/wrist disagreement stop
coverage alone from hiding a geometry regression.

## Compute policy and diagnostics

Pass 1 covers the active video once. Pass 2 is capped at 30% hard frames; Pass
3 is capped at the worst unresolved 5%. Final repair is local to padded error
segments, not a fourth whole-video pass. Convergence, minimum quality gain and
the three-iteration ceiling can skip work early. `pose-keypoints.json` reports
pass/final quality, hard/critical segment counts, improved/unchanged/rolled-back
frames, per-joint selected pass/source/consensus/correction iteration and the
runtime split for Pass 1, Pass 2, Pass 3, global optimization, hands and render.

## Tests

From the repository root:

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\pose_v6 -q
```

Synthetic tests validate detector gaps, bbox prediction, scene-cut/hard-lost
boundaries, interpolation, optical-flow validation, kinematic reconstruction,
fast motion, persistent per-bone rendering, geometry jumps, angle glitches and
grip hysteresis/occlusion. They do not require GPU models.
