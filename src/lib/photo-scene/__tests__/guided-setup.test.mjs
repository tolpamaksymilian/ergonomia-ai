import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { mergeSceneDetection } from "../analysis-control.ts";
import {
  GUIDED_SCENE_STEPS,
  bboxFromPolygon,
  buildGuidedWorkerContext,
  createMovementZoneFromFloor,
  deriveGuidedSetupStatus,
  heightSpreadAdvice,
  measurementAssociationSuggestions,
  polygonSelfIntersects,
} from "../guided-setup.ts";
import { emptyMeasurements, emptySceneState } from "../schema.ts";

function point(x, y) { return { raw: { x, y }, snapped: null, effective: { x, y }, snapSourceId: null, snapDistancePx: null }; }
function region(id, type, points, objectId = null) { return { id, type, label: type, polygonImageNormalized: points.map(([x, y]) => point(x, y)), associatedObjectId: objectId, planeId: null, source: "USER_PROVIDED", quality: "HIGH", visible: true, locked: false, createdAt: "2026-08-16T00:00:00Z", updatedAt: "2026-08-16T00:00:00Z" }; }
function height(id, x, value = 100) { return { id, name: id, dimensionType: "HEIGHT", valueCm: value, unit: "cm", start: { x, y: .85 }, end: { x, y: .45 }, pixelDistance: 360, objectId: null, active: true, visible: true, locked: false, measurementKind: "VERTICAL_HEIGHT", axis: "VERTICAL", plane: "VERTICAL_PLANE", purpose: "CALIBRATION", useForCalibration: true, semanticStatus: "CONFIRMED", worldAnchors: { bottom: { id: `${id}-b`, imagePoint: { x, y: .85 }, worldHeightCm: 0, role: "BOTTOM" }, top: { id: `${id}-t`, imagePoint: { x, y: .45 }, worldHeightCm: value, role: "TOP" } }, source: "USER_PROVIDED", residual: null, residualStatus: "UNASSESSED", manualOverride: false }; }
function dimension(id, type, axis) { return { ...height(id, .5, 120), dimensionType: type, measurementKind: type === "WIDTH" ? "HORIZONTAL_WIDTH" : type === "DEPTH" ? "DEPTH" : "FLOOR_DISTANCE", axis, plane: axis === "GROUND_X" || axis === "GROUND_Y" ? "GROUND_PLANE" : "OBJECT_FRONT_PLANE", purpose: "OBJECT_DESCRIPTION", useForCalibration: false, worldAnchors: { bottom: null, top: null }, start: { x: .2, y: .55 }, end: { x: .8, y: .55 } }; }
function table(id = "table") { return { id, sourceClass: null, type: "TABLE", name: "Blat", bbox: { x: .15, y: .35, width: .7, height: .35 }, detectorConfidence: null, source: "USER", status: "USER_ADDED", visible: true, locked: false, measurements: emptyMeasurements(), geometryMeasurements: [], interactionPoints: [], referencePoint: null, geometry3d: null, interactionPoints3d: [], regionIds: ["table-region"], faceIds: [], planeIds: [], shapeAssumptions: ["RECTANGULAR", "PLANAR"], reconstructionQuality: "UNSOLVED" }; }
function requiredScene(heightCount = 2) { const state = emptySceneState(); const floor = region("floor", "FLOOR_REGION", [[.05,.65],[.95,.65],[.95,.98],[.05,.98]]); state.regions = [floor, createMovementZoneFromFloor(floor, "2026-08-16T00:00:00Z")]; state.calibration.references = Array.from({ length: heightCount }, (_, index) => height(`h${index}`, .15 + index * .65 / Math.max(1, heightCount - 1))); return state; }

test("guided order is exactly photo floor heights dimensions objects worker verify human ergonomics", () => {
  assert.deepEqual(GUIDED_SCENE_STEPS.map((step) => step.id), ["PHOTO", "FLOOR", "HEIGHTS", "DIMENSIONS", "OBJECTS", "BUILD", "VERIFY", "HUMAN", "ERGONOMICS"]);
});

test("new scene before image starts at photo and uploaded image starts at floor", () => {
  const state = emptySceneState();
  assert.equal(deriveGuidedSetupStatus(state, { hasImage: false }).recommendedStep, "PHOTO");
  assert.equal(deriveGuidedSetupStatus(state).recommendedStep, "FLOOR");
});

test("floor and default movement unlock height step", () => {
  const state = requiredScene(0);
  const status = deriveGuidedSetupStatus(state);
  assert.equal(status.hasFloor, true); assert.equal(status.hasMovementZone, true); assert.equal(status.recommendedStep, "HEIGHTS");
});

test("zero and one heights block build while two unlock it", () => {
  assert.equal(deriveGuidedSetupStatus(requiredScene(0)).canBuild, false);
  assert.equal(deriveGuidedSetupStatus(requiredScene(1)).canBuild, false);
  assert.equal(deriveGuidedSetupStatus(requiredScene(2)).canBuild, true);
});

