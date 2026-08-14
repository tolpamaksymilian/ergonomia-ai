import assert from "node:assert/strict";
import test from "node:test";

import { rebuildPerspectiveField } from "../calibration.ts";
import { createHuman, profileFromHeight } from "../anthropometry.ts";
import { measurementDirectionWarning, semanticsForReferenceType, validateMeasurementForCalibration } from "../measurement-semantics.ts";
import { emptySceneState, normalizeSceneState } from "../schema.ts";
import { createSceneWorldModel, getCalibrationCoverageAt, getGroundProjectionAt, getHumanProjectionAt, getMeasurementPlane, getVerticalScaleAt } from "../scene-world-model.ts";

const WIDTH = 1200;
const HEIGHT = 900;

function verticalReference(id, x, bottomY, pixels, cm, overrides = {}) {
  const topY = bottomY - pixels / HEIGHT;
  return {
    id, name: id, dimensionType: "HEIGHT", valueCm: cm, unit: "cm",
    start: { x, y: bottomY }, end: { x, y: topY }, pixelDistance: pixels, objectId: null,
    active: true, visible: true, locked: false,
    measurementKind: "VERTICAL_HEIGHT", axis: "VERTICAL", plane: "VERTICAL_PLANE",
    purpose: "CALIBRATION", useForCalibration: true, semanticStatus: "CONFIRMED",
    worldAnchors: {
      bottom: { id: `${id}-bottom`, imagePoint: { x, y: bottomY }, worldHeightCm: 0, role: "BOTTOM" },
      top: { id: `${id}-top`, imagePoint: { x, y: topY }, worldHeightCm: cm, role: "TOP" },
    },
    source: "USER_PROVIDED", residual: null, residualStatus: "UNASSESSED", manualOverride: false,
    ...overrides,
  };
}

function worldWith(references) {
  const scene = emptySceneState();
  scene.calibration.references = references;
  scene.calibration = rebuildPerspectiveField(scene.calibration);
  return createSceneWorldModel(scene.calibration, WIDTH, HEIGHT);
}

test("Measurement Semantics V2 maps reference types onto separate axes and planes", () => {
  assert.deepEqual(semanticsForReferenceType("HEIGHT"), { measurementKind: "VERTICAL_HEIGHT", axis: "VERTICAL", plane: "VERTICAL_PLANE", purpose: "CALIBRATION" });
  assert.equal(semanticsForReferenceType("WIDTH").axis, "HORIZONTAL");
  assert.equal(semanticsForReferenceType("DEPTH").plane, "OBJECT_TOP_PLANE");
  assert.equal(semanticsForReferenceType("CUSTOM").purpose, "INFORMATION_ONLY");
});

test("only confirmed selected vertical references validate for human scale", () => {
  assert.equal(validateMeasurementForCalibration(verticalReference("v", .5, .9, 380, 190)).valid, true);
  assert.equal(validateMeasurementForCalibration(verticalReference("w", .5, .9, 100, 50, { measurementKind: "HORIZONTAL_WIDTH", axis: "HORIZONTAL", plane: "OBJECT_FRONT_PLANE" })).valid, false);
  assert.equal(validateMeasurementForCalibration(verticalReference("d", .5, .9, 100, 50, { measurementKind: "DEPTH", axis: "GROUND_Y", plane: "OBJECT_TOP_PLANE" })).valid, false);
  assert.equal(validateMeasurementForCalibration(verticalReference("i", .5, .9, 100, 50, { purpose: "INFORMATION_ONLY" })).valid, false);
  assert.equal(validateMeasurementForCalibration(verticalReference("r", .5, .9, 380, 190, { semanticStatus: "SEMANTICS_REVIEW_REQUIRED" })).valid, false);
});

test("wrong declared direction produces a non-blocking warning", () => {
  const warning = measurementDirectionWarning({ x: .1, y: .5 }, { x: .9, y: .5 }, semanticsForReferenceType("HEIGHT"), { x: .087, y: -.996 });
  assert.match(warning, /poziomy/);
  assert.equal(measurementDirectionWarning({ x: .5, y: .9 }, { x: .57, y: .2 }, semanticsForReferenceType("HEIGHT"), { x: .087, y: -.996 }), null);
});

