import type {
  HumanConstraintGraph, HumanPose, HumanPosture, HumanProfile, HumanProfilePreset,
  HumanSegmentKey, NormalizedPoint, SceneHuman, SegmentProvenance,
} from "../../types/photo-scene";

export const HUMAN_PRESETS: Record<Exclude<HumanProfilePreset, "CUSTOM">, { label: string; heightCm: number }> = {
  SHORT: { label: "Niski", heightCm: 160 }, MEDIUM: { label: "Średni", heightCm: 175 }, TALL: { label: "Wysoki", heightCm: 190 },
};

const derivedProvenance = (): Record<HumanSegmentKey, SegmentProvenance> => ({
  headNeck: "DERIVED_APPROXIMATION", torso: "DERIVED_APPROXIMATION", shoulderGirdle: "DERIVED_APPROXIMATION",
  pelvis: "DERIVED_APPROXIMATION", upperArm: "DERIVED_APPROXIMATION", forearm: "DERIVED_APPROXIMATION",
  hand: "DERIVED_APPROXIMATION", thigh: "DERIVED_APPROXIMATION", lowerLeg: "DERIVED_APPROXIMATION", foot: "DERIVED_APPROXIMATION",
});

export function profileFromHeight(name: string, heightCm: number, preset: HumanProfilePreset = "CUSTOM"): HumanProfile {
  const h = Math.max(120, Math.min(220, heightCm));
  const handLengthCm = h * .108, arm = derivedArmSegments(h, h, handLengthCm);
  return {
    name, preset, heightCm: h, armSpanCm: h, functionalReachCm: h * .40, maximumReachCm: h * .47,
    shoulderHeightCm: h * .818, elbowHeightCm: h * .63, eyeHeightCm: h * .936,
    hipHeightCm: h * .53, upperArmLengthCm: arm.upperArm, forearmLengthCm: arm.forearm,
    handLengthCm, thighLengthCm: h * .245, lowerLegLengthCm: h * .246,
    geometrySource: "ANTHROPOMETRIC_ESTIMATE", segmentProvenance: derivedProvenance(),
  };
}

export function profileWithArmSpan(profile: HumanProfile, armSpanCm: number): HumanProfile {
  const span = Math.max(profile.heightCm * .7, Math.min(profile.heightCm * 1.3, armSpanCm));
  const hand = profile.handLengthCm ?? profile.heightCm * .108, arm = derivedArmSegments(profile.heightCm, span, hand);
  return {
    ...profile, armSpanCm: span, preset: "CUSTOM",
    upperArmLengthCm: profile.segmentProvenance.upperArm === "USER_PROVIDED" ? profile.upperArmLengthCm : arm.upperArm,
    forearmLengthCm: profile.segmentProvenance.forearm === "USER_PROVIDED" ? profile.forearmLengthCm : arm.forearm,
  };
}

function segment(length: number, id: HumanSegmentKey, parentJoint: HumanConstraintGraph[HumanSegmentKey]["parentJoint"], childJoint: HumanConstraintGraph[HumanSegmentKey]["childJoint"], proximalWidth: number, distalWidth: number, preferred: number, min: number, max: number, provenance: SegmentProvenance) {
  return { id, parentJoint, childJoint, fixedLengthCm: length, proximalWidthCm: proximalWidth, distalWidthCm: distalWidth, preferredOrientationDeg: preferred, minimumJointAngleDeg: min, maximumJointAngleDeg: max, provenance } as const;
}

