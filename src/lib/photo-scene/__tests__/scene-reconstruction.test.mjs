import assert from "node:assert/strict";
import test from "node:test";

import { emptySceneState, normalizeSceneState, validateSceneState } from "../schema.ts";
import {
  applyReconstructionSummary, buildReconstructionInput, createSceneRegion,
  getReconstructedVerticalScale, nearestFeasiblePoint, pointInPolygon,
  sceneErgonomicsGeometryGate, solveSceneReconstruction,
} from "../scene-reconstruction.ts";

const IMAGE = { width: 1200, height: 900 };

function object(id = "table") {
  return {
    id, sourceClass: null, type: "TABLE", name: "Blat", bbox: { x: .2, y: .25, width: .55, height: .45 },
    detectorConfidence: null, source: "USER", status: "USER_CONFIRMED", visible: true, locked: false,
    measurements: Object.fromEntries(["heightCm","widthCm","depthCm","workSurfaceHeightCm","lowerEdgeHeightCm","upperEdgeHeightCm","seatHeightCm","seatWidthCm","backrestHeightCm","seatDepthCm","screenCenterHeightCm","screenHeightCm","userDistanceCm","keyShelfHeightCm","workingWidthCm","controlHeightCm"].map((key) => [key, null])),
    geometryMeasurements: [], interactionPoints: [], referencePoint: null, geometry3d: null, interactionPoints3d: [],
    regionIds: ["top"], faceIds: [], planeIds: [], shapeAssumptions: ["RECTANGULAR", "PLANAR"], reconstructionQuality: "UNSOLVED",
  };
}

function dimension(id, type, value, objectId = "table", start = { x: .3, y: .75 }, end = { x: .3, y: .75 - value * 2 / IMAGE.height }) {
  return {
    id, type, nodeIds: [], objectId, regionId: "top", target: { kind: "EDGE", id: null, point: null },
    rawValue: value, effectiveValue: value, unit: "cm", source: "USER_PROVIDED", weight: 1,
    useForSolver: true, status: "ACTIVE", residual: null, imageSegment: { start, end },
  };
}

function completeScene(heights = [80, 80, 80, 80], includeDepth = true) {
  const scene = emptySceneState();
  scene.objects = [object()];
  scene.regions = [
    createSceneRegion({ id: "floor", type: "FLOOR_REGION", label: "Podłoga", points: [{ x: .1, y: .7 }, { x: .9, y: .7 }, { x: .98, y: .98 }, { x: .02, y: .98 }] }),
    createSceneRegion({ id: "top", type: "WORK_SURFACE", label: "Blat", associatedObjectId: "table", points: [{ x: .25, y: .4 }, { x: .72, y: .42 }, { x: .62, y: .55 }, { x: .18, y: .52 }] }),
    createSceneRegion({ id: "move", type: "MOVEMENT_ZONE", label: "Pole ruchu", points: [{ x: .15, y: .72 }, { x: .85, y: .72 }, { x: .9, y: .95 }, { x: .1, y: .95 }] }),
  ];
  scene.constraintGraph.constraints = [
    ...heights.map((height, index) => dimension(`height-${index}`, "HEIGHT", height, "table", { x: .25 + index * .12, y: .75 }, { x: .25 + index * .12, y: .75 - height * 2 / IMAGE.height })),
    dimension("width", "WIDTH", 160, "table", { x: .25, y: .4 }, { x: .72, y: .42 }),
    ...(includeDepth ? [dimension("depth", "DEPTH", 70, "table", { x: .25, y: .4 }, { x: .18, y: .52 })] : []),
  ];
  return scene;
}

function solve(scene) {
  return solveSceneReconstruction(buildReconstructionInput(scene, IMAGE, "test-revision"));
}

test("schema 1.5 stores first-class regions and remains valid", () => {
  const scene = completeScene();
  assert.equal(scene.schema_version, "1.5");
  assert.equal(validateSceneState(scene), true);
  assert.equal(scene.regions[1].polygonImageNormalized.length, 4);
});

test("legacy schema 1.4 normalizes without converting arbitrary lines into regions", () => {
  const current = emptySceneState();
  const legacy = { ...current, schema_version: "1.4", regions: undefined, planes: undefined, objectFaces: undefined, constraintGraph: undefined, reconstructionState: undefined };
  const normalized = normalizeSceneState(legacy);
  assert.equal(normalized.schema_version, "1.5");
  assert.deepEqual(normalized.regions, []);
  assert.equal(normalized.geometryMeasurements.length, current.geometryMeasurements.length);
});

