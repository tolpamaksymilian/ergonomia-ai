# Scene Ergonomics Engine V1

Version: `scene-ergonomics-v1.0-beta.1`  
Builder: `photo-scene-builder-v0.8-beta.1`  
Assessment artifact: `scene-ergonomic-assessment-v1.0`  
Report artifact: `scene-design-report-v1.0-beta.1`

## Scope

The engine is a deterministic design-support layer for `PHOTO_SCENE`. It uses
the physical 3D rig and object geometry in centimeters. Screen-projected SVG
coordinates never enter posture calculations. Geometry, reach, collision,
RULA and REBA remain separate results and are not merged into a 0–100 score.

## Contracts

`buildSceneErgonomicsInput` converts validated Scene Schema 1.4 into the
versioned `scene-ergonomics-input-v1` contract. It records scene revision,
human profiles and joint transforms, object geometry, interaction points,
calibration quality, optional task sequence and explicit manual context.

Every technical measurement has a value or `null`, validity, technical data
quality, provenance, coordinate frame and rejection reason. Missing or invalid
geometry is `UNKNOWN`; it is never converted to zero.

`assessScene` produces a versioned assessment with per-human posture, local
joint angles, work height, sampled reach zones, clearance, line of sight, grip,
side-specific RULA/REBA evidence, task samples, findings, recommendations,
missing data, quality and traceability.

## Anatomical frames

Root yaw is removed before limb angles are measured. Trunk and neck rotations
come from their local rig rotations. Shoulder vectors are transformed into the
torso frame. Elbow and knee flexion use adjacent fixed-length 3D segments.
Consequently rotating the complete operator around world Y does not alter local
posture angles.

## RULA and REBA

The authoritative scoring tables remain in:

- `worker/src/assessment/rula/tables.py`
- `worker/src/assessment/reba/tables.py`

`scripts/export-scene-assessment-tables.py` mechanically exports those tables
for the TypeScript scene adapter. Run it with `--check` to detect a stale
artifact. The scene adapter does not infer force, load, muscle use, coupling,
activity or support. Missing evidence produces a score range and `PARTIAL`.

## Persistence and stale state

The scene remains Schema 1.4. Final assessment and report JSON are recalculated
on the authenticated server from the saved scene and uploaded to the existing
private `analysis-scenes` bucket. `photo_scenes` stores only the private path,
versions, revision/hash, a small summary and completion timestamp. A different
current scene hash marks the loaded assessment as stale.

## Limitations

- Single-photo depth and camera mapping may remain approximate.
- Object clearance uses conservative capsule-to-AABB geometry.
- Reach envelopes sample the implemented joint-space model, not human strength.
- Task motion is kinematic; it is not a dynamics or biomechanics simulation.
- Recommendations are deterministic design suggestions, not compliance claims.
- Specialist review remains required.

## Verification

```powershell
npm.cmd run test:scene-ergonomics
npm.cmd run test:photo-scene
worker\.venv\Scripts\python.exe scripts\export-scene-assessment-tables.py --check
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
git diff --check
```
