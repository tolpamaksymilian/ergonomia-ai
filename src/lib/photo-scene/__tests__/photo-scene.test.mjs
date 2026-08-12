import assert from "node:assert/strict";
import test from "node:test";

import { distance, localPixelsPerCentimeter, solveTwoBoneIk } from "../geometry.ts";
import { emptySceneState, validateSceneState } from "../schema.ts";

test("empty scene is schema-valid", () => assert.equal(validateSceneState(emptySceneState()), true));
test("normalized object coordinates survive viewport changes", () => {
  const point = { x: 0.25, y: 0.75 };
  assert.deepEqual([point.x * 400, point.y * 200], [100, 150]);
  assert.deepEqual([point.x * 1200, point.y * 800], [300, 600]);
});
test("two-bone IK preserves segment lengths for a reachable target", () => {
  const result = solveTwoBoneIk({ x: 0, y: 0 }, { x: 0.3, y: 0.2 }, 0.25, 0.2);
  assert.ok(Math.abs(distance({ x: 0, y: 0 }, result.joint) - 0.25) < 1e-9);
  assert.ok(Math.abs(distance(result.joint, result.end) - 0.2) < 1e-9);
});
test("unreachable IK target straightens but never stretches a limb", () => {
  const result = solveTwoBoneIk({ x: 0, y: 0 }, { x: 2, y: 0 }, 0.3, 0.2);
  assert.ok(Math.abs(distance({ x: 0, y: 0 }, result.end) - 0.5) < 1e-9);
});
test("local scale uses user anchors and no calibration returns null", () => {
  assert.equal(localPixelsPerCentimeter({ status: "UNCALIBRATED", floorBaseline: null, anchors: [] }, { x: .5, y: .5 }, 1000), null);
  const value = localPixelsPerCentimeter({ status: "PARTIALLY_CALIBRATED", floorBaseline: null, anchors: [{ id:"a", lower:{x:.2,y:.8}, upper:{x:.2,y:.5}, pixelDistance:300, realDistanceCm:100, objectId:null, source:"USER_PROVIDED" }] }, { x:.2,y:.6 }, 1000);
  assert.equal(value, 3);
});
test("invalid zero anchor and negative human dimensions are rejected", () => {
  const state = emptySceneState();
  state.calibration.anchors.push({ id:"a", lower:{x:.2,y:.2}, upper:{x:.2,y:.2}, pixelDistance:0, realDistanceCm:-1, objectId:null, source:"USER_PROVIDED" });
  assert.equal(validateSceneState(state), false);
});
