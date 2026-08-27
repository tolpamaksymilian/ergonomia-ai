# Pose V6 overlay contract

The standard overlay is a readable presentation layer, not an additional
measurement source. Bones use the persistent V6 render skeleton, while labels
use valid Angle Engine values calculated from the analysis skeleton.

- Main bone width scales from 3 to 10 px with video height and has a dark
  outline. Joint markers scale from 3 to 11 px.
- Labels show named 2D projected angles in degrees. A percentage is not shown:
  there is no validated, universal mapping from an anatomical angle to a
  percentage of flexion, and inventing one would imply unsupported accuracy.
- Labels use opaque-enough dark bubbles, a colored border and text outline.
  The deterministic layout places trunk and neck first, tries six positions,
  respects frame margins and suppresses a label if no collision-free position
  exists.
- `overlay_label_overlap_count` counts suppressed labels,
  `overlay_main_metric_visibility_ratio` is the placed/requested ratio and
  `overlay_label_readability_score` penalizes both suppression and overlap.
  These are layout KPIs, not pose accuracy metrics.
- The standard mode contains the skeleton, angle labels and confirmed active
  grip badges. Debug mode additionally exposes tracking, provenance and source
  diagnostics.

Hand landmark geometry may be translated toward the RTMW wrist only when the
Grip V5 alignment gate accepts the assignment. It is never relabeled as a body
measurement.
