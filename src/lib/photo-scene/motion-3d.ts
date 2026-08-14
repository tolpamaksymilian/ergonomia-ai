import type { MotionResult3D, SceneHuman, SceneObject, Vector3Cm } from "../../types/photo-scene";
import { getSceneCollisions } from "./collision-3d.ts";
import { applyArmTarget, getReachabilityResult } from "./reachability-3d.ts";
import { distance3, lerp3 } from "./vector3.ts";
import { getFingertipReachability } from "./reachability-3d.ts";

export function getMotionPathResult(human: SceneHuman, objects: SceneObject[], hand: "LEFT"|"RIGHT", startCm: Vector3Cm, targetCm: Vector3Cm, requestedSamples?: number): MotionResult3D {
  const samples = requestedSamples ?? Math.max(20, Math.min(60, Math.ceil(distance3(startCm,targetCm)/3)));
  if (objects.some((object)=>object.geometry3d && object.geometry3d.geometryQuality!=="COMPLETE" && object.geometry3d.collisionEnabled)) return result("INVALID_GEOMETRY",null,null);
  for(let index=0;index<samples;index++){
    const progress=index/(samples-1),target=lerp3(startCm,targetCm,progress),reach=getReachabilityResult(human,hand,target,"ARM_ONLY");
    if(reach.level==="UNREACHABLE")return result("UNREACHABLE",progress,null);
    const moved={...human,human3d:applyArmTarget(human.human3d,human.profile,hand,target)}, collision=getSceneCollisions(moved,objects).find((item)=>item.level==="CONTACT"||item.level==="PENETRATION");
    if(collision)return result("COLLISION",progress,collision);
  }
  return result("CLEAR",null,null);
  function result(status:MotionResult3D["status"],progress:number|null,collision:MotionResult3D["firstCollision"]):MotionResult3D{return{status,hand,startCm,targetCm,sampleCount:samples,firstCollisionProgress:progress,firstCollision:collision}}
}

export type BasicTaskAction = "REACH"|"GRASP"|"MOVE_OBJECT"|"PLACE"|"PRESS_BUTTON";
export type BasicTask3D = { id:string; action:BasicTaskAction; humanId:string; objectId:string|null; interactionPointId:string|null; hand:"LEFT"|"RIGHT"; startCm:Vector3Cm; targetCm:Vector3Cm };
export function createBasicTask3d(action: BasicTaskAction, human: SceneHuman, hand: "LEFT"|"RIGHT", startCm: Vector3Cm, targetCm: Vector3Cm, objectId: string|null = null, interactionPointId: string|null = null): BasicTask3D { return { id: crypto.randomUUID(), action, humanId: human.id, objectId, interactionPointId, hand, startCm, targetCm }; }
export function evaluateBasicTask3d(task: BasicTask3D, human: SceneHuman, objects: SceneObject[]) {
  if (task.humanId !== human.id) return { status: "INVALID_HUMAN" as const, reachability: null, motion: null };
  const reachability = task.action === "PRESS_BUTTON" ? getFingertipReachability(human, task.hand, task.targetCm, task.interactionPointId) : getReachabilityResult(human, task.hand, task.targetCm, task.action === "REACH" ? "WHOLE_BODY" : "ARM_ONLY", task.interactionPointId);
  if (reachability.level === "UNREACHABLE") return { status: "UNREACHABLE" as const, reachability, motion: null };
  const motion = getMotionPathResult(human, objects, task.hand, task.startCm, task.targetCm);
  return { status: motion.status === "CLEAR" ? "FEASIBLE" as const : motion.status, reachability, motion };
}
