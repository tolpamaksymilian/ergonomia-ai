import type { HumanJointName, HumanPose, NormalizedPoint, SceneCalibration } from "../../types/photo-scene";

export function distance(a: NormalizedPoint, b: NormalizedPoint) {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

export function solveTwoBoneIk(
  root: NormalizedPoint,
  target: NormalizedPoint,
  firstLength: number,
  secondLength: number,
  bend: 1 | -1 = 1,
): { joint: NormalizedPoint; end: NormalizedPoint } {
  const dx = target.x - root.x;
  const dy = target.y - root.y;
  const targetDistance = Math.hypot(dx, dy);
  const maximum = Math.max(0.000001, firstLength + secondLength);
  const minimum = Math.abs(firstLength - secondLength) + 0.000001;
  const clamped = Math.min(maximum, Math.max(minimum, targetDistance || minimum));
  const base = Math.atan2(dy, dx);
  const cosine = Math.max(-1, Math.min(1, (firstLength ** 2 + clamped ** 2 - secondLength ** 2) / (2 * firstLength * clamped)));
  const angle = base + bend * Math.acos(cosine);
  const joint = { x: root.x + Math.cos(angle) * firstLength, y: root.y + Math.sin(angle) * firstLength };
  const scale = targetDistance > maximum ? maximum / targetDistance : 1;
  const end = targetDistance === 0 ? { x: root.x + maximum, y: root.y } : { x: root.x + dx * scale, y: root.y + dy * scale };
  return { joint, end };
}

export function localPixelsPerCentimeter(calibration: SceneCalibration, position: NormalizedPoint, imageHeight: number): number | null {
  const valid = calibration.anchors.filter((anchor) => anchor.realDistanceCm > 0 && anchor.pixelDistance > 0);
  if (!valid.length || imageHeight <= 0) return null;
  const ranked = [...valid].sort((a, b) => {
    const am = { x: (a.lower.x + a.upper.x) / 2, y: (a.lower.y + a.upper.y) / 2 };
    const bm = { x: (b.lower.x + b.upper.x) / 2, y: (b.lower.y + b.upper.y) / 2 };
    return distance(am, position) - distance(bm, position);
  });
  const nearest = ranked.slice(0, Math.min(3, ranked.length));
  let totalWeight = 0;
  let total = 0;
  for (const anchor of nearest) {
    const middle = { x: (anchor.lower.x + anchor.upper.x) / 2, y: (anchor.lower.y + anchor.upper.y) / 2 };
    const weight = 1 / Math.max(0.02, distance(middle, position));
    totalWeight += weight;
    total += weight * (anchor.pixelDistance / anchor.realDistanceCm);
  }
  return totalWeight ? total / totalWeight : null;
}

export function moveJointWithIk(pose: HumanPose, joint: HumanJointName, target: NormalizedPoint, aspectRatio = 1): HumanPose {
  const joints = { ...pose.joints };
  const toMetric = (point: NormalizedPoint) => ({ x: point.x * aspectRatio, y: point.y });
  const fromMetric = (point: NormalizedPoint) => ({ x: point.x / aspectRatio, y: point.y });
  if (joint === "leftWrist" || joint === "rightWrist") {
    const side = joint.startsWith("left") ? "left" : "right";
    const shoulder = joints[`${side}Shoulder` as HumanJointName];
    const elbowName = `${side}Elbow` as HumanJointName;
    const wristName = `${side}Wrist` as HumanJointName;
    const result = solveTwoBoneIk(toMetric(shoulder), toMetric(target), distance(toMetric(shoulder), toMetric(joints[elbowName])), distance(toMetric(joints[elbowName]), toMetric(joints[wristName])), side === "left" ? 1 : -1);
    joints[elbowName] = fromMetric(result.joint);
    joints[wristName] = fromMetric(result.end);
  } else if (joint === "leftAnkle" || joint === "rightAnkle") {
    const side = joint.startsWith("left") ? "left" : "right";
    const hip = joints[`${side}Hip` as HumanJointName];
    const kneeName = `${side}Knee` as HumanJointName;
    const ankleName = `${side}Ankle` as HumanJointName;
    const result = solveTwoBoneIk(toMetric(hip), toMetric(target), distance(toMetric(hip), toMetric(joints[kneeName])), distance(toMetric(joints[kneeName]), toMetric(joints[ankleName])), side === "left" ? -1 : 1);
    joints[kneeName] = fromMetric(result.joint);
    joints[ankleName] = fromMetric(result.end);
  } else {
    joints[joint] = target;
  }
  return { ...pose, preset: "CUSTOM", joints };
}
