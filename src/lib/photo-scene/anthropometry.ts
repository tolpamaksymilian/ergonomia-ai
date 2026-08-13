import type {
  HumanConstraintGraph, HumanPose, HumanPosture, HumanProfile, HumanProfilePreset,
  HumanSegmentKey, NormalizedPoint, SceneHuman, SegmentProvenance,
} from "../../types/photo-scene";
import { createAnthropometricProfile, derivePhysicalDimensions, normalizePhysicalProfile } from "./human-physical-model.ts";
import { getProjectedHuman } from "./human-projection.ts";

export const HUMAN_PRESETS: Record<Exclude<HumanProfilePreset, "CUSTOM">, { label: string; heightCm: number }> = {
  SHORT: { label: "Niski", heightCm: 160 }, MEDIUM: { label: "Średni", heightCm: 175 }, TALL: { label: "Wysoki", heightCm: 190 },
};

export function profileFromHeight(name: string, heightCm: number, preset: HumanProfilePreset = "CUSTOM"): HumanProfile {
  return createAnthropometricProfile(name, heightCm, preset);
}

export function profileWithArmSpan(profile: HumanProfile, armSpanCm: number): HumanProfile {
  const span = Math.max(profile.heightCm * .7, Math.min(profile.heightCm * 1.3, armSpanCm));
  const ratio = span / Math.max(1, profile.armSpanCm);
  const arm = {
    upperArm: (profile.upperArmLengthCm ?? profile.heightCm * .186) * ratio,
    forearm: (profile.forearmLengthCm ?? profile.heightCm * .157) * ratio,
  };
  return {
    ...profile, armSpanCm: span, preset: "CUSTOM",
    upperArmLengthCm: profile.segmentProvenance.upperArm === "USER_PROVIDED" ? profile.upperArmLengthCm : arm.upperArm,
    forearmLengthCm: profile.segmentProvenance.forearm === "USER_PROVIDED" ? profile.forearmLengthCm : arm.forearm,
    physicalDimensions: derivePhysicalDimensions(profile.heightCm, {
      ...profile.physicalDimensions,
      upperArmLengthCm: profile.segmentProvenance.upperArm === "USER_PROVIDED" ? profile.upperArmLengthCm ?? undefined : arm.upperArm,
      forearmLengthCm: profile.segmentProvenance.forearm === "USER_PROVIDED" ? profile.forearmLengthCm ?? undefined : arm.forearm,
    }),
  };
}

function segment(length: number, id: HumanSegmentKey, parentJoint: HumanConstraintGraph[HumanSegmentKey]["parentJoint"], childJoint: HumanConstraintGraph[HumanSegmentKey]["childJoint"], proximalWidth: number, distalWidth: number, preferred: number, min: number, max: number, provenance: SegmentProvenance) {
  return { id, parentJoint, childJoint, fixedLengthCm: length, proximalWidthCm: proximalWidth, distalWidthCm: distalWidth, preferredOrientationDeg: preferred, minimumJointAngleDeg: min, maximumJointAngleDeg: max, provenance } as const;
}

