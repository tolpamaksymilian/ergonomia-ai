import type { HumanPose, HumanPosture, HumanProfile, HumanProfilePreset, NormalizedPoint, SceneHuman } from "../../types/photo-scene";

export const HUMAN_PRESETS: Record<Exclude<HumanProfilePreset, "CUSTOM">, { label: string; heightCm: number }> = {
  SHORT: { label: "Niski", heightCm: 160 }, MEDIUM: { label: "Średni", heightCm: 175 }, TALL: { label: "Wysoki", heightCm: 190 },
};

export function profileFromHeight(name: string, heightCm: number, preset: HumanProfilePreset = "CUSTOM"): HumanProfile {
  const h = Math.max(120, Math.min(220, heightCm));
  return {
    name, preset, heightCm: h, armSpanCm: h, functionalReachCm: h * 0.40, maximumReachCm: h * 0.47,
    shoulderHeightCm: h * 0.818, elbowHeightCm: h * 0.63, eyeHeightCm: h * 0.936,
    hipHeightCm: h * 0.53, upperArmLengthCm: h * 0.186, forearmLengthCm: h * 0.146,
    handLengthCm: h * 0.108, thighLengthCm: h * 0.245, lowerLegLengthCm: h * 0.246,
    geometrySource: "ANTHROPOMETRIC_ESTIMATE",
  };
}

export function createHuman(name: string, color: string, preset: HumanProfilePreset = "MEDIUM"): SceneHuman {
  const height = preset === "CUSTOM" ? 175 : HUMAN_PRESETS[preset].heightCm;
  const pose = defaultPose("STANDING");
  return {
    id: crypto.randomUUID(), name, color, profile: profileFromHeight(name, height, preset), pose,
    placement: { contactPoint: { x: .5, y: .9 }, floorPinned: false, attachedObjectId: null, attachmentMode: "NONE" },
    visible: true, locked: false,
  };
}

export function defaultPose(preset: HumanPosture): HumanPose {
  const seated = preset === "SEATED";
  const reach = ["REACHING", "WORK_SURFACE", "TWO_HANDED"].includes(preset);
  const lean = preset === "FORWARD_LEAN" ? .025 : 0;
  const one = preset === "ONE_HANDED";
  return { preset, mirrored: false, scaleLocked: true, reachState: { leftArm: "NATURAL", rightArm: "NATURAL", leftLeg: "NATURAL", rightLeg: "NATURAL" }, joints: {
    head:{x:.5+lean,y:.15}, neck:{x:.5+lean,y:.22}, leftShoulder:{x:.465+lean,y:.25}, rightShoulder:{x:.535+lean,y:.25},
    leftElbow:reach||one?{x:.40,y:.31}:{x:.44,y:.38}, rightElbow:reach?{x:.60,y:.31}:{x:.56,y:.38},
    leftWrist:reach||one?{x:.33,y:.31}:{x:.435,y:.49}, rightWrist:reach?{x:.67,y:.31}:{x:.565,y:.49},
    leftHand:reach||one?{x:.31,y:.31}:{x:.433,y:.525}, rightHand:reach?{x:.69,y:.31}:{x:.567,y:.525},
    leftHip:{x:.475,y:.49}, rightHip:{x:.525,y:.49},
    leftKnee:seated?{x:.40,y:.58}:{x:.477,y:.69}, rightKnee:seated?{x:.60,y:.58}:{x:.523,y:.69},
    leftAnkle:seated?{x:.40,y:.78}:{x:.47,y:.89}, rightAnkle:seated?{x:.60,y:.78}:{x:.53,y:.89},
    leftFoot:seated?{x:.43,y:.80}:{x:.49,y:.91}, rightFoot:seated?{x:.63,y:.80}:{x:.55,y:.91},
  }};
}

export function resetHumanPose(human: SceneHuman, preset: HumanPosture = human.pose.preset): SceneHuman {
  const fresh = defaultPose(preset === "CUSTOM" ? "STANDING" : preset);
  const oldContact = contactPoint(human.pose);
  const newContact = contactPoint(fresh);
  const dx = oldContact.x - newContact.x, dy = oldContact.y - newContact.y;
  return { ...human, pose: { ...fresh, joints: mapPoints(fresh.joints, (p) => ({ x: p.x + dx, y: p.y + dy })) } };
}

export function contactPoint(pose: HumanPose): NormalizedPoint {
  return { x: (pose.joints.leftFoot.x + pose.joints.rightFoot.x) / 2, y: Math.max(pose.joints.leftFoot.y, pose.joints.rightFoot.y) };
}

export function mapPoints<T extends Record<string, NormalizedPoint>>(points: T, fn: (point: NormalizedPoint) => NormalizedPoint): T {
  return Object.fromEntries(Object.entries(points).map(([key, value]) => [key, fn(value)])) as T;
}