export function createConstraintGraph(profile: HumanProfile): HumanConstraintGraph {
  const h = profile.heightCm, provenance = profile.segmentProvenance;
  const hand = profile.handLengthCm ?? h * .108, derivedArm = derivedArmSegments(h, profile.armSpanCm, hand);
  const upperArm = profile.upperArmLengthCm ?? derivedArm.upperArm, forearm = profile.forearmLengthCm ?? derivedArm.forearm;
  const thigh = profile.thighLengthCm ?? h * .245, lowerLeg = profile.lowerLegLengthCm ?? h * .246;
  return {
    headNeck: segment(h * .145, "headNeck", "neck", "head", h * .09, h * .11, -90, 55, 125, provenance.headNeck),
    torso: segment(Math.max(h * .25, (profile.shoulderHeightCm ?? h * .818) - (profile.hipHeightCm ?? h * .53)), "torso", "pelvisRoot", "neck", h * .21, h * .15, -90, 55, 125, provenance.torso),
    shoulderGirdle: segment(h * .245, "shoulderGirdle", "leftShoulder", "rightShoulder", h * .10, h * .10, 0, 0, 180, provenance.shoulderGirdle),
    pelvis: segment(h * .115, "pelvis", "leftHip", "rightHip", h * .14, h * .13, 0, 0, 180, provenance.pelvis),
    upperArm: segment(upperArm, "upperArm", "leftShoulder", "leftElbow", h * .075, h * .058, 78, 5, 175, provenance.upperArm),
    forearm: segment(forearm, "forearm", "leftElbow", "leftWrist", h * .06, h * .043, 82, 5, 175, provenance.forearm),
    hand: segment(hand, "hand", "leftWrist", "leftHand", h * .052, h * .036, 82, 25, 155, provenance.hand),
    thigh: segment(thigh, "thigh", "leftHip", "leftKnee", h * .105, h * .075, 88, 15, 175, provenance.thigh),
    lowerLeg: segment(lowerLeg, "lowerLeg", "leftKnee", "leftAnkle", h * .078, h * .052, 90, 15, 175, provenance.lowerLeg),
    foot: segment(h * .152, "foot", "leftAnkle", "leftFoot", h * .065, h * .075, 7, 0, 45, provenance.foot),
  };
}

export function createHuman(name: string, color: string, preset: HumanProfilePreset = "MEDIUM"): SceneHuman {
  const height = preset === "CUSTOM" ? 175 : HUMAN_PRESETS[preset].heightCm;
  const profile = profileFromHeight(name, height, preset), pose = defaultPose("STANDING");
  return {
    id: crypto.randomUUID(), name, color, profile, constraints: createConstraintGraph(profile), pose,
    placement: {
      root: pose.joints.pelvisRoot, leftFootContact: pose.joints.leftFoot, rightFootContact: pose.joints.rightFoot,
      contactPoint: midpoint(pose.joints.leftFoot, pose.joints.rightFoot), floorPinned: false,
      attachedObjectId: null, positionMode: "FREE", orientationDeg: 0, facingPreset: "FRONT",
      lastScalePxPerCm: null, scaleStatus: "NO_SCALE",
    },
    handTargets: { left: null, right: null }, visible: true, locked: false,
  };
}

export function defaultPose(preset: HumanPosture): HumanPose {
  const profile = profileFromHeight("Operator", 175, "MEDIUM");
  return buildAnthropometricPose(profile, { x: .5, y: .91 }, 3, 1200, 900, preset, 0);
}