test("two three four five and ten heights are preserved without a hard limit", () => {
  for (const count of [2, 3, 4, 5, 10]) assert.equal(deriveGuidedSetupStatus(requiredScene(count)).heightCount, count);
});

test("width depth and floor distance are optional and multiple values remain in context", () => {
  const state = requiredScene(2);
  state.calibration.references.push(...Array.from({ length: 4 }, (_, index) => dimension(`w${index}`, "WIDTH", "HORIZONTAL")), ...Array.from({ length: 3 }, (_, index) => dimension(`d${index}`, "DEPTH", "GROUND_Y")), ...Array.from({ length: 2 }, (_, index) => dimension(`g${index}`, "DISTANCE", "GROUND_X")));
  const status = deriveGuidedSetupStatus(state), context = buildGuidedWorkerContext(state, { width: 1200, height: 900 });
  assert.equal(status.canBuild, true); assert.equal(status.dimensionCount, 9); assert.equal(context.dimensionReferences.length, 9);
});

test("worker context contains floor movement all heights dimensions manual objects surfaces and graph", () => {
  const state = requiredScene(5); const object = table(); const surface = region("table-region", "WORK_SURFACE", [[.15,.35],[.85,.35],[.8,.55],[.2,.55]], object.id);
  state.objects = [object]; state.regions.push(surface); state.calibration.references.push(dimension("width", "WIDTH", "HORIZONTAL"));
  state.constraintGraph.constraints.push({ id: "c", type: "WIDTH", nodeIds: [], objectId: null, regionId: null, target: { kind: "EDGE", id: "width", point: null }, rawValue: 120, effectiveValue: 120, unit: "cm", source: "USER_PROVIDED", weight: 1, useForSolver: true, status: "ACTIVE", residual: null, imageSegment: { start: { x: .2, y: .55 }, end: { x: .8, y: .55 } } });
  const context = buildGuidedWorkerContext(state, { width: 1200, height: 900, storagePath: "owner/id/source/photo.jpg" }, "revision");
  assert.equal(context.floorRegions.length, 1); assert.equal(context.movementZones.length, 1); assert.equal(context.heightReferences.length, 5); assert.equal(context.dimensionReferences.length, 1); assert.equal(context.manualObjects.length, 1); assert.equal(context.manualSurfaces.length, 1); assert.equal(context.constraintGraph.constraints.length, 1); assert.equal(context.originalImage.storagePath, "owner/id/source/photo.jpg");
});

test("manual object type and region outrank overlapping worker prediction", () => {
  const state = requiredScene(2); state.objects = [table()];
  const detection = { schema_version: "1.0", detection_version: "scene-detection-v0.3-beta.1", analysis_id: "a", source_image: { width: 100, height: 100 }, candidates: [{ id: "detector", source_class: "tv", suggested_scene_type: "MONITOR", bounding_box: { x: .17, y: .37, width: .65, height: .3 }, confidence: .9, source: "YOLOX_X_COCO", status: "DETECTED" }], limitations: [] };
  const merged = mergeSceneDetection(state, detection);
  assert.equal(merged.objects.length, 1); assert.equal(merged.objects[0].type, "TABLE"); assert.equal(merged.objects[0].source, "USER"); assert.equal(merged.regions.length, state.regions.length);
});

test("scene reference is suggested for association but never assigned automatically", () => {
  const state = requiredScene(2), object = table(); state.objects = [object]; state.regions.push(region("table-region", "WORK_SURFACE", [[.15,.35],[.85,.35],[.8,.6],[.2,.6]], object.id)); state.calibration.references.push(dimension("width", "WIDTH", "HORIZONTAL"));
  const suggestions = measurementAssociationSuggestions(state, object);
  assert.equal(suggestions.length, 1); assert.equal(state.calibration.references.at(-1).objectId, null);
});

test("clustered heights produce spatial spread advice", () => assert.match(heightSpreadAdvice([height("a", .45), height("b", .5)]), /części zdjęcia/));
test("polygon utilities detect a bow tie and create a stable bbox", () => { assert.equal(polygonSelfIntersects([{x:.1,y:.1},{x:.9,y:.9},{x:.1,y:.9},{x:.9,y:.1}]), true); assert.deepEqual(bboxFromPolygon([{x:.2,y:.3},{x:.8,y:.4},{x:.5,y:.9}]), { x: .2, y: .3, width: .6000000000000001, height: .6000000000000001 }); });

test("guided UI exposes one worker CTA and no old simple flow order", () => {
  const source = readFileSync(new URL("../../../components/photo-scene/guided-scene-setup.tsx", import.meta.url), "utf8");
  assert.match(source, /Rozpoznaj i zbuduj scenę/); assert.doesNotMatch(source, /Analizuj zdjęcie.*Oblicz geometrię/s);
});

test("geometry changes explicitly invalidate reconstruction review and readiness", () => {
  const source = readFileSync(new URL("../../../components/photo-scene/photo-scene-editor.tsx", import.meta.url), "utf8");
  assert.match(source, /reviewStatus: "UNREVIEWED"/); assert.match(source, /status: "STALE"/);
});
