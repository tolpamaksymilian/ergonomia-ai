import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildAnthropometricPose, createConstraintGraph, createHuman, profileFromHeight, profileWithArmSpan, renderedHeightPixels } from "../anthropometry.ts";
import { calibrationAssistant, calibrationQuality, calibrationSpatialCoverage, estimateLocalScale, rebuildPerspectiveField } from "../calibration.ts";
import { distance, moveHumanJointWithConstraints, segmentLengthPixels, solveTwoBoneIk } from "../geometry.ts";
import { layoutMeasurementLabels } from "../label-layout.ts";
import { dimensionsFor, objectCompleteness } from "../object-dimensions.ts";
import { emptyMeasurements, emptySceneState, normalizeSceneState, validateSceneState } from "../schema.ts";
import { missingDimensionSuggestions, nextBestAction, sceneCompleteness } from "../suggestions.ts";

const WIDTH = 1200;
const HEIGHT = 900;

function reference(id, x, y, pixels, cm, type = "HEIGHT") {
  return { id, name: id, dimensionType: type, valueCm: cm, unit: "cm", start: { x, y }, end: { x, y: y - .2 }, pixelDistance: pixels, objectId: null, active: true, visible: true, locked: false, measurementKind: "VERTICAL_HEIGHT", axis: "VERTICAL", plane: "VERTICAL_PLANE", purpose: "CALIBRATION", useForCalibration: true, semanticStatus: "CONFIRMED", worldAnchors: { bottom: { id: `${id}-bottom`, imagePoint: { x, y }, worldHeightCm: 0, role: "BOTTOM" }, top: { id: `${id}-top`, imagePoint: { x, y: y - .2 }, worldHeightCm: cm, role: "TOP" } }, source: "USER_PROVIDED", residual: null, residualStatus: "UNASSESSED", manualOverride: false };
}

function sceneObject(id = "table", type = "TABLE") {
  return { id, sourceClass: type === "TABLE" ? "dining table" : null, type, name: id, bbox: { x: .1, y: .3, width: .5, height: .4 }, detectorConfidence: null, source: "USER", status: "USER_CONFIRMED", visible: true, locked: false, measurements: emptyMeasurements(), geometryMeasurements: [], interactionPoints: [], referencePoint: null };
}

test("empty schema 1.3 scene is valid", () => assert.equal(validateSceneState(emptySceneState()), true));

test("consistent non-collinear references create a perspective scale field", () => {
  const scene = emptySceneState();
  scene.calibration.references = [reference("a", .15, .85, 400, 100), reference("b", .82, .78, 350, 100), reference("c", .52, .28, 210, 100)];
  const calibration = rebuildPerspectiveField(scene.calibration);
  assert.equal(calibration.scaleField.status, "PERSPECTIVE_GOOD");
  assert.equal(calibration.scaleField.model, "INVERSE_AFFINE_2D");
  assert.equal(calibration.scaleField.inlierCount, 3);
});

test("a distant inconsistent reference is marked as outlier and excluded", () => {
  const scene = emptySceneState();
  scene.calibration.references = [
    reference("a", .1, .85, 390, 100), reference("b", .8, .82, 370, 100), reference("c", .45, .38, 240, 100),
    reference("bad", .92, .2, 900, 100),
  ];
  const calibration = rebuildPerspectiveField(scene.calibration);
  assert.equal(calibration.references.find((item) => item.id === "bad")?.residualStatus, "OUTLIER");
  assert.ok(calibration.scaleField.inlierCount < calibration.scaleField.anchorCount);
});

test("single reference remains local only", () => {
  const scene = emptySceneState(); scene.calibration.references = [reference("a", .5, .8, 300, 100)];
  assert.equal(rebuildPerspectiveField(scene.calibration).scaleField.status, "LOCAL_ONLY");
  assert.equal(calibrationQuality(scene.calibration), "PARTIAL");
});

