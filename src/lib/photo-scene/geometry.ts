import type { HumanJointName, HumanPose, LimbReachState, NormalizedPoint, SceneCalibration, SceneHuman } from "../../types/photo-scene";
import { estimateLocalScale } from "./calibration.ts";
import { mapPoints, syncPlacement } from "./anthropometry.ts";

export function distance(a: NormalizedPoint, b: NormalizedPoint) { return Math.hypot(b.x - a.x, b.y - a.y); }
export type IkResult = { joint: NormalizedPoint; end: NormalizedPoint; target: NormalizedPoint; reachState: LimbReachState; targetDistance: number; maximumReach: number; bend: 1 | -1 };

export function solveTwoBoneIk(root: NormalizedPoint, target: NormalizedPoint, firstLength: number, secondLength: number, bend: 1 | -1 = 1, comfortRatio = .82): IkResult {
  const safeFirst = Math.max(1e-8, firstLength), safeSecond = Math.max(1e-8, secondLength);
  const dx = target.x - root.x, dy = target.y - root.y, targetDistance = Math.hypot(dx, dy);
  const maximum = safeFirst + safeSecond, minimum = Math.abs(safeFirst - safeSecond) + 1e-8;
  const clamped = Math.min(maximum - 1e-8, Math.max(minimum, targetDistance || minimum));
  const base = Math.atan2(dy, dx), cosine = clampCosine((safeFirst ** 2 + clamped ** 2 - safeSecond ** 2) / (2 * safeFirst * clamped));
  const angle = base + bend * Math.acos(cosine);
  const joint = { x: root.x + Math.cos(angle) * safeFirst, y: root.y + Math.sin(angle) * safeFirst };
  const endDistance = Math.min(maximum, Math.max(minimum, targetDistance || minimum));
  const direction = targetDistance > 1e-8 ? { x: dx / targetDistance, y: dy / targetDistance } : { x: Math.cos(base), y: Math.sin(base) };
  const end = { x: root.x + direction.x * endDistance, y: root.y + direction.y * endDistance };
  const reachState: LimbReachState = targetDistance > maximum + 1e-7 ? "OUT_OF_REACH" : targetDistance < minimum ? "SOFT_LIMIT" : targetDistance > maximum * comfortRatio ? "COMFORT_EXCEEDED" : "NATURAL";
  return { joint, end, target, targetDistance, maximumReach: maximum, reachState, bend };
}

export function moveHumanJointWithConstraints(human: SceneHuman, joint: HumanJointName, target: NormalizedPoint, pixelsPerCm: number, imageWidth: number, imageHeight: number): SceneHuman {
  const pose = human.pose, joints = { ...pose.joints }, reachState = { ...pose.reachState }, bendPreference = { ...pose.bendPreference };
  const pixel = (point: NormalizedPoint) => ({ x: point.x * imageWidth, y: point.y * imageHeight });
  const normalized = (point: NormalizedPoint) => ({ x: point.x / imageWidth, y: point.y / imageHeight });
  const targetPx = pixel(target), px = Math.max(.05, pixelsPerCm);
  if (["leftWrist", "rightWrist", "leftHand", "rightHand"].includes(joint)) {
    const side = joint.startsWith("left") ? "left" : "right", shoulderName = `${side}Shoulder` as HumanJointName;
    const elbowName = `${side}Elbow` as HumanJointName, wristName = `${side}Wrist` as HumanJointName, handName = `${side}Hand` as HumanJointName;
    const shoulder = pixel(joints[shoulderName]), upper = human.constraints.upperArm.fixedLengthCm * px, forearm = human.constraints.forearm.fixedLengthCm * px, hand = human.constraints.hand.fixedLengthCm * px;
    const direction = unitVector(shoulder, targetPx), wristTarget = joint.endsWith("Hand") ? { x: targetPx.x - direction.x * hand, y: targetPx.y - direction.y * hand } : targetPx;
    const key = `${side}Arm` as "leftArm" | "rightArm", bend = stableBend(shoulder, wristTarget, pixel(joints[elbowName]), bendPreference[key]);
    const result = solveTwoBoneIk(shoulder, wristTarget, upper, forearm, bend);
    joints[elbowName] = normalized(result.joint); joints[wristName] = normalized(result.end);
    const handEnd = { x: result.end.x + direction.x * hand, y: result.end.y + direction.y * hand };
    joints[handName] = normalized(handEnd); bendPreference[key] = bend;
    const totalDistance = distance(shoulder, targetPx), maximum = upper + forearm + (joint.endsWith("Hand") ? hand : 0);
    reachState[key] = totalDistance > maximum + 1e-7 ? "OUT_OF_REACH" : totalDistance > maximum * .82 ? "COMFORT_EXCEEDED" : result.reachState;
  } else if (["leftAnkle", "rightAnkle", "leftFoot", "rightFoot"].includes(joint)) {
    const side = joint.startsWith("left") ? "left" : "right", hipName = `${side}Hip` as HumanJointName;
    const kneeName = `${side}Knee` as HumanJointName, ankleName = `${side}Ankle` as HumanJointName, footName = `${side}Foot` as HumanJointName;
    const hip = pixel(joints[hipName]), thigh = human.constraints.thigh.fixedLengthCm * px, lower = human.constraints.lowerLeg.fixedLengthCm * px, foot = human.constraints.foot.fixedLengthCm * px;
    const key = `${side}Leg` as "leftLeg" | "rightLeg", ankleTarget = joint.endsWith("Foot") ? { x: targetPx.x - foot, y: targetPx.y } : targetPx;
    const bend = stableBend(hip, ankleTarget, pixel(joints[kneeName]), bendPreference[key]), result = solveTwoBoneIk(hip, ankleTarget, thigh, lower, bend, .9);
    joints[kneeName] = normalized(result.joint); joints[ankleName] = normalized(result.end); joints[footName] = normalized({ x: result.end.x + foot, y: result.end.y });
    bendPreference[key] = bend; reachState[key] = result.reachState;
  }
  const nextPose: HumanPose = { ...pose, preset: "CUSTOM", joints, reachState, bendPreference };
  const next = { ...human, pose: nextPose, placement: syncPlacement(nextPose, human.placement) };
  return Object.values(nextPose.joints).every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)) ? next : human;
}

