import assert from "node:assert/strict";
import test from "node:test";

import { buildAnthropometricPose, createHuman, profileFromHeight, renderedHeightPixels } from "../anthropometry.ts";
import { estimateLocalScale, rebuildPerspectiveField } from "../calibration.ts";
import { moveHumanJointWithConstraints, segmentLengthPixels, solveTwoBoneIk } from "../geometry.ts";
import { getCanonicalHuman } from "../human-physical-model.ts";
import { buildCanonicalPose, validateCanonicalPose } from "../human-pose-model.ts";
import { getGroundPlaneStatus, getProjectedHuman } from "../human-projection.ts";
import { emptySceneState, normalizeSceneState, validateSceneState } from "../schema.ts";

const WIDTH = 1200;
const HEIGHT = 900;

function reference(id, x, y, pixels, cm) {
  return { id, name: id, dimensionType: "HEIGHT", valueCm: cm, unit: "cm", start: { x, y }, end: { x, y: y - .2 }, pixelDistance: pixels, objectId: null, active: true, visible: true, locked: false, affectsScale: true, source: "USER_PROVIDED", residual: null, residualStatus: "UNASSESSED", manualOverride: false };
}

for (const heightCm of [160, 175, 190]) test(`golden neutral human ${heightCm} cm has exact canonical stature and symmetric landmarks`, () => {
  const canonical = getCanonicalHuman(profileFromHeight(`H${heightCm}`, heightCm));
  const pose = buildCanonicalPose(canonical, "STANDING");
  assert.equal(canonical.unit, "cm");
  assert.equal(canonical.dimensions.statureCm, heightCm);
  assert.ok(Math.abs(pose.joints.head.y - heightCm) < 1e-9);
  assert.ok(Math.abs(pose.joints.leftShoulder.x + pose.joints.rightShoulder.x) < 1e-9);
  assert.ok(Math.abs(pose.joints.leftHip.x + pose.joints.rightHip.x) < 1e-9);
  assert.deepEqual(validateCanonicalPose(canonical, pose).violations, []);
});

test("175 cm canonical dimensions use explicit technical provenance", () => {
  const canonical = getCanonicalHuman(profileFromHeight("Operator", 175));
  assert.equal(canonical.provenance.upperArm, "DERIVED_DISPLAY_APPROXIMATION");
  assert.equal(Number(canonical.dimensions.upperArmLengthCm.toFixed(3)), 32.55);
  assert.equal(Number(canonical.dimensions.forearmLengthCm.toFixed(3)), 27.475);
  assert.equal(Number(canonical.dimensions.thighLengthCm.toFixed(3)), 42.875);
  assert.equal(Number(canonical.dimensions.lowerLegLengthCm.toFixed(3)), 43.05);
});

for (const posture of ["STANDING", "SEATED", "REACHING", "FORWARD_LEAN", "WORK_SURFACE", "ONE_HANDED", "TWO_HANDED"]) test(`canonical pose ${posture} remains finite and connected`, () => {
  const canonical = getCanonicalHuman(profileFromHeight("Operator", 175));
  const pose = buildCanonicalPose(canonical, posture);
  assert.ok(Object.values(pose.joints).every((point) => [point.x, point.y, point.z].every(Number.isFinite)));
  assert.equal(validateCanonicalPose(canonical, pose).valid, true);
});

test("1000 two-bone IK targets remain finite and preserve fixed lengths", () => {
  for (let index = 0; index < 1000; index += 1) {
    const angle = index * 2.3999632297, radius = (index % 73) * 1.7;
    const result = solveTwoBoneIk({ x: 0, y: 0 }, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius }, 32.55, 27.475, index % 2 ? 1 : -1);
    assert.ok([result.joint.x, result.joint.y, result.end.x, result.end.y].every(Number.isFinite));
    assert.ok(Math.abs(Math.hypot(result.joint.x, result.joint.y) - 32.55) < 1e-6);
    assert.ok(Math.abs(Math.hypot(result.end.x - result.joint.x, result.end.y - result.joint.y) - 27.475) < 1e-5);
  }
});