test("consistent references clustered in one local region cannot claim good calibration", () => {
  const scene = emptySceneState();
  scene.calibration.references = [reference("a", .46, .55, 300, 100), reference("b", .51, .58, 294, 100), reference("c", .55, .51, 287, 100)];
  const calibration = rebuildPerspectiveField(scene.calibration);
  assert.equal(calibration.scaleField.status, "PERSPECTIVE_PARTIAL");
  assert.equal(calibrationQuality(calibration), "PARTIAL");
  assert.equal(calibrationSpatialCoverage(calibration.references).adequate, false);
});

test("calibration assistant points to a missing scene region", () => {
  const scene = emptySceneState(); scene.calibration.references = [reference("right", .8, .7, 300, 100)];
  assert.equal(calibrationAssistant(scene.calibration).region, "LEFT");
});

test("170 cm human preserves real height at A B and C while pixel size changes", () => {
  const scene = emptySceneState();
  scene.calibration.references = [reference("a", .15, .85, 400, 100), reference("b", .82, .78, 350, 100), reference("c", .52, .28, 210, 100)];
  const calibration = rebuildPerspectiveField(scene.calibration), profile = profileFromHeight("Operator", 170);
  const renderedPixels = [];
  for (const point of [{ x: .2, y: .82 }, { x: .52, y: .58 }, { x: .7, y: .35 }]) {
    const scale = estimateLocalScale(calibration, point, WIDTH, HEIGHT); assert.ok(scale);
    const pose = buildAnthropometricPose(profile, point, scale.pixelsPerCm, WIDTH, HEIGHT, "STANDING", 0);
    const actualCm = renderedHeightPixels(pose, HEIGHT) / scale.pixelsPerCm;
    assert.ok(Math.abs(actualCm - 170) < .001);
    renderedPixels.push(renderedHeightPixels(pose, HEIGHT));
  }
  assert.ok(Math.max(...renderedPixels) - Math.min(...renderedPixels) > 40);
});

test("perspective workstation regression fixture remains finite and correctly scaled", () => {
  const fixture = JSON.parse(readFileSync(new URL("./fixtures/perspective-scene-v12.json", import.meta.url), "utf8"));
  const scene = emptySceneState();
  scene.calibration.references = fixture.references.map((item) => reference(item.id, item.x, item.y, item.pixels, item.cm));
  const calibration = rebuildPerspectiveField(scene.calibration), profile = profileFromHeight("Fixture operator", fixture.human_height_cm);
  for (const point of fixture.standing_points) {
    const scale = estimateLocalScale(calibration, point, fixture.image.width, fixture.image.height); assert.ok(scale && Number.isFinite(scale.pixelsPerCm));
    const pose = buildAnthropometricPose(profile, point, scale.pixelsPerCm, fixture.image.width, fixture.image.height, "STANDING", 0);
    assert.ok(Object.values(pose.joints).every((joint) => Number.isFinite(joint.x) && Number.isFinite(joint.y)));
    assert.ok(Math.abs(renderedHeightPixels(pose, fixture.image.height) / scale.pixelsPerCm - fixture.human_height_cm) < .001);
  }
});

test("two-bone IK preserves both segment lengths for reachable and extreme targets", () => {
  const reachable = solveTwoBoneIk({ x: 0, y: 0 }, { x: .3, y: .2 }, .25, .2);
  assert.ok(Math.abs(distance({ x: 0, y: 0 }, reachable.joint) - .25) < 1e-9);
  assert.ok(Math.abs(distance(reachable.joint, reachable.end) - .2) < 1e-6);
  const extreme = solveTwoBoneIk({ x: 0, y: 0 }, { x: 20, y: -10 }, .3, .2);
  assert.ok(Math.abs(distance({ x: 0, y: 0 }, extreme.end) - .5) < 1e-9);
  assert.equal(extreme.reachState, "OUT_OF_REACH");
});

