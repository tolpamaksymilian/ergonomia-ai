import type { Human3DJointName, Human3DState, HumanProfile, Vector3Cm } from "../../types/photo-scene";
import { getCanonicalHuman } from "./human-physical-model.ts";
import { buildCanonicalPose } from "./human-pose-model.ts";
import { createHandRig } from "./hand-rig.ts";
import { add3, rotateEuler, sub3, v3 } from "./vector3.ts";

export type Human3DBone = { name: string; parent: Human3DJointName; child: Human3DJointName; allowedDof: ("x" | "y" | "z")[]; limitsDeg: Partial<Record<"x" | "y" | "z", [number, number]>> };
export const HUMAN_3D_BONES: Human3DBone[] = [
  bone("pelvis-spine", "pelvis", "spineLower", ["x","y","z"], 30), bone("spine-mid", "spineLower", "spineMid", ["x","y","z"], 25), bone("chest", "spineMid", "chest", ["x","y","z"], 35), bone("neck", "chest", "neck", ["x","y","z"], 55), bone("head", "neck", "head", ["x","y","z"], 65),
  ...limb("left", "Arm"), ...limb("right", "Arm"), ...limb("left", "Leg"), ...limb("right", "Leg"),
];

const KINEMATIC_EDGES: [Human3DJointName, Human3DJointName][] = [
  ["root", "pelvis"], ["pelvis", "spineLower"], ["spineLower", "spineMid"], ["spineMid", "chest"], ["chest", "neck"], ["neck", "head"], ["head", "headTop"],
  ["chest", "leftClavicle"], ["leftClavicle", "leftShoulder"], ["leftShoulder", "leftElbow"], ["leftElbow", "leftWrist"], ["leftWrist", "leftHand"],
  ["chest", "rightClavicle"], ["rightClavicle", "rightShoulder"], ["rightShoulder", "rightElbow"], ["rightElbow", "rightWrist"], ["rightWrist", "rightHand"],
  ["pelvis", "leftHip"], ["leftHip", "leftKnee"], ["leftKnee", "leftAnkle"], ["leftAnkle", "leftFoot"],
  ["pelvis", "rightHip"], ["rightHip", "rightKnee"], ["rightKnee", "rightAnkle"], ["rightAnkle", "rightFoot"],
];

export function createHuman3DState(profile: HumanProfile, migrationStatus: Human3DState["migrationStatus"] = "NATIVE_3D"): Human3DState {
  const joints = createNeutralJointPositions3d(profile), zero = () => ({ x: 0, y: 0, z: 0 });
  return { modelVersion: "digital-human-3d-v1", migrationStatus, rootPositionCm: v3(), rootRotationDeg: zero(), jointPositionsCm: joints, jointRotationsDeg: Object.fromEntries(Object.keys(joints).map((key) => [key, zero()])) as Human3DState["jointRotationsDeg"], poleTargetsCm: { leftElbow: v3(-35, profile.heightCm * .68, -25), rightElbow: v3(35, profile.heightCm * .68, -25), leftKnee: v3(-12, profile.heightCm * .25, 25), rightKnee: v3(12, profile.heightCm * .25, 25) }, hands: { left: createHandRig(), right: createHandRig() }, attachments: { leftObjectId: null, rightObjectId: null }, legacy2dBackup: null };
}

export function createNeutralJointPositions3d(profile: HumanProfile): Record<Human3DJointName, Vector3Cm> {
  const canonical = buildCanonicalPose(getCanonicalHuman(profile), "STANDING").joints, d = profile.physicalDimensions;
  const pelvis = canonical.pelvisRoot, neck = canonical.neck, chestY = pelvis.y + d.torsoLengthCm * .78;
  return {
    root: v3(0,0,0), pelvis: { ...pelvis }, spineLower: v3(0, pelvis.y + d.torsoLengthCm * .25, 0), spineMid: v3(0, pelvis.y + d.torsoLengthCm * .52, 0), chest: v3(0, chestY, 0), neck: { ...neck }, head: v3(0, canonical.head.y - d.headHeightCm * .45, canonical.head.z), headTop: { ...canonical.head },
    leftClavicle: v3(-d.shoulderWidthCm * .25, chestY, 0), leftShoulder: { ...canonical.leftShoulder }, leftElbow: { ...canonical.leftElbow }, leftWrist: { ...canonical.leftWrist }, leftHand: { ...canonical.leftHand },
    rightClavicle: v3(d.shoulderWidthCm * .25, chestY, 0), rightShoulder: { ...canonical.rightShoulder }, rightElbow: { ...canonical.rightElbow }, rightWrist: { ...canonical.rightWrist }, rightHand: { ...canonical.rightHand },
    leftHip: { ...canonical.leftHip }, leftKnee: { ...canonical.leftKnee }, leftAnkle: { ...canonical.leftAnkle }, leftFoot: { ...canonical.leftFoot }, rightHip: { ...canonical.rightHip }, rightKnee: { ...canonical.rightKnee }, rightAnkle: { ...canonical.rightAnkle }, rightFoot: { ...canonical.rightFoot },
  };
}

