# Pose V6.1 timeline coverage contract

`pose-timeline-coverage-v1` is an additive part of Pose schema `6.0`. It does
not change the 133-point raw payload and does not treat render continuity as a
measurement.

Every frame exposes `timeline_v6.layers` for torso, neck, left/right arm,
left/right wrist and left/right hand. A layer has one state:

- `MEASURED` — validated primary model observation;
- `REFINED_MODEL` — validated joint selected from the hard-frame RTMW pass;
- `TEMPORALLY_RECONSTRUCTED` — bounded bidirectional reconstruction;
- `FLOW_TRACKED` — validated forward/backward optical flow;
- `KINEMATICALLY_INFERRED` — geometry usable only by render/timeline;
- `LOW_CONFIDENCE_BUT_USABLE` — persistent visible geometry, never analysis;
- `NOT_VISIBLE` — explicit occlusion/out-of-frame/lost state;
- `NO_DATA` — no defensible geometry.

Usability is independent of the state: `fully_usable`,
`usable_with_reconstruction`, `usable_for_timeline_only` or `insufficient`.
Only the first two can enter Metrics Engine calculations. A one-frame display
gap may be coalesced as `usable_for_timeline_only`; the original state is kept
as `coalesced_from_state` and `analysis_usable` remains false.

`summary.timeline_v6.layers` reports analysis/timeline coverage, measured,
reconstructed and inferred ratios, state counts, single-frame dropout count,
long-gap count and maximum gap. `rula_reba_timeline_coverage_ratio` means only
that required technical geometry is present; it is not a completed RULA/REBA
score, accuracy, confidence or normative result.

The same per-frame provenance is forwarded by Ergonomics Metrics Engine to
metric samples. The web timeline uses it for a separate reconstruction legend;
geometric deviation colors remain non-normative.