test("100 deterministic wrist targets never change arm segment lengths", () => {
  let human = createHuman("Operator", "#f97316");
  human.placement.lastScalePxPerCm = 3;
  const upper = human.constraints.upperArm.fixedLengthCm * 3, forearm = human.constraints.forearm.fixedLengthCm * 3;
  for (let index = 0; index < 100; index += 1) {
    const angle = index * 2.399963, radius = 40 + index % 11 * 18;
    const shoulder = human.pose.joints.leftShoulder;
    const target = { x: shoulder.x + Math.cos(angle) * radius / WIDTH, y: shoulder.y + Math.sin(angle) * radius / HEIGHT };
    human = moveHumanJointWithConstraints(human, "leftWrist", target, 3, WIDTH, HEIGHT);
    assert.ok(Math.abs(segmentLengthPixels(human, "leftShoulder", "leftElbow", WIDTH, HEIGHT) - upper) < 1e-6);
    assert.ok(Math.abs(segmentLengthPixels(human, "leftElbow", "leftWrist", WIDTH, HEIGHT) - forearm) < 1e-6);
  }
});

test("100 deterministic ankle targets never change leg segment lengths", () => {
  let human = createHuman("Operator", "#06b6d4");
  const thigh = human.constraints.thigh.fixedLengthCm * 2.8, lower = human.constraints.lowerLeg.fixedLengthCm * 2.8;
  for (let index = 0; index < 100; index += 1) {
    const angle = index * 1.618, radius = 80 + index % 9 * 22, hip = human.pose.joints.rightHip;
    human = moveHumanJointWithConstraints(human, "rightAnkle", { x: hip.x + Math.cos(angle) * radius / WIDTH, y: hip.y + Math.sin(angle) * radius / HEIGHT }, 2.8, WIDTH, HEIGHT);
    assert.ok(Math.abs(segmentLengthPixels(human, "rightHip", "rightKnee", WIDTH, HEIGHT) - thigh) < 1e-6);
    assert.ok(Math.abs(segmentLengthPixels(human, "rightKnee", "rightAnkle", WIDTH, HEIGHT) - lower) < 1e-6);
  }
});

test("bend preference remains stable around near-collinear targets", () => {
  let human = createHuman("Operator", "#a78bfa");
  const shoulder = human.pose.joints.rightShoulder;
  for (const offset of [-.0002, -.0001, 0, .0001, .0002]) human = moveHumanJointWithConstraints(human, "rightWrist", { x: shoulder.x + .15, y: shoulder.y + offset }, 3, WIDTH, HEIGHT);
  assert.equal(human.pose.bendPreference.rightArm, -1);
});

test("dimension profiles cover table rack chair monitor and custom object", () => {
  assert.deepEqual(dimensionsFor("TABLE").map((item) => item.key), ["workSurfaceHeightCm", "widthCm", "depthCm"]);
  assert.ok(dimensionsFor("RACK").some((item) => item.key === "keyShelfHeightCm"));
  assert.ok(dimensionsFor("CHAIR").some((item) => item.key === "seatWidthCm"));
  assert.ok(dimensionsFor("MONITOR").some((item) => item.key === "screenHeightCm"));
  assert.ok(dimensionsFor("OTHER").length > 0);
});

test("arm span updates only segments still marked as derived approximation", () => {
  const profile = profileFromHeight("Operator", 175), wider = profileWithArmSpan(profile, 190);
  assert.ok(createConstraintGraph(wider).upperArm.fixedLengthCm > createConstraintGraph(profile).upperArm.fixedLengthCm);
  const userProvided = { ...profile, upperArmLengthCm: 35, segmentProvenance: { ...profile.segmentProvenance, upperArm: "USER_PROVIDED" } };
  assert.equal(profileWithArmSpan(userProvided, 190).upperArmLengthCm, 35);
});