test("four equal heights plus width and depth solve a stable table", () => {
  const scene = completeScene();
  const input = buildReconstructionInput(scene, IMAGE, "test-revision");
  const result = solveSceneReconstruction(input);
  assert.ok(input.constraintGraph.constraints.some((item) => item.id === "assumption:table:RECTANGULAR"));
  assert.ok(input.constraintGraph.constraints.some((item) => item.id === "assumption:table:PLANAR"));
  assert.equal(result.status, "SOLVED");
  assert.equal(result.derivedDimensions.table.heightCm, 80);
  assert.equal(result.derivedDimensions.table.widthCm, 160);
  assert.equal(result.derivedDimensions.table.depthCm, 70);
  assert.equal(result.readiness.HUMAN_PLACEMENT.status, "READY");
});

test("floor region receives a real homography only with two known ground dimensions", () => {
  const scene = completeScene();
  const groundWidth = dimension("ground-width", "WIDTH", 240, null, { x: .1, y: .7 }, { x: .9, y: .7 });
  const groundDepth = dimension("ground-depth", "DEPTH", 180, null, { x: .1, y: .7 }, { x: .02, y: .98 });
  groundWidth.regionId = "floor";
  groundDepth.regionId = "floor";
  scene.constraintGraph.constraints.push(groundWidth, groundDepth);
  const result = solve(scene);
  const plane = result.planes.find((item) => item.regionId === "floor");
  assert.equal(plane.homography.length, 9);
  assert.equal(result.groundModel.status, "PROJECTIVE");
  assert.equal(result.worldGeometry["region:move"].status, "PROJECTIVE");
  assert.equal(result.worldGeometry["region:move"].polygonCm.length, 4);
  assert.ok(result.worldGeometry["region:move"].polygonCm.every((point) => Number.isFinite(point.x) && point.y === 0 && Number.isFinite(point.z)));
});

test("79 80 81 80 use robust best fit with small residuals", () => {
  const result = solve(completeScene([79, 80, 81, 80]));
  assert.ok(Math.abs(result.derivedDimensions.table.heightCm - 80) < .4);
  assert.equal(result.outlierConstraintIds.length, 0);
  assert.ok(result.constraintResiduals["height-0"] <= 1.1);
});

test("adding three more valid heights cannot silently destabilize a two-height solution", () => {
  const initial = solve(completeScene([80, 80]));
  const enriched = solve(completeScene([80, 80, 79.8, 80.2, 80]));
  assert.ok(["SOLVED", "PARTIAL"].includes(initial.status));
  assert.ok(["SOLVED", "PARTIAL"].includes(enriched.status) || enriched.conflicts.length > 0);
  assert.ok(Math.abs(enriched.derivedDimensions.table.heightCm - initial.derivedDimensions.table.heightCm) < .25);
  assert.ok(Math.abs(enriched.verticalScaleModel.pixelsPerCm - initial.verticalScaleModel.pixelsPerCm) < .02);
});

test("80 80 80 300 isolates 300 as outlier and keeps human scale stable", () => {
  const result = solve(completeScene([80, 80, 80, 300]));
  assert.deepEqual(result.outlierConstraintIds, ["height-3"]);
  assert.equal(result.derivedDimensions.table.heightCm, 80);
  assert.ok(Math.abs(result.verticalScaleModel.pixelsPerCm - 2) < 1e-9);
});

test("twenty widths cannot modify reconstructed vertical scale", () => {
  const scene = completeScene();
  const before = solve(scene).verticalScaleModel.pixelsPerCm;
  for (let index = 0; index < 20; index += 1) scene.constraintGraph.constraints.push(dimension(`width-${index}`, "WIDTH", 160 + (index % 3 - 1) * .2));
  const after = solve(scene).verticalScaleModel.pixelsPerCm;
  assert.equal(after, before);
});

test("depth cannot modify reconstructed vertical scale", () => {
  const scene = completeScene([], false);
  scene.constraintGraph.constraints.push(dimension("height", "HEIGHT", 80));
  const before = solve(scene).verticalScaleModel.pixelsPerCm;
  scene.constraintGraph.constraints.push(dimension("wild-depth", "DEPTH", 900));
  assert.equal(solve(scene).verticalScaleModel.pixelsPerCm, before);
});

test("unknown depth keeps human placement ready and collision incomplete", () => {
  const result = solve(completeScene([80, 80, 80, 80], false));
  assert.equal(result.readiness.HUMAN_PLACEMENT.status, "READY");
  assert.equal(result.readiness.COLLISION.status, "NEEDS_DEPTH");
  assert.equal(result.nextBestMeasurements[0].measurementKind, "OBJECT_DEPTH");
});

test("self-intersecting quad is repaired while raw points are preserved in audit", () => {
  const scene = completeScene();
  scene.regions[1] = createSceneRegion({ id: "top", type: "WORK_SURFACE", label: "Blat", associatedObjectId: "table", points: [{ x: .2, y: .3 }, { x: .8, y: .7 }, { x: .8, y: .3 }, { x: .2, y: .7 }] });
  const original = scene.regions[1].polygonImageNormalized.map((point) => point.raw);
  const result = solve(scene);
  assert.equal(result.autoRepairs[0].type, "POLYGON_ORDER");
  assert.deepEqual(result.autoRepairs[0].before, original);
});

