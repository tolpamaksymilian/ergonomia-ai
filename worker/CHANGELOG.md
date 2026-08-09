# Worker changelog

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
