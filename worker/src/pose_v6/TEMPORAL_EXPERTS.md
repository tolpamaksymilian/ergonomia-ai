# Pose V6.7 temporal experts

## Selected models

| Role | Model | Upstream | License | Runtime contract |
|---|---|---|---|---|
| Temporal pose measurement | TAR-ViTPose Base, 17 joints | `zgspose/TARViTPose` revision `42164c2c…` | Apache-2.0 | five real frames, center-frame output, COCO17 core body only |
| Learned point evidence | TAPNext++ TRecViT-B 512 | `google-deepmind/tapnet` revision `c2cbab81…` | Apache-2.0 | forward and backward tracking; never a pose measurement |

The official model repositories and checkpoints are not committed and are not
downloaded by a worker process. Install them explicitly:

```powershell
worker\.venv\Scripts\python.exe -m pip install -r worker\requirements-temporal-experts.txt
worker\.venv\Scripts\python.exe worker\tools\install_temporal_experts.py
```

The installer verifies the pinned source revisions and exact artifact sizes.
The model tree is covered by `.gitignore`.

## Fusion policy

RTMW and TAR are independent image measurements. TAPNext++ is initialized from
strong native RTMW anchors on both sides of a hard-motion segment. The forward
and backward tracks must agree within a body-scale-normalized gate before the
track can support a measurement.

An anchor must be a stable raw measurement with quality at least 0.60, visible
geometry, valid incident bones, a stable identity score and no strong motion
blur. V6.7 searches backward for the last such frame and forward for the first
such frame (12 native frames by default). If either side is unavailable, TAP is
not run for that segment and diagnostics report `NO_VALID_ANCHOR`. A one-way
track is diagnostic only. Forward/backward points must agree within 0.12 of
body scale; the resulting `tap_fb_consensus_score` is recorded explicitly.

Decoded TAR coordinates retain their original value for diagnostics and are
classified as `VALID_IN_FRAME`, `VALID_NEAR_EDGE`, `OUT_OF_FRAME` or
`OUTSIDE_PERSON_CONTEXT`. Invalid spatial classes receive zero measurement
quality and are never clamped to an image border. A later canonical-chain
rejection is recorded as `ANATOMICAL_OUTLIER` and cannot reach the renderer.

1. RTMW + TAR agreement selects a confidence-weighted image consensus.
2. When RTMW and TAR disagree, a valid bidirectional track may select the one
   image measurement that agrees with the trajectory.
3. A tracker-only point is rejected.
4. A single uncorroborated image measurement is accepted only at strong quality
   and receives a conservative quality reduction.
5. A complete shoulder–elbow–wrist or hip–knee–ankle proposal must still pass
   the existing canonical length and reach gate before it replaces RTMW.

Only indexes 5–16 are replaceable. TAR face points 0–4 are retained only within
the local inference observation and do not replace RTMW. No TAR value is mapped
to WholeBody face, hand or six-point foot extensions.

## GPU and failure behavior

TAR and TAP are loaded sequentially to fit the target 8-GB RTX worker. Each
backend records inference time and peak allocated CUDA memory. Missing,
truncated or incompatible artifacts produce an explicit degraded diagnostic;
the existing RTMW V6.6 path then continues unchanged. CUDA OOM is never hidden
as a successful expert pass.

Real smoke test:

```powershell
worker\.venv\Scripts\python.exe worker\tools\smoke_temporal_experts.py
worker\.venv\Scripts\python.exe worker\tools\smoke_temporal_experts.py --video C:\path\sample.mp4
```

Four-way real-video ablation:

```powershell
worker\.venv\Scripts\python.exe worker\tools\analyze_local_video.py `
  --input C:\path\sample.mp4 --output .runtime\pose-v67 `
  --compare-temporal-modes --debug-overlay
```

## Rejected/deferred candidates

- Track-On-R is not a production dependency because its DINOv3 checkpoint
  requires separately granted access. It can be revisited as a challenger.
- SEA-RAFT is BSD-3-Clause but deferred unless point tracking remains an
  evidenced failure after the TAPNext++ benchmark.
- CoTracker3 and Sapiens V1 are excluded from this commercial worker because
  the reviewed assets carry non-commercial restrictions.
- RIFE interpolates pixels and is not a pose measurement or point tracker; it
  is not used as the primary answer to joint identity failures.

These choices do not establish ground-truth accuracy. Quality KPIs and visual
worst-frame bundles are engineering evidence and require review on representative
real recordings.
