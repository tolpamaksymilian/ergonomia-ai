import type { HandPosePreset, SceneHuman, SceneObject, Vector3Cm } from "../../types/photo-scene";
import { applyHandPreset, gripGeometryForDiameter } from "./hand-rig.ts";
import { getHumanJointPositions3d } from "./human-3d-model.ts";
import { getReachabilityResult } from "./reachability-3d.ts";

export function attachObjectToHand(human: SceneHuman, object: SceneObject, hand: "LEFT"|"RIGHT", grip: HandPosePreset = "POWER_GRIP"): { human: SceneHuman; object: SceneObject; status: string } {
  if (!object.geometry3d) return { human, object, status: "UNKNOWN_GEOMETRY" };
  const target = object.interactionPoints3d.find((p) => p.type === "GRIP")?.positionCm ?? object.geometry3d.positionCm;
  const reach = getReachabilityResult(human, hand, target, "WHOLE_BODY"); if (reach.level === "UNREACHABLE") return { human, object, status: "UNREACHABLE" };
  const side = hand === "LEFT" ? "left" : "right", diameter = object.geometry3d.dimensionsCm.diameter ?? Math.min(object.geometry3d.dimensionsCm.width ?? Infinity, object.geometry3d.dimensionsCm.depth ?? Infinity);
  const gripResult = Number.isFinite(diameter) ? gripGeometryForDiameter(human.profile, diameter, grip) : { status: "GRIP_GEOMETRY_PARTIAL" as const };
  if (gripResult.status === "GRIP_GEOMETRY_INVALID") return { human, object, status: gripResult.status };
  return { human: { ...human, human3d: { ...human.human3d, hands: { ...human.human3d.hands, [side]: applyHandPreset(human.human3d.hands[side], grip) }, attachments: { ...human.human3d.attachments, [`${side}ObjectId`]: object.id } } }, object: { ...object, geometry3d: { ...object.geometry3d, collisionGroup: "HELD_OBJECT" } }, status: gripResult.status };
}
export function getAttachedObjectWorldPosition(human: SceneHuman, object: SceneObject): Vector3Cm | null {
  if (!object.geometry3d) return null;
  const attachedLeft = human.human3d.attachments.leftObjectId === object.id;
  const attachedRight = human.human3d.attachments.rightObjectId === object.id;
  if (!attachedLeft && !attachedRight) return object.geometry3d.positionCm;
  const joints = getHumanJointPositions3d(human.human3d);
  if (attachedLeft && attachedRight) return { x: (joints.leftWrist.x + joints.rightWrist.x) / 2, y: (joints.leftWrist.y + joints.rightWrist.y) / 2, z: (joints.leftWrist.z + joints.rightWrist.z) / 2 };
  return attachedLeft ? joints.leftWrist : joints.rightWrist;
}
export function resolveAttachedObject(human: SceneHuman, object: SceneObject): SceneObject {
  const position = getAttachedObjectWorldPosition(human, object);
  return position && object.geometry3d ? { ...object, geometry3d: { ...object.geometry3d, positionCm: position } } : object;
}
export function releaseObjectFromHand(human: SceneHuman, object: SceneObject, hand: "LEFT"|"RIGHT") {
  const side = hand === "LEFT" ? "left" : "right", resolved = resolveAttachedObject(human, object);
  const attachments = { ...human.human3d.attachments, [`${side}ObjectId`]: null };
  const stillHeld = attachments.leftObjectId === object.id || attachments.rightObjectId === object.id;
  return { human: { ...human, human3d: { ...human.human3d, attachments } }, object: resolved.geometry3d ? { ...resolved, geometry3d: { ...resolved.geometry3d, collisionGroup: stillHeld ? "HELD_OBJECT" as const : "STATIC_SCENE" as const } } : resolved };
}
export function attachObjectTwoHanded(human: SceneHuman, object: SceneObject) { const points = object.interactionPoints3d.filter((p) => p.type === "GRIP"); if (points.length < 2) return { human, object, status: "MISSING_TWO_GRIP_POINTS" }; const left = getReachabilityResult(human, "LEFT", points[0].positionCm, "WHOLE_BODY"), right = getReachabilityResult(human, "RIGHT", points[1].positionCm, "WHOLE_BODY"); if (left.level === "UNREACHABLE" || right.level === "UNREACHABLE") return { human, object, status: "UNREACHABLE" }; const first = attachObjectToHand(human, object, "LEFT", "POWER_GRIP"); return attachObjectToHand(first.human, first.object, "RIGHT", "POWER_GRIP"); }