test("physical height stays 175 cm at 50 scene positions while projected pixels vary", () => {
  const scene = emptySceneState();
  scene.calibration.references = [reference("a", .1, .88, 420, 100), reference("b", .85, .78, 350, 100), reference("c", .55, .25, 180, 100)];
  scene.calibration = rebuildPerspectiveField(scene.calibration);
  const profile = profileFromHeight("Operator", 175), pixels = [];
  for (let index = 0; index < 50; index += 1) {
    const point = { x: .1 + (index % 10) * .08, y: .25 + Math.floor(index / 10) * .14 };
    const scale = estimateLocalScale(scene.calibration, point, WIDTH, HEIGHT); assert.ok(scale);
    const pose = buildAnthropometricPose(profile, point, scale.pixelsPerCm, WIDTH, HEIGHT, "STANDING", index * 7.2);
    assert.ok(Math.abs(renderedHeightPixels(pose, HEIGHT) / scale.pixelsPerCm - 175) < 1e-6);
    pixels.push(renderedHeightPixels(pose, HEIGHT));
  }
  assert.ok(Math.max(...pixels) > Math.min(...pixels));
});

test("projected human reports calibration and ground fallback states", () => {
  const scene = emptySceneState(), human = createHuman("Operator", "#f97316");
  assert.equal(getGroundPlaneStatus(scene.calibration), "GROUND_NONE");
  scene.calibration.floorBaseline = { start: { x: 0, y: .9 }, end: { x: 1, y: .9 } };
  assert.equal(getGroundPlaneStatus(scene.calibration), "GROUND_BASIC");
  const projected = getProjectedHuman({ human, calibration: scene.calibration, contactPoint: { x: .5, y: .9 }, imageWidth: WIDTH, imageHeight: HEIGHT });
  assert.equal(projected.physicalHeightCm, 175);
  assert.equal(projected.placementQuality, "UNVERIFIED");
});

test("interactive wrist target cannot stretch arm segments", () => {
  let human = createHuman("Operator", "#f97316");
  const shoulder = human.pose.joints.leftShoulder;
  human = moveHumanJointWithConstraints(human, "leftWrist", { x: shoulder.x + 2, y: shoulder.y - 2 }, 3, WIDTH, HEIGHT);
  assert.ok(Math.abs(segmentLengthPixels(human, "leftShoulder", "leftElbow", WIDTH, HEIGHT) - human.constraints.upperArm.fixedLengthCm * 3) < 1e-6);
  assert.ok(Math.abs(segmentLengthPixels(human, "leftElbow", "leftWrist", WIDTH, HEIGHT) - human.constraints.forearm.fixedLengthCm * 3) < 1e-6);
  assert.equal(human.pose.reachState.leftArm, "OUT_OF_REACH");
});

test("old schema 1.2 human is normalized into Digital Human v1 without losing placement", () => {
  const scene = emptySceneState(), original = createHuman("Legacy", "#06b6d4");
  const contact = { ...original.placement.contactPoint };
  const legacy = structuredClone({ ...scene, humans: [original], selectedHumanId: original.id });
  delete legacy.humans[0].modelVersion;
  delete legacy.humans[0].profile.physicalDimensions;
  for (const key of Object.keys(legacy.humans[0].profile.segmentProvenance)) legacy.humans[0].profile.segmentProvenance[key] = "DERIVED_APPROXIMATION";
  const normalized = normalizeSceneState(legacy);
  assert.equal(normalized.humans[0].modelVersion, "digital-human-v1");
  assert.equal(normalized.humans[0].profile.segmentProvenance.upperArm, "DERIVED_DISPLAY_APPROXIMATION");
  assert.deepEqual(normalized.humans[0].placement.contactPoint, contact);
  assert.equal(validateSceneState(normalized), true);
});