export function buildAnthropometricPose(profile: HumanProfile, standingPoint: NormalizedPoint, pixelsPerCm: number, imageWidth: number, imageHeight: number, preset: HumanPosture, orientationDeg: number, previous?: HumanPose): HumanPose {
  const graph = createConstraintGraph(profile), px = Math.max(.05, pixelsPerCm), facing = Math.max(.16, Math.abs(Math.cos(orientationDeg * Math.PI / 180)));
  const toNorm = (point: { x: number; y: number }): NormalizedPoint => ({ x: point.x / imageWidth, y: point.y / imageHeight });
  const stand = { x: standingPoint.x * imageWidth, y: standingPoint.y * imageHeight };
  const hipHeight = (profile.hipHeightCm ?? profile.heightCm * .53) * px;
  const shoulderHeight = (profile.shoulderHeightCm ?? profile.heightCm * .818) * px;
  const root = { x: stand.x, y: stand.y - hipHeight };
  const hipHalf = graph.pelvis.fixedLengthCm * px * facing / 2, shoulderHalf = graph.shoulderGirdle.fixedLengthCm * px * facing / 2;
  const lean = preset === "FORWARD_LEAN" ? graph.torso.fixedLengthCm * px * .18 : 0;
  const neck = { x: root.x + lean, y: stand.y - shoulderHeight - profile.heightCm * px * .025 };
  let head = { x: neck.x + lean * .18, y: stand.y - profile.heightCm * px };
  const leftHip = { x: root.x - hipHalf, y: root.y }, rightHip = { x: root.x + hipHalf, y: root.y };
  const leftShoulder = { x: neck.x - shoulderHalf, y: stand.y - shoulderHeight }, rightShoulder = { x: neck.x + shoulderHalf, y: stand.y - shoulderHeight };
  const seated = preset === "SEATED";
  const legAngles = seated ? { left: [155, 88], right: [25, 92] } : { left: [93, 87], right: [87, 93] };
  const leftKnee = project(leftHip, graph.thigh.fixedLengthCm * px, legAngles.left[0]), rightKnee = project(rightHip, graph.thigh.fixedLengthCm * px, legAngles.right[0]);
  const leftAnkle = project(leftKnee, graph.lowerLeg.fixedLengthCm * px, legAngles.left[1]), rightAnkle = project(rightKnee, graph.lowerLeg.fixedLengthCm * px, legAngles.right[1]);
  const leftFoot = project(leftAnkle, graph.foot.fixedLengthCm * px, 5), rightFoot = project(rightAnkle, graph.foot.fixedLengthCm * px, 5);
  head = { x: neck.x + lean * .18, y: (leftFoot.y + rightFoot.y) / 2 - profile.heightCm * px };
  const oneHanded = preset === "ONE_HANDED", reaching = ["REACHING", "WORK_SURFACE", "TWO_HANDED"].includes(preset);
  const leftArmAngles = reaching || oneHanded ? [165, 178, 178] : [102, 82, 88];
  const rightArmAngles = reaching ? [15, 2, 2] : [78, 98, 92];
  const leftElbow = project(leftShoulder, graph.upperArm.fixedLengthCm * px, leftArmAngles[0]), rightElbow = project(rightShoulder, graph.upperArm.fixedLengthCm * px, rightArmAngles[0]);
  const leftWrist = project(leftElbow, graph.forearm.fixedLengthCm * px, leftArmAngles[1]), rightWrist = project(rightElbow, graph.forearm.fixedLengthCm * px, rightArmAngles[1]);
  const leftHand = project(leftWrist, graph.hand.fixedLengthCm * px, leftArmAngles[2]), rightHand = project(rightWrist, graph.hand.fixedLengthCm * px, rightArmAngles[2]);
  const raw = { head, neck, leftShoulder, rightShoulder, leftElbow, rightElbow, leftWrist, rightWrist, leftHand, rightHand, pelvisRoot: root, leftHip, rightHip, leftKnee, rightKnee, leftAnkle, rightAnkle, leftFoot, rightFoot };
  const pose: HumanPose = {
    preset, mirrored: false, scaleLocked: true,
    joints: Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, toNorm(value)])) as HumanPose["joints"],
    reachState: { leftArm: "NATURAL", rightArm: "NATURAL", leftLeg: "NATURAL", rightLeg: "NATURAL" },
    bendPreference: previous?.bendPreference ?? { leftArm: 1, rightArm: -1, leftLeg: -1, rightLeg: 1 },
  };
  return translatePoseToFootContact(pose, standingPoint);
}

export function resetHumanPose(human: SceneHuman, preset: HumanPosture = human.pose.preset, width = 1200, height = 900): SceneHuman {
  const scale = human.placement.lastScalePxPerCm ?? 3;
  const pose = buildAnthropometricPose(human.profile, human.placement.contactPoint, scale, width, height, preset === "CUSTOM" ? "STANDING" : preset, human.placement.orientationDeg, human.pose);
  return { ...human, constraints: createConstraintGraph(human.profile), pose, placement: syncPlacement(pose, human.placement) };
}

export function withUserSegment(profile: HumanProfile, key: HumanSegmentKey, valueCm: number | null): HumanProfile {
  const next = { ...profile, segmentProvenance: { ...profile.segmentProvenance, [key]: valueCm ? "USER_PROVIDED" : "DERIVED_APPROXIMATION" }, geometrySource: valueCm ? "USER_MEASUREMENTS" as const : profile.geometrySource };
  return next;
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
function project(origin: { x: number; y: number }, length: number, angleDeg: number) { const angle = angleDeg * Math.PI / 180; return { x: origin.x + Math.cos(angle) * length, y: origin.y + Math.sin(angle) * length }; }
function translatePoseToFootContact(pose: HumanPose, standingPoint: NormalizedPoint): HumanPose { const current = contactPoint(pose), dx = standingPoint.x - current.x, dy = standingPoint.y - current.y; return { ...pose, joints: mapPoints(pose.joints, (point) => ({ x: point.x + dx, y: point.y + dy })) }; }