export function validateProjectedHuman(human: SceneHuman, pixelsPerCm: number, imageWidth: number, imageHeight: number) {
  const violations: string[] = [];
  if (Object.values(human.pose.joints).some((point) => !Number.isFinite(point.x) || !Number.isFinite(point.y))) violations.push("non_finite_joint");
  const expected: [string, HumanJointName, HumanJointName, number][] = [
    ["left_upper_arm", "leftShoulder", "leftElbow", human.constraints.upperArm.fixedLengthCm],
    ["right_upper_arm", "rightShoulder", "rightElbow", human.constraints.upperArm.fixedLengthCm],
    ["left_forearm", "leftElbow", "leftWrist", human.constraints.forearm.fixedLengthCm],
    ["right_forearm", "rightElbow", "rightWrist", human.constraints.forearm.fixedLengthCm],
    ["left_thigh", "leftHip", "leftKnee", human.constraints.thigh.fixedLengthCm],
    ["right_thigh", "rightHip", "rightKnee", human.constraints.thigh.fixedLengthCm],
    ["left_lower_leg", "leftKnee", "leftAnkle", human.constraints.lowerLeg.fixedLengthCm],
    ["right_lower_leg", "rightKnee", "rightAnkle", human.constraints.lowerLeg.fixedLengthCm],
  ];
  for (const [name, parent, child, centimeters] of expected) {
    const actual = segmentLengthPixels(human, parent, child, imageWidth, imageHeight);
    if (Math.abs(actual - centimeters * pixelsPerCm) > Math.max(.05, centimeters * pixelsPerCm * .002)) violations.push(`${name}_length`);
  }
  return { valid: violations.length === 0, violations };
}

export function moveHumanRootUniform(human: SceneHuman, standingPoint: NormalizedPoint, nextScale: number | null, imageWidth: number, imageHeight: number): SceneHuman {
  const oldContact = human.placement.contactPoint, oldScale = human.placement.lastScalePxPerCm;
  const ratio = nextScale && oldScale ? clamp(nextScale / oldScale, .2, 5) : 1;
  const oldPx = { x: oldContact.x * imageWidth, y: oldContact.y * imageHeight }, nextPx = { x: standingPoint.x * imageWidth, y: standingPoint.y * imageHeight };
  const joints = mapPoints(human.pose.joints, (point) => {
    const pointPx = { x: point.x * imageWidth, y: point.y * imageHeight };
    return { x: (nextPx.x + (pointPx.x - oldPx.x) * ratio) / imageWidth, y: (nextPx.y + (pointPx.y - oldPx.y) * ratio) / imageHeight };
  });
  const pose = { ...human.pose, joints };
  return { ...human, pose, placement: syncPlacement(pose, { ...human.placement, lastScalePxPerCm: nextScale ?? oldScale }) };
}

export function localPixelsPerCentimeter(calibration: SceneCalibration, position: NormalizedPoint, imageHeight: number, imageWidth = imageHeight) { return estimateLocalScale(calibration, position, imageWidth, imageHeight)?.pixelsPerCm ?? null; }

/** Compatibility wrapper used by legacy tests; v0.3 UI uses constraint-aware human IK above. */
export function moveJointWithIk(pose: HumanPose, joint: HumanJointName, target: NormalizedPoint, aspectRatio = 1): HumanPose {
  const joints = { ...pose.joints }, metric = (point: NormalizedPoint) => ({ x: point.x * aspectRatio, y: point.y }), screen = (point: NormalizedPoint) => ({ x: point.x / aspectRatio, y: point.y });
  if (joint === "leftWrist" || joint === "rightWrist") { const side = joint.startsWith("left") ? "left" : "right", shoulder = joints[`${side}Shoulder` as HumanJointName], elbow = `${side}Elbow` as HumanJointName; const result = solveTwoBoneIk(metric(shoulder), metric(target), distance(metric(shoulder), metric(joints[elbow])), distance(metric(joints[elbow]), metric(joints[joint])), pose.bendPreference[`${side}Arm` as "leftArm" | "rightArm"]); joints[elbow] = screen(result.joint); joints[joint] = screen(result.end); }
  return { ...pose, joints };
}

export function segmentLengthPixels(human: SceneHuman, parent: HumanJointName, child: HumanJointName, width: number, height: number) { return Math.hypot((human.pose.joints[child].x - human.pose.joints[parent].x) * width, (human.pose.joints[child].y - human.pose.joints[parent].y) * height); }
export function clampCosine(value: number) { return Math.max(-1, Math.min(1, Number.isFinite(value) ? value : 1)); }
function stableBend(_root: NormalizedPoint, _target: NormalizedPoint, _previousJoint: NormalizedPoint, previous: 1 | -1): 1 | -1 { return previous; }
function unitVector(from: NormalizedPoint, to: NormalizedPoint) { const length = Math.max(1e-8, distance(from, to)); return { x: (to.x - from.x) / length, y: (to.y - from.y) / length }; }
function clamp(value: number, min: number, max: number) { return Math.max(min, Math.min(max, value)); }
