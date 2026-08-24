# Pose Pipeline V6 — temporal continuity

Pose V6 extends the existing YOLOX-X, RTMW WholeBody, MediaPipe hand and
biomechanical validation pipeline. It does not change the AI models. Its role
is to preserve the identity and visual continuity of the locked worker during
short detector/keypoint gaps while keeping analytical provenance explicit.

## Quality contract

Each body point is labelled `MEASURED`, `REFINED_MEASUREMENT`, `INTERPOLATED`,
`FLOW_TRACKED`, `KINEMATIC_PREDICTED`, `REJECTED` or `MISSING`.
`KINEMATIC_PREDICTED` and render `HELD` geometry are visualization-only.
Ergonomic calculations may only consume points whose `analysis_usable` flag is
true. Render coverage is therefore not accuracy and does not increase raw
measurement coverage.

Pose 6.1 additionally fuses the normal and hard-frame RTMW results per joint.
A fallback joint replaces the primary one only when it is materially better
and spatially consistent with body scale. Layer-level timeline states and
coverage KPIs are documented in `TIMELINE_CONTRACT.md`.

## Continuity

After lock-on, a short YOLOX miss may trigger RTMW on an FPS-aware predicted
ROI. Offline reconstruction uses bounded velocity-aware Hermite interpolation;
validated pyramidal LK flow can fill remaining short gaps. Missing elbow/knee
geometry can be reconstructed for rendering with stable bone lengths. Scene
cuts, identity conflicts, prediction uncertainty and the hard-lost time limit
reset continuity.

## Environment

The defaults target the `ACCURATE` profile. The small optional surface is
documented in `worker/.env.example`: recovery/hard-lost/interpolation/render
times, optical-flow validation, fast-motion threshold and recovery ROI scale.

## Tests

From the repository root:

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\pose_v6 -q
```

Synthetic tests validate detector gaps, bbox prediction, scene-cut/hard-lost
boundaries, interpolation, optical-flow validation, kinematic reconstruction,
fast motion and persistent per-bone rendering. They do not require GPU models.