test("suggestions and next best action prioritize missing table height", () => {
  const scene = emptySceneState(); scene.objects.push(sceneObject());
  const suggestions = missingDimensionSuggestions(scene);
  assert.ok(suggestions.some((item) => item.key === "workSurfaceHeightCm" && item.priority === "CRITICAL"));
  assert.equal(nextBestAction(scene).kind, "CALIBRATION");
});

test("object and scene completeness use explicit categories", () => {
  const scene = emptySceneState(), table = sceneObject(); scene.objects.push(table);
  assert.equal(objectCompleteness("TABLE", table.measurements).ratio, 0);
  const completeness = sceneCompleteness(scene);
  assert.ok(completeness.categories.geometry.total > 0);
  assert.ok(completeness.categories.calibration.total > 0);
  assert.ok(completeness.categories.objects.total > 0);
});

test("label declutter produces unique positions and leader lines", () => {
  const measurements = Array.from({ length: 6 }, (_, index) => ({ id: `m-${index}`, objectId: "table", dimensionKey: "widthCm", name: `Pomiar ${index}`, valueCm: 100 + index, unit: "cm", start: { x: .45, y: .5 + index * .001 }, end: { x: .55, y: .5 + index * .001 }, orientation: "HORIZONTAL", source: "USER_MEASURED", estimateStatus: "MEASURED", evidenceQuality: "HIGH", reason: null, active: true, visible: true, locked: false, measurementKind: "OBJECT_WIDTH", axis: "HORIZONTAL", plane: "OBJECT_FRONT_PLANE", purpose: "OBJECT_DESCRIPTION", useForCalibration: false, semanticStatus: "CONFIRMED" }));
  const layout = layoutMeasurementLabels(measurements, 1);
  assert.equal(new Set(layout.map((item) => `${item.position.x.toFixed(4)}:${item.position.y.toFixed(4)}`)).size, layout.length);
  assert.ok(layout.some((item) => item.leader));
  assert.ok(layoutMeasurementLabels(measurements, .7).some((item) => item.compact));
});

test("legacy schema 1.0 is normalized to 1.3 without losing object human or reference", () => {
  const human = createHuman("Operator", "#f97316");
  const legacy = { schema_version: "1.0", objects: [{ ...sceneObject(), geometryMeasurements: undefined, interactionPoints: undefined }], calibration: { status: "PARTIALLY_CALIBRATED", floorBaseline: null, anchors: [{ id: "old", lower: { x: .2, y: .8 }, upper: { x: .2, y: .5 }, pixelDistance: 300, realDistanceCm: 100, objectId: null, source: "USER_PROVIDED" }] }, human: human.profile, pose: human.pose, viewport: { zoom: 1, pan_x: 0, pan_y: 0 } };
  const normalized = normalizeSceneState(legacy);
  assert.equal(normalized.schema_version, "1.3");
  assert.equal(normalized.objects.length, 1); assert.equal(normalized.humans.length, 1); assert.equal(normalized.calibration.references[0].valueCm, 100);
  assert.equal(validateSceneState(normalized), true);
});

test("legacy schema 1.1 keeps multiple humans and object measurements", () => {
  const scene = emptySceneState(); scene.objects.push(sceneObject()); scene.humans.push(createHuman("A", "#f97316"), createHuman("B", "#06b6d4", "TALL"));
  const legacy = { ...scene, schema_version: "1.1", geometryMeasurements: undefined, workerSuggestions: undefined, view: undefined };
  const normalized = normalizeSceneState(legacy);
  assert.equal(normalized.schema_version, "1.3");
  assert.equal(normalized.humans.length, 2);
  assert.equal(normalized.objects.length, 1);
});

test("invalid zero reference and negative human dimensions are rejected", () => {
  const scene = emptySceneState(); scene.calibration.references.push(reference("bad", .2, .2, 0, -1));
  assert.equal(validateSceneState(scene), false);
});