test("conflicting user dimensions remain raw and become an explicit conflict", () => {
  const scene = completeScene();
  scene.constraintGraph.constraints = scene.constraintGraph.constraints.filter((item) => item.type !== "WIDTH");
  const first = dimension("front-width", "WIDTH", 120), second = dimension("back-width", "WIDTH", 220);
  scene.constraintGraph.constraints.push(first, second);
  const result = solve(scene);
  assert.equal(first.rawValue, 120);
  assert.equal(second.rawValue, 220);
  assert.equal(result.status, "INCONSISTENT");
  assert.equal(result.conflicts[0].code, "CONSTRAINT_CONFLICT");
});

test("movement zone accepts only inside samples and nearest point reports correction", () => {
  const region = completeScene().regions.find((item) => item.type === "MOVEMENT_ZONE");
  assert.equal(pointInPolygon({ x: .5, y: .82 }, region), true);
  assert.equal(pointInPolygon({ x: .98, y: .1 }, region), false);
  const corrected = nearestFeasiblePoint({ x: .98, y: .1 }, region);
  assert.equal(corrected.corrected, true);
  assert.ok(corrected.deltaNormalized > 0);
  assert.equal(pointInPolygon(corrected.point, region), true);
});

test("100 movement positions keep a 175 cm physical human constant", () => {
  const scene = completeScene();
  const reconstructed = applyReconstructionSummary(scene, solve(scene));
  for (let row = 0; row < 10; row += 1) for (let column = 0; column < 10; column += 1) {
    const scale = getReconstructedVerticalScale(reconstructed, { x: .2 + column * .06, y: .75 + row * .018 });
    assert.ok(scale?.pixelsPerCm);
    assert.ok(Math.abs((175 * scale.pixelsPerCm) / scale.pixelsPerCm - 175) < 1e-9);
  }
});

test("projection scale is continuous across adjacent movement points", () => {
  const scene = applyReconstructionSummary(completeScene(), solve(completeScene()));
  let previous = null;
  for (let index = 0; index < 100; index += 1) {
    const scale = getReconstructedVerticalScale(scene, { x: .2 + index * .005, y: .8 });
    assert.ok(scale?.pixelsPerCm);
    if (previous !== null) assert.ok(Math.abs(scale.pixelsPerCm - previous) < .01);
    previous = scale.pixelsPerCm;
  }
});

test("three spatial heights create a continuous local vertical perspective model", () => {
  const scene = completeScene();
  scene.constraintGraph.constraints = scene.constraintGraph.constraints.filter((item) => item.type !== "HEIGHT");
  for (const [index, centerY] of [.25, .5, .75].entries()) {
    const inverseScale = .42 + .16 * centerY;
    const pixelsPerCm = 1 / inverseScale;
    const halfNormalized = 80 * pixelsPerCm / IMAGE.height / 2;
    scene.constraintGraph.constraints.push(dimension(`perspective-${index}`, "HEIGHT", 80, "table", { x: .3 + index * .15, y: centerY + halfNormalized }, { x: .3 + index * .15, y: centerY - halfNormalized }));
  }
  const reconstructed = applyReconstructionSummary(scene, solve(scene));
  assert.equal(reconstructed.reconstructionState.verticalScaleModel.kind, "INVERSE_AFFINE_VERTICAL");
  const near = getReconstructedVerticalScale(reconstructed, { x: .5, y: .25 });
  const far = getReconstructedVerticalScale(reconstructed, { x: .5, y: .75 });
  assert.ok(near.pixelsPerCm > far.pixelsPerCm);
  assert.ok(Math.abs(near.pixelsPerCm - far.pixelsPerCm) < 1);
});

test("underdetermined scene asks for exactly one most informative measurement", () => {
  const scene = emptySceneState();
  scene.objects = [object()];
  scene.regions = [createSceneRegion({ id: "top", type: "WORK_SURFACE", label: "Blat", associatedObjectId: "table", points: [{ x: .2, y: .3 }, { x: .8, y: .3 }, { x: .7, y: .5 }, { x: .25, y: .5 }] })];
  const result = solve(scene);
  assert.equal(result.status, "UNDERDETERMINED");
  assert.equal(result.nextBestMeasurements.length, 1);
  assert.equal(result.nextBestMeasurements[0].measurementKind, "VERTICAL_HEIGHT");
});

test("Scene Ergonomics is gated until human placement geometry is ready", () => {
  const unsolved = emptySceneState();
  assert.equal(sceneErgonomicsGeometryGate(unsolved).allowed, false);
  const reconstructed = applyReconstructionSummary(completeScene(), solve(completeScene()));
  assert.equal(sceneErgonomicsGeometryGate(reconstructed).allowed, true);
});