test("golden 190 cm human and 190 cm reference have matching projected spans", () => {
  const model = worldWith([verticalReference("human-height", .5, .9, 380, 190)]);
  const human = createHuman("Operator 190", "#f97316", "TALL");
  const projected = getHumanProjectionAt(model, human, { x: .5, y: .9 });
  assert.equal(projected.projectionStatus, "VALID");
  assert.ok(Math.abs(projected.projectedHeightPx - 380) < 1e-8);
  assert.equal(projected.backConvertedHeightCm, 190);
});

test("50 cm horizontal measurement cannot change human vertical projection", () => {
  const vertical = verticalReference("v190", .5, .9, 380, 190);
  const before = getHumanProjectionAt(worldWith([vertical]), createHuman("Operator", "#f97316", "TALL"), { x: .5, y: .9 });
  const horizontal = verticalReference("width50", .5, .9, 240, 50, { measurementKind: "HORIZONTAL_WIDTH", axis: "HORIZONTAL", plane: "OBJECT_FRONT_PLANE", purpose: "OBJECT_DESCRIPTION", useForCalibration: false, worldAnchors: { bottom: null, top: null } });
  const after = getHumanProjectionAt(worldWith([vertical, horizontal]), createHuman("Operator", "#f97316", "TALL"), { x: .5, y: .9 });
  assert.equal(after.projectedHeightPx, before.projectedHeightPx);
});

test("depth measurement cannot change human vertical projection", () => {
  const vertical = verticalReference("v190", .5, .9, 380, 190);
  const before = getVerticalScaleAt(worldWith([vertical]), { x: .5, y: .9 });
  const depth = verticalReference("depth100", .5, .9, 300, 100, { measurementKind: "OBJECT_DEPTH", axis: "GROUND_Y", plane: "OBJECT_TOP_PLANE", purpose: "OBJECT_DESCRIPTION", useForCalibration: false, worldAnchors: { bottom: null, top: null } });
  const after = getVerticalScaleAt(worldWith([vertical, depth]), { x: .5, y: .9 });
  assert.equal(after.pixelsPerCm, before.pixelsPerCm);
});

test("table height affects vertical scale only when explicitly confirmed for calibration", () => {
  const off = verticalReference("table80", .4, .9, 160, 80, { measurementKind: "WORK_SURFACE_HEIGHT", purpose: "OBJECT_DESCRIPTION", useForCalibration: false });
  assert.equal(getVerticalScaleAt(worldWith([off]), { x: .4, y: .9 }).pixelsPerCm, null);
  const on = { ...off, purpose: "CALIBRATION", useForCalibration: true };
  assert.equal(getVerticalScaleAt(worldWith([on]), { x: .4, y: .9 }).pixelsPerCm, 2);
});

test("screenshot regression fixture 190 vertical, 80 vertical and 50 horizontal has no 2x jump", () => {
  const references = [
    verticalReference("left190", .18, .88, 380, 190),
    verticalReference("right80", .78, .82, 144, 80),
    verticalReference("width50", .5, .6, 260, 50, { measurementKind: "HORIZONTAL_WIDTH", axis: "HORIZONTAL", plane: "OBJECT_FRONT_PLANE", purpose: "OBJECT_DESCRIPTION", useForCalibration: false, worldAnchors: { bottom: null, top: null } }),
  ];
  const model = worldWith(references), human = createHuman("Operator 190", "#f97316", "TALL");
  const a = getHumanProjectionAt(model, human, { x: .2, y: .87 });
  const b = getHumanProjectionAt(model, human, { x: .76, y: .82 });
  assert.equal(a.physicalHeightCm, 190); assert.equal(b.physicalHeightCm, 190);
  assert.equal(a.backConvertedHeightCm, 190); assert.equal(b.backConvertedHeightCm, 190);
  assert.ok(Math.max(a.projectedHeightPx, b.projectedHeightPx) / Math.min(a.projectedHeightPx, b.projectedHeightPx) < 1.35);
});

test("two vertical regions interpolate local vertical scale without changing physical height", () => {
  const model = worldWith([verticalReference("left", .15, .9, 300, 100), verticalReference("right", .85, .8, 200, 100)]);
  const human = createHuman("Operator", "#06b6d4");
  const left = getHumanProjectionAt(model, human, { x: .18, y: .88 });
  const right = getHumanProjectionAt(model, human, { x: .82, y: .8 });
  assert.equal(left.physicalHeightCm, 175); assert.equal(right.physicalHeightCm, 175);
  assert.notEqual(left.projectedHeightPx, right.projectedHeightPx);
});

