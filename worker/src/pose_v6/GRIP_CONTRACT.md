# Grip V5 contract

Grip V5 classifies validated MediaPipe hand geometry into `OPEN`, `RELAXED`,
`PARTIALLY_CLOSED`, `POWER_GRIP`, `PRECISION_PINCH`, `CLOSED` or `UNKNOWN`.
Classification uses palm-normalized closure, aperture, finger flexion, thumb
opposition and thumb-to-finger distance. Object proximity is supporting
evidence only and does not prove a grip.

State changes require elapsed-time confirmation. A bounded short occlusion
retains the previous state with decaying confidence; longer or low-quality
gaps become `UNKNOWN`, never `OPEN`. The summary reports state transitions,
single-frame flicker and a temporal stability score alongside coverage.

RTMW and MediaPipe wrists are fused only for visualization when both sources
are valid and their palm-normalized distance is at most 0.65. The output keeps
the alignment weight and translation explicit. Rejected assignments do not
move the hand. Grip V5 additionally reports state confidence, temporal
stability and usable landmark coverage as separate technical signals. It does
not estimate force, mass or normative ergonomic
risk.
