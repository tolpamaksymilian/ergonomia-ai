import type { HumanJointName, HumanPosture, LimbReachState } from "../../types/photo-scene";
import type { CanonicalHuman, CanonicalPointCm } from "./human-physical-model.ts";

export type CanonicalPose = {
  unit: "cm";
  posture: HumanPosture;
  joints: Record<HumanJointName, CanonicalPointCm>;
  reachState: { leftArm: LimbReachState; rightArm: LimbReachState; leftLeg: LimbReachState; rightLeg: LimbReachState };
};

export type CanonicalValidation = { valid: boolean; violations: string[] };

export function buildCanonicalPose(human: CanonicalHuman, posture: HumanPosture = "STANDING"): CanonicalPose {
  const d = human.dimensions;
  const h = d.statureCm;
  const seated = posture === "SEATED";
  const reaching = ["REACHING", "WORK_SURFACE", "TWO_HANDED"].includes(posture);
  const oneHanded = posture === "ONE_HANDED";
  const forwardLean = posture === "FORWARD_LEAN" ? h * 0.055 : 0;
  const hipY = seated ? h * 0.40 : h * 0.53;
  const shoulderY = hipY + d.torsoLengthCm;
  const neckY = Math.min(h - d.headHeightCm, shoulderY + d.neckLengthCm + h * 0.012);
  const headTopY = seated ? neckY + d.headHeightCm : h;
  const shoulderHalf = d.shoulderWidthCm / 2;
  const hipHalf = d.pelvisWidthCm / 2;
  const joints = {} as Record<HumanJointName, CanonicalPointCm>;
  joints.pelvisRoot = p(0, hipY, seated ? -h * 0.015 : 0);
  joints.leftHip = p(-hipHalf, hipY, 0); joints.rightHip = p(hipHalf, hipY, 0);
  joints.neck = p(0, neckY, forwardLean);
  joints.head = p(0, headTopY, forwardLean * 1.15);
  joints.leftShoulder = p(-shoulderHalf, shoulderY, forwardLean);
  joints.rightShoulder = p(shoulderHalf, shoulderY, forwardLean);

  const armLeft = reaching || oneHanded ? { upper: 18, lower: 4 } : { upper: -98, lower: -86 };
  const armRight = reaching ? { upper: 162, lower: 176 } : { upper: -82, lower: -94 };
  assignArm(joints, "left", d.upperArmLengthCm, d.forearmLengthCm, d.handLengthCm, armLeft.upper, armLeft.lower);
  assignArm(joints, "right", d.upperArmLengthCm, d.forearmLengthCm, d.handLengthCm, armRight.upper, armRight.lower);

  if (seated) {
    assignLeg(joints, "left", d.thighLengthCm, d.lowerLegLengthCm, d.footLengthCm, -8, -90);
    assignLeg(joints, "right", d.thighLengthCm, d.lowerLegLengthCm, d.footLengthCm, 8, -90);
  } else {
    assignLeg(joints, "left", d.thighLengthCm, d.lowerLegLengthCm, d.footLengthCm, -92, -88);
    assignLeg(joints, "right", d.thighLengthCm, d.lowerLegLengthCm, d.footLengthCm, -88, -92);
    const floorOffset = Math.min(joints.leftFoot.y, joints.rightFoot.y);
    for (const point of Object.values(joints)) point.y -= floorOffset;
    joints.head.y = h;
  }
  const pose: CanonicalPose = {
    unit: "cm", posture, joints,
    reachState: { leftArm: "NATURAL", rightArm: "NATURAL", leftLeg: "NATURAL", rightLeg: "NATURAL" },
  };
  return pose;
}

export function validateCanonicalPose(human: CanonicalHuman, pose: CanonicalPose, toleranceCm = 0.05): CanonicalValidation {
  const d = human.dimensions;
  const checks: [string, HumanJointName, HumanJointName, number][] = [
    ["left_upper_arm", "leftShoulder", "leftElbow", d.upperArmLengthCm],
    ["right_upper_arm", "rightShoulder", "rightElbow", d.upperArmLengthCm],
    ["left_forearm", "leftElbow", "leftWrist", d.forearmLengthCm],
    ["right_forearm", "rightElbow", "rightWrist", d.forearmLengthCm],
    ["left_thigh", "leftHip", "leftKnee", d.thighLengthCm],
    ["right_thigh", "rightHip", "rightKnee", d.thighLengthCm],
    ["left_lower_leg", "leftKnee", "leftAnkle", d.lowerLegLengthCm],
    ["right_lower_leg", "rightKnee", "rightAnkle", d.lowerLegLengthCm],
  ];
  const violations: string[] = [];
  if (Object.values(pose.joints).some((point) => ![point.x, point.y, point.z].every(Number.isFinite))) violations.push("non_finite_joint");
  for (const [name, a, b, expected] of checks) if (Math.abs(distance3(pose.joints[a], pose.joints[b]) - expected) > toleranceCm) violations.push(`${name}_length`);
  if (Math.abs(pose.joints.leftShoulder.y - pose.joints.rightShoulder.y) > toleranceCm) violations.push("shoulder_asymmetry");
  if (Math.abs(pose.joints.leftHip.y - pose.joints.rightHip.y) > toleranceCm) violations.push("hip_asymmetry");
  return { valid: violations.length === 0, violations };
}

function assignArm(joints: Record<HumanJointName, CanonicalPointCm>, side: "left" | "right", upper: number, forearm: number, hand: number, upperDeg: number, lowerDeg: number) {
  const shoulder = joints[`${side}Shoulder`];
  const elbow = fromAngle(shoulder, upper, upperDeg);
  const wrist = fromAngle(elbow, forearm, lowerDeg);
  const handEnd = fromAngle(wrist, hand, lowerDeg);
  joints[`${side}Elbow`] = elbow; joints[`${side}Wrist`] = wrist; joints[`${side}Hand`] = handEnd;
}
function assignLeg(joints: Record<HumanJointName, CanonicalPointCm>, side: "left" | "right", thigh: number, lower: number, foot: number, thighDeg: number, lowerDeg: number) {
  const hip = joints[`${side}Hip`];
  const knee = fromAngle(hip, thigh, thighDeg);
  const ankle = fromAngle(knee, lower, lowerDeg);
  const sign = side === "left" ? -1 : 1;
  joints[`${side}Knee`] = knee; joints[`${side}Ankle`] = ankle; joints[`${side}Foot`] = p(ankle.x + sign * foot * 0.08, ankle.y, foot * 0.92);
}
function fromAngle(origin: CanonicalPointCm, length: number, degrees: number): CanonicalPointCm {
  const angle = degrees * Math.PI / 180;
  return p(origin.x + Math.cos(angle) * length, origin.y + Math.sin(angle) * length, origin.z);
}
function p(x: number, y: number, z: number): CanonicalPointCm { return { x, y, z }; }
function distance3(a: CanonicalPointCm, b: CanonicalPointCm) { return Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z); }