export function createConstraintGraph(profile: HumanProfile): HumanConstraintGraph {
  profile = normalizePhysicalProfile(profile);
  const h = profile.heightCm, provenance = profile.segmentProvenance, dimensions = profile.physicalDimensions;
  const hand = profile.handLengthCm ?? h * .108, derivedArm = derivedArmSegments(h, profile.armSpanCm, hand);
  const upperArm = profile.upperArmLengthCm ?? derivedArm.upperArm, forearm = profile.forearmLengthCm ?? derivedArm.forearm;
  const thigh = profile.thighLengthCm ?? h * .245, lowerLeg = profile.lowerLegLengthCm ?? h * .246;
  return {
    headNeck: segment(dimensions.headHeightCm + dimensions.neckLengthCm, "headNeck", "neck", "head", h * .09, h * .11, -90, 55, 125, provenance.headNeck),
    torso: segment(dimensions.torsoLengthCm, "torso", "pelvisRoot", "neck", dimensions.chestWidthCm, dimensions.waistWidthCm, -90, 55, 125, provenance.torso),
    shoulderGirdle: segment(dimensions.shoulderWidthCm, "shoulderGirdle", "leftShoulder", "rightShoulder", h * .10, h * .10, 0, 0, 180, provenance.shoulderGirdle),
    pelvis: segment(dimensions.pelvisWidthCm, "pelvis", "leftHip", "rightHip", h * .14, h * .13, 0, 0, 180, provenance.pelvis),
    upperArm: segment(upperArm, "upperArm", "leftShoulder", "leftElbow", h * .075, h * .058, 78, 5, 175, provenance.upperArm),
    forearm: segment(forearm, "forearm", "leftElbow", "leftWrist", h * .06, h * .043, 82, 5, 175, provenance.forearm),
    hand: segment(hand, "hand", "leftWrist", "leftHand", h * .052, h * .036, 82, 25, 155, provenance.hand),
    thigh: segment(thigh, "thigh", "leftHip", "leftKnee", h * .105, h * .075, 88, 15, 175, provenance.thigh),
    lowerLeg: segment(lowerLeg, "lowerLeg", "leftKnee", "leftAnkle", h * .078, h * .052, 90, 15, 175, provenance.lowerLeg),
    foot: segment(dimensions.footLengthCm, "foot", "leftAnkle", "leftFoot", h * .065, h * .075, 7, 0, 45, provenance.foot),
  };
}

export function createHuman(name: string, color: string, preset: HumanProfilePreset = "MEDIUM"): SceneHuman {
  const height = preset === "CUSTOM" ? 175 : HUMAN_PRESETS[preset].heightCm;
  const profile = profileFromHeight(name, height, preset);
  const pose = buildAnthropometricPose(profile, { x: .5, y: .91 }, 3, 1200, 900, "STANDING", 0);
  return {
    id: crypto.randomUUID(), name, color, profile, constraints: createConstraintGraph(profile), pose,
    placement: {
      root: pose.joints.pelvisRoot, leftFootContact: pose.joints.leftFoot, rightFootContact: pose.joints.rightFoot,
      contactPoint: midpoint(pose.joints.leftFoot, pose.joints.rightFoot), floorPinned: false,
      attachedObjectId: null, positionMode: "FREE", orientationDeg: 0, facingPreset: "FRONT",
      lastScalePxPerCm: null, scaleStatus: "NO_SCALE",
    },
    handTargets: { left: null, right: null }, modelVersion: "digital-human-v1", visible: true, locked: false,
  };
}

export function defaultPose(preset: HumanPosture): HumanPose {
  const profile = profileFromHeight("Operator", 175, "MEDIUM");
  return buildAnthropometricPose(profile, { x: .5, y: .91 }, 3, 1200, 900, preset, 0);
}

export function buildAnthropometricPose(profile: HumanProfile, standingPoint: NormalizedPoint, pixelsPerCm: number, imageWidth: number, imageHeight: number, preset: HumanPosture, orientationDeg: number, previous?: HumanPose): HumanPose {
  const base = previous ?? defaultPoseShell();
  const projected = getProjectedHuman({
    human: { profile: normalizePhysicalProfile(profile), pose: { ...base, preset }, placement: { ...emptyPlacement(standingPoint), orientationDeg } },
    calibration: emptyCalibration(), contactPoint: standingPoint, imageWidth, imageHeight,
    posture: preset, yawDeg: orientationDeg, fallbackPixelsPerCm: pixelsPerCm,
  });
  return { ...projected.pose, bendPreference: previous?.bendPreference ?? projected.pose.bendPreference };
}

export function resetHumanPose(human: SceneHuman, preset: HumanPosture = human.pose.preset, width = 1200, height = 900): SceneHuman {
  const scale = human.placement.lastScalePxPerCm ?? 3;
  const pose = buildAnthropometricPose(human.profile, human.placement.contactPoint, scale, width, height, preset === "CUSTOM" ? "STANDING" : preset, human.placement.orientationDeg, human.pose);
  return { ...human, constraints: createConstraintGraph(human.profile), pose, placement: syncPlacement(pose, human.placement) };
}

