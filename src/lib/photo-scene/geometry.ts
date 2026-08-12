import type { HumanJointName, HumanPose, LimbReachState, NormalizedPoint, SceneCalibration } from "../../types/photo-scene";
import { estimateLocalScale } from "./calibration.ts";

export function distance(a: NormalizedPoint, b: NormalizedPoint) { return Math.hypot(b.x - a.x, b.y - a.y); }

export type IkResult = { joint: NormalizedPoint; end: NormalizedPoint; target: NormalizedPoint; reachState: LimbReachState; targetDistance: number; maximumReach: number };

export function solveTwoBoneIk(root: NormalizedPoint, target: NormalizedPoint, firstLength: number, secondLength: number, bend: 1 | -1 = 1, comfortRatio = .82): IkResult {
  const dx = target.x - root.x, dy = target.y - root.y;
  const targetDistance = Math.hypot(dx, dy);
  const maximum = Math.max(.000001, firstLength + secondLength);
  const minimum = Math.abs(firstLength - secondLength) + .000001;
  const clamped = Math.min(maximum - .000001, Math.max(minimum, targetDistance || minimum));
  const base = Math.atan2(dy, dx);
  const cosine = Math.max(-1, Math.min(1, (firstLength ** 2 + clamped ** 2 - secondLength ** 2) / (2 * firstLength * clamped)));
  const angle = base + bend * Math.acos(cosine);
  const joint = { x: root.x + Math.cos(angle) * firstLength, y: root.y + Math.sin(angle) * firstLength };
  const scale = targetDistance > maximum ? maximum / targetDistance : 1;
  const end = targetDistance === 0 ? { x: root.x + maximum, y: root.y } : { x: root.x + dx * scale, y: root.y + dy * scale };
  return { joint, end, target, targetDistance, maximumReach: maximum, reachState: targetDistance > maximum ? "OUT_OF_REACH" : targetDistance > maximum * comfortRatio ? "COMFORT_EXCEEDED" : "NATURAL" };
}

export function localPixelsPerCentimeter(calibration: SceneCalibration, position: NormalizedPoint, imageHeight: number, imageWidth = imageHeight): number | null {
  return estimateLocalScale(calibration, position, imageWidth, imageHeight)?.pixelsPerCm ?? null;
}

export function moveJointWithIk(pose: HumanPose, joint: HumanJointName, target: NormalizedPoint, aspectRatio = 1): HumanPose {
  const joints = { ...pose.joints }, reachState = { ...pose.reachState };
  const metric = (point: NormalizedPoint) => ({ x: point.x * aspectRatio, y: point.y });
  const screen = (point: NormalizedPoint) => ({ x: point.x / aspectRatio, y: point.y });
  if (["leftWrist", "rightWrist", "leftHand", "rightHand"].includes(joint)) {
    const side = joint.startsWith("left") ? "left" : "right";
    const shoulder = joints[`${side}Shoulder` as HumanJointName], elbowName = `${side}Elbow` as HumanJointName, wristName = `${side}Wrist` as HumanJointName, handName = `${side}Hand` as HumanJointName;
    const upper = distance(metric(shoulder), metric(joints[elbowName])), lower = distance(metric(joints[elbowName]), metric(joints[wristName]));
    const handVector = { x: joints[handName].x - joints[wristName].x, y: joints[handName].y - joints[wristName].y };
    const handLength = distance(metric(joints[wristName]), metric(joints[handName]));
    const shoulderMetric = metric(shoulder), targetMetric = metric(target);
    const directionLength = Math.max(.000001, distance(shoulderMetric, targetMetric));
    const direction = { x: (targetMetric.x - shoulderMetric.x) / directionLength, y: (targetMetric.y - shoulderMetric.y) / directionLength };
    const wristTarget = joint.endsWith("Hand") ? { x: targetMetric.x - direction.x * handLength, y: targetMetric.y - direction.y * handLength } : targetMetric;
    const result = solveTwoBoneIk(shoulderMetric, wristTarget, upper, lower, side === "left" ? 1 : -1);
    joints[elbowName] = screen(result.joint); joints[wristName] = screen(result.end);
    joints[handName] = joint.endsWith("Hand") ? screen({ x: result.end.x + direction.x * handLength, y: result.end.y + direction.y * handLength }) : { x: joints[wristName].x + handVector.x, y: joints[wristName].y + handVector.y };
    const totalDistance = distance(shoulderMetric, targetMetric), maximum = upper + lower + (joint.endsWith("Hand") ? handLength : 0);
    reachState[`${side}Arm` as "leftArm" | "rightArm"] = totalDistance > maximum ? "OUT_OF_REACH" : totalDistance > maximum * .82 ? "COMFORT_EXCEEDED" : "NATURAL";
  } else if (["leftAnkle", "rightAnkle", "leftFoot", "rightFoot"].includes(joint)) {
    const side = joint.startsWith("left") ? "left" : "right";
    const hip = joints[`${side}Hip` as HumanJointName], kneeName = `${side}Knee` as HumanJointName, ankleName = `${side}Ankle` as HumanJointName, footName = `${side}Foot` as HumanJointName;
    const result = solveTwoBoneIk(metric(hip), metric(target), distance(metric(hip), metric(joints[kneeName])), distance(metric(joints[kneeName]), metric(joints[ankleName])), side === "left" ? -1 : 1, .9);
    joints[kneeName] = screen(result.joint); joints[ankleName] = screen(result.end); joints[footName] = { ...joints[ankleName], x: joints[ankleName].x + (side === "left" ? .018 : .022) };
    reachState[`${side}Leg` as "leftLeg" | "rightLeg"] = result.reachState;
  } else joints[joint] = target;
  return { ...pose, preset: "CUSTOM", joints, reachState };
}
