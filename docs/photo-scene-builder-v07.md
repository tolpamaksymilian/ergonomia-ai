# Photo Scene Builder v0.7 Beta

Photo Scene Builder v0.7 adds a physical, serializable 3D workspace while preserving Photo View and Calibration V3.

## Coordinates and scope

- X is width, Y is height, Z is depth.
- The unit is a centimeter and the default floor is Y=0.
- The engine performs geometric and kinematic checks. It is not a dynamics, biomechanics, RULA, REBA, OWAS, or risk engine.
- Photo projection remains approximate unless the camera mapping is explicitly calibrated.

## Digital Human 3D

The procedural mannequin is generated from the existing anthropometric profile. The physical state contains root transform, joints, pole targets, hand/finger pose and attachments. Rendering state and Three.js objects are never serialized.

## Interactions

The engine provides arm and leg two-bone IK, finger presets, grip geometry, one- and two-hand attachment, reach margin, capsule-to-object collision proxies, held-object collision and sampled A→B motion checks.

Objects without confirmed depth remain plane proxies with collision disabled. A missing solid is reported as `UNKNOWN_GEOMETRY`, never as clear space.

## Compatibility

Schemas 1.0–1.3 normalize to 1.4. A legacy 2D operator is preserved through a migration marker and backup placement; a neutral 3D pose is created when exact migration is not possible.

## Debugging

In development, append `?debugInteraction3d=1` to show joints. Use the HTML side panel for accessible position, grip, reach, collision and motion controls.

## Validation

```powershell
npm.cmd run test:photo-scene
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
git diff --check
```
