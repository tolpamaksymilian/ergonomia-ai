import assert from "node:assert/strict";
import test from "node:test";

import { createHuman } from "../anthropometry.ts";
import { calibrationQuality, estimateLocalScale } from "../calibration.ts";
import { distance, solveTwoBoneIk } from "../geometry.ts";
import { objectCompleteness } from "../object-dimensions.ts";
import { emptyMeasurements, emptySceneState, normalizeSceneState, validateSceneState } from "../schema.ts";
import { missingDimensionSuggestions, sceneCompleteness } from "../suggestions.ts";

function reference(id, x, y, pixels, cm, type = "HEIGHT") {
  return { id, name: id, dimensionType: type, valueCm: cm, unit: "cm", start: { x, y }, end: { x, y: y - .2 }, pixelDistance: pixels, objectId: null, active: true, visible: true, locked: false, affectsScale: true, source: "USER_PROVIDED" };
}

test("empty schema 1.1 scene is valid", () => assert.equal(validateSceneState(emptySceneState()), true));

test("multipoint calibration uses nearby references and rejects a distant outlier", () => {
  const scene = emptySceneState();
  scene.calibration.references = [reference("near-a", .2, .8, 300, 100), reference("near-b", .3, .7, 315, 100), reference("far-outlier", .95, .15, 900, 100)];
  const scale = estimateLocalScale(scene.calibration, { x: .25, y: .75 }, 1000, 1000);
  assert.ok(scale);
  assert.ok(scale.pixelsPerCm > 2.9 && scale.pixelsPerCm < 3.3);
  assert.ok(scale.referencesUsed.includes("near-a"));
});

test("three consistent references produce good calibration quality", () => {
  const scene = emptySceneState();
  scene.calibration.references = [reference("a", .2, .8, 300, 100), reference("b", .5, .7, 310, 100), reference("c", .8, .6, 290, 100)];
  assert.equal(calibrationQuality(scene.calibration), "GOOD");
});

test("single reference remains partial rather than pretending full calibration", () => {
  const scene = emptySceneState(); scene.calibration.references = [reference("a", .5, .8, 300, 100)];
  assert.equal(calibrationQuality(scene.calibration), "PARTIAL");
});

test("two-bone IK preserves both segment lengths for a reachable target", () => {
  const result = solveTwoBoneIk({ x: 0, y: 0 }, { x: .3, y: .2 }, .25, .2);
  assert.ok(Math.abs(distance({ x: 0, y: 0 }, result.joint) - .25) < 1e-9);
  assert.ok(Math.abs(distance(result.joint, result.end) - .2) < 1e-6);
  assert.equal(result.reachState, "NATURAL");
});

test("unreachable IK target never stretches and reports out of reach", () => {
  const result = solveTwoBoneIk({ x: 0, y: 0 }, { x: 2, y: 0 }, .3, .2);
  assert.ok(Math.abs(distance({ x: 0, y: 0 }, result.end) - .5) < 1e-9);
  assert.equal(result.reachState, "OUT_OF_REACH");
});

test("near-limit target reports comfort exceeded", () => {
  assert.equal(solveTwoBoneIk({ x: 0, y: 0 }, { x: .46, y: 0 }, .3, .2).reachState, "COMFORT_EXCEEDED");
});

test("table suggestions ask for work surface height and geometry", () => {
  const scene = emptySceneState();
  scene.objects.push({ id: "table", sourceClass: "dining table", type: "TABLE", name: "Stół", bbox: { x: .1, y: .3, width: .5, height: .4 }, detectorConfidence: null, source: "YOLOX_X_COCO", status: "USER_CONFIRMED", visible: true, locked: false, measurements: emptyMeasurements(), referencePoint: null });
  const suggestions = missingDimensionSuggestions(scene);
  assert.ok(suggestions.some((item) => item.key === "workSurfaceHeightCm" && item.priority === "CRITICAL"));
  assert.ok(suggestions.some((item) => item.key === "widthCm"));
});

test("object completeness increases only after required dimensions are supplied", () => {
  const measurements = emptyMeasurements();
  assert.equal(objectCompleteness("TABLE", measurements).ratio, 0);
  measurements.workSurfaceHeightCm = 75; measurements.widthCm = 140; measurements.depthCm = 70;
  assert.equal(objectCompleteness("TABLE", measurements).ratio, 1);
});

test("scene completeness does not count optional fields as required", () => {
  const scene = emptySceneState();
  scene.objects.push({ id: "monitor", sourceClass: null, type: "MONITOR", name: "Monitor", bbox: { x: .2, y: .2, width: .2, height: .2 }, detectorConfidence: null, source: "USER", status: "USER_ADDED", visible: true, locked: false, measurements: { ...emptyMeasurements(), screenCenterHeightCm: 120, userDistanceCm: 60 }, referencePoint: null });
  assert.equal(sceneCompleteness(scene).ratio, 1);
});

test("legacy schema 1.0 is normalized to 1.1 without losing object or human", () => {
  const human = createHuman("Operator", "#f97316");
  const legacy = { schema_version: "1.0", objects: [{ id: "table", sourceClass: null, type: "TABLE", name: "Stół", bbox: { x: .1, y: .2, width: .3, height: .3 }, detectorConfidence: null, source: "USER", status: "USER_ADDED", visible: true, measurements: { heightCm: 75, widthCm: null, depthCm: null, workSurfaceHeightCm: null, lowerEdgeHeightCm: null, upperEdgeHeightCm: null }, referencePoint: null }], calibration: { status: "PARTIALLY_CALIBRATED", floorBaseline: null, anchors: [{ id: "old", lower: { x: .2, y: .8 }, upper: { x: .2, y: .5 }, pixelDistance: 300, realDistanceCm: 100, objectId: null, source: "USER_PROVIDED" }] }, human: { ...human.profile, upperLimbLengthCm: 60, lowerLimbLengthCm: 90, geometrySource: "APPROXIMATE_DISPLAY_GEOMETRY" }, pose: { preset: "STANDING", mirrored: false, scaleLocked: true, joints: human.pose.joints }, viewport: { zoom: 1, pan_x: 0, pan_y: 0 } };
  const normalized = normalizeSceneState(legacy);
  assert.equal(normalized.schema_version, "1.1");
  assert.equal(normalized.objects.length, 1); assert.equal(normalized.humans.length, 1); assert.equal(normalized.calibration.references[0].valueCm, 100);
  assert.equal(validateSceneState(normalized), true);
});

test("multiple people retain independent profiles and positions", () => {
  const scene = emptySceneState(), first = createHuman("A", "#f97316", "SHORT"), second = createHuman("B", "#06b6d4", "TALL");
  second.pose.joints.leftHip.x += .2; scene.humans.push(first, second);
  assert.equal(scene.humans.length, 2); assert.notEqual(scene.humans[0].profile.heightCm, scene.humans[1].profile.heightCm); assert.notEqual(scene.humans[0].pose.joints.leftHip.x, scene.humans[1].pose.joints.leftHip.x);
});

test("invalid zero reference and negative human dimensions are rejected", () => {
  const scene = emptySceneState(); scene.calibration.references.push(reference("bad", .2, .2, 0, -1));
  assert.equal(validateSceneState(scene), false);
});