export function getHumanJointPositions3d(state: Human3DState): Record<Human3DJointName, Vector3Cm> {
  return forwardKinematics3d(state);
}
export function forwardKinematics3d(state: Human3DState): Record<Human3DJointName, Vector3Cm> {
  const local = state.jointPositionsCm;
  const posed = { root: { ...local.root } } as Record<Human3DJointName, Vector3Cm>;
  const cumulative = { root: state.jointRotationsDeg.root ?? v3() } as Record<Human3DJointName, Vector3Cm>;
  for (const [parent, child] of KINEMATIC_EDGES) {
    const parentRotation = cumulative[parent] ?? v3();
    const ownRotation = state.jointRotationsDeg[parent] ?? v3();
    const appliedRotation = parent === "root" ? parentRotation : add3(parentRotation, ownRotation);
    posed[child] = add3(posed[parent], rotateEuler(sub3(local[child], local[parent]), appliedRotation));
    cumulative[child] = appliedRotation;
  }
  return Object.fromEntries(Object.entries(posed).map(([name, point]) => [name, add3(state.rootPositionCm, rotateEuler(point, state.rootRotationDeg))])) as Record<Human3DJointName, Vector3Cm>;
}
export function setHumanJointRotation(state: Human3DState, joint: Human3DJointName, rotation: Vector3Cm): Human3DState {
  const finite = (value: number) => Number.isFinite(value) ? Math.max(-180, Math.min(180, value)) : 0;
  return { ...state, jointRotationsDeg: { ...state.jointRotationsDeg, [joint]: v3(finite(rotation.x), finite(rotation.y), finite(rotation.z)) } };
}
export function setHumanRoot(state: Human3DState, position: Vector3Cm, yawDeg = state.rootRotationDeg.y): Human3DState { return { ...state, rootPositionCm: { x: position.x, y: Math.max(0, position.y), z: position.z }, rootRotationDeg: { ...state.rootRotationDeg, y: ((yawDeg % 360) + 360) % 360 } }; }
export function getHumanJointAngles3d(state: Human3DState) { return structuredClone(state.jointRotationsDeg); }
export function validateHuman3D(profile: HumanProfile, state: Human3DState) { const joints = getHumanJointPositions3d(state), height = joints.headTop.y - Math.min(joints.leftFoot.y, joints.rightFoot.y); return { valid: Object.values(joints).every((p) => [p.x,p.y,p.z].every(Number.isFinite)) && Math.abs(height - profile.heightCm) < 1e-6, heightCm: height }; }

function bone(name: string, parent: Human3DJointName, child: Human3DJointName, allowedDof: ("x"|"y"|"z")[], limit: number): Human3DBone { return { name, parent, child, allowedDof, limitsDeg: Object.fromEntries(allowedDof.map((axis) => [axis, [-limit, limit]])) }; }
function limb(side: "left"|"right", type: "Arm"|"Leg"): Human3DBone[] { if (type === "Arm") return [bone(`${side}-clavicle`, "chest", `${side}Clavicle`, ["x","y","z"], 35), bone(`${side}-shoulder`, `${side}Clavicle`, `${side}Shoulder`, ["x","y","z"], 170), { name: `${side}-elbow`, parent: `${side}Shoulder`, child: `${side}Elbow`, allowedDof: ["x"], limitsDeg: { x: [0, 155] } }, bone(`${side}-wrist`, `${side}Elbow`, `${side}Wrist`, ["x","y","z"], 80)]; return [bone(`${side}-hip`, "pelvis", `${side}Hip`, ["x","y","z"], 120), { name: `${side}-knee`, parent: `${side}Hip`, child: `${side}Knee`, allowedDof: ["x"], limitsDeg: { x: [0, 150] } }, bone(`${side}-ankle`, `${side}Knee`, `${side}Ankle`, ["x","z"], 45)]; }