export function withUserSegment(profile: HumanProfile, key: HumanSegmentKey, valueCm: number | null): HumanProfile {
  const next = { ...profile, segmentProvenance: { ...profile.segmentProvenance, [key]: valueCm ? "USER_PROVIDED" : "DERIVED_DISPLAY_APPROXIMATION" }, geometrySource: valueCm ? "USER_MEASUREMENTS" as const : profile.geometrySource };
  return next;
}

export function repairHumanModel(human: SceneHuman, width = 1200, height = 900): SceneHuman {
  const profile = normalizePhysicalProfile(human.profile);
  const repaired = resetHumanPose({ ...human, profile, constraints: createConstraintGraph(profile), modelVersion: "digital-human-v1" }, human.pose.preset, width, height);
  return { ...repaired, placement: { ...repaired.placement, orientationDeg: human.placement.orientationDeg, facingPreset: human.placement.facingPreset, attachedObjectId: human.placement.attachedObjectId, positionMode: human.placement.positionMode } };
}

export function renderedHeightPixels(pose: HumanPose, imageHeight: number) {
  const top = Math.min(...Object.values(pose.joints).map((point) => point.y));
  const bottom = Math.max(pose.joints.leftFoot.y, pose.joints.rightFoot.y);
  return (bottom - top) * imageHeight;
}

export function syncPlacement(pose: HumanPose, placement: SceneHuman["placement"]): SceneHuman["placement"] {
  const contact = midpoint(pose.joints.leftFoot, pose.joints.rightFoot);
  return { ...placement, root: pose.joints.pelvisRoot, leftFootContact: pose.joints.leftFoot, rightFootContact: pose.joints.rightFoot, contactPoint: contact };
}

export function contactPoint(pose: HumanPose): NormalizedPoint { return midpoint(pose.joints.leftFoot, pose.joints.rightFoot); }
export function mapPoints<T extends Record<string, NormalizedPoint>>(points: T, fn: (point: NormalizedPoint) => NormalizedPoint): T { return Object.fromEntries(Object.entries(points).map(([key, value]) => [key, fn(value)])) as T; }
function midpoint(a: NormalizedPoint, b: NormalizedPoint) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }
function derivedArmSegments(heightCm: number, armSpanCm: number, handCm: number) { const shoulderWidth = heightCm * .225, available = Math.max(heightCm * .24, (armSpanCm - shoulderWidth) / 2 - handCm); return { upperArm: available * .57, forearm: available * .43 }; }
function defaultPoseShell(): HumanPose {
  const zero = { x: 0, y: 0 };
  return { preset: "STANDING", mirrored: false, scaleLocked: true, joints: Object.fromEntries(["head","neck","leftShoulder","rightShoulder","leftElbow","rightElbow","leftWrist","rightWrist","leftHand","rightHand","pelvisRoot","leftHip","rightHip","leftKnee","rightKnee","leftAnkle","rightAnkle","leftFoot","rightFoot"].map((name) => [name, zero])) as HumanPose["joints"], reachState: { leftArm: "NATURAL", rightArm: "NATURAL", leftLeg: "NATURAL", rightLeg: "NATURAL" }, bendPreference: { leftArm: 1, rightArm: -1, leftLeg: -1, rightLeg: 1 } };
}
function emptyPlacement(point: NormalizedPoint): SceneHuman["placement"] { return { root: point, leftFootContact: point, rightFootContact: point, contactPoint: point, floorPinned: false, attachedObjectId: null, positionMode: "FREE", orientationDeg: 0, facingPreset: "FRONT", lastScalePxPerCm: null, scaleStatus: "NO_SCALE" }; }
function emptyCalibration() { return { status: "UNCALIBRATED" as const, floorBaseline: null, horizonY: null, verticalDirection: null, references: [], scaleField: { status: "NO_SCALE" as const, coefficients: null, model: "NONE" as const, anchorCount: 0, inlierCount: 0, residualRms: null, uncertainty: null, generatedAt: null } }; }