test("placement outside calibrated coverage is rejected instead of aggressively extrapolated", () => {
  const model = worldWith([verticalReference("left", .08, .85, 300, 100)]);
  const coverage = getCalibrationCoverageAt(model, { x: .95, y: .15 });
  assert.equal(coverage.quality, "UNKNOWN");
  const projected = getHumanProjectionAt(model, createHuman("Operator", "#f97316"), { x: .95, y: .15 });
  assert.equal(projected.projectionStatus, "PROJECTION_INVALID");
  assert.equal(projected.projectionError, "CALIBRATION_COVERAGE_UNKNOWN");
});

test("absurd projected height is an explicit error and is not silently clamped", () => {
  const model = worldWith([verticalReference("bad", .5, .9, 2000, 80)]);
  const projected = getHumanProjectionAt(model, createHuman("Operator", "#f97316"), { x: .5, y: .9 });
  assert.equal(projected.projectionStatus, "PROJECTION_INVALID");
  assert.equal(projected.projectedHeightPx, null);
  assert.equal(projected.projectionError, "PROJECTED_HEIGHT_OUT_OF_RANGE");
});

test("old schema 1.2 measurements require semantic review and do not affect Calibration V3", () => {
  const current = emptySceneState(), legacyReference = verticalReference("old", .5, .9, 380, 190);
  delete legacyReference.measurementKind; delete legacyReference.axis; delete legacyReference.plane; delete legacyReference.purpose; delete legacyReference.useForCalibration; delete legacyReference.semanticStatus; delete legacyReference.worldAnchors;
  const normalized = normalizeSceneState({ ...current, schema_version: "1.2", calibration: { ...current.calibration, references: [legacyReference] } });
  assert.equal(normalized.schema_version, "1.4");
  assert.equal(normalized.calibration.references[0].semanticStatus, "SEMANTICS_REVIEW_REQUIRED");
  assert.equal(normalized.calibration.references[0].useForCalibration, false);
  assert.equal(getVerticalScaleAt(createSceneWorldModel(normalized.calibration, WIDTH, HEIGHT), { x: .5, y: .9 }).pixelsPerCm, null);
});

test("ground model keeps basic and quadrilateral geometry separate from vertical scale", () => {
  const scene = emptySceneState();
  scene.calibration.floorBaseline = { start: { x: .1, y: .9 }, end: { x: .9, y: .8 } };
  scene.calibration.floorPlane = { mode: "BASIC", points: [scene.calibration.floorBaseline.start, scene.calibration.floorBaseline.end], actualGroundDimensionCm: null, mappingStatus: "ORIENTATION_ONLY" };
  const basic = getGroundProjectionAt(createSceneWorldModel(scene.calibration, WIDTH, HEIGHT), { x: .5, y: .5 });
  assert.equal(basic.status, "GROUND_BASIC");
  assert.ok(Math.abs(basic.point.y - .85) < 1e-9);
  scene.calibration.floorPlane = { mode: "QUADRILATERAL", points: [{ x: .1, y: .9 }, { x: .9, y: .9 }, { x: .7, y: .5 }, { x: .3, y: .5 }], actualGroundDimensionCm: null, mappingStatus: "ORIENTATION_ONLY" };
  assert.equal(getGroundProjectionAt(createSceneWorldModel(scene.calibration, WIDTH, HEIGHT), { x: .5, y: .7 }).status, "GROUND_LOCAL");
});

test("measurement plane API returns explicit object plane", () => {
  assert.equal(getMeasurementPlane({ plane: "OBJECT_TOP_PLANE" }), "OBJECT_TOP_PLANE");
});

test("canonical profiles 160 175 and 190 remain exact through scene projection", () => {
  for (const stature of [160, 175, 190]) {
    const model = worldWith([verticalReference(`v-${stature}`, .5, .9, stature * 2, stature)]);
    const human = createHuman(`H${stature}`, "#f97316", "CUSTOM");
    human.profile = profileFromHeight(human.name, stature, "CUSTOM");
    const projected = getHumanProjectionAt(model, human, { x: .5, y: .9 });
    assert.equal(projected.physicalHeightCm, stature);
    assert.equal(projected.backConvertedHeightCm, stature);
  }
});
