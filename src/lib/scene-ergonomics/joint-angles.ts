import type { Vector3Cm } from "../../types/photo-scene";
import type { ErgonomicsHumanInput, JointAngleSet, PostureSnapshot } from "./types.ts";
import { angleBetweenDeg, inverseEuler, inverseRootYaw, segmentVector, technical } from "./math3d.ts";
import { v3 } from "../photo-scene/vector3.ts";

export function calculateJointAngles3d(human:ErgonomicsHumanInput):JointAngleSet {
  const joints=human.jointPositionsCm,yaw=human.rootRotationDeg.y,rotation=(name:string)=>human.jointRotationsDeg[name]??v3();
  const chest=rotation("chest"),neck=addRotation(rotation("neck"),rotation("head"));
  const angles:JointAngleSet={
    trunk_flexion_deg:technical(chest.x,"deg"),trunk_side_bend_deg:technical(chest.z,"deg"),trunk_twist_deg:technical(chest.y,"deg"),
    neck_flexion_deg:technical(neck.x,"deg"),neck_side_bend_deg:technical(neck.z,"deg"),neck_rotation_deg:technical(neck.y,"deg"),
  };
  for(const side of ["left","right"] as const){
    const upper=segmentVector(joints,`${side}Shoulder`,`${side}Elbow`),fore=segmentVector(joints,`${side}Elbow`,`${side}Wrist`),thigh=segmentVector(joints,`${side}Hip`,`${side}Knee`),shin=segmentVector(joints,`${side}Knee`,`${side}Ankle`);
    const torsoRotation=addRotation(human.rootRotationDeg,chest),localUpper=upper?inverseEuler(inverseRootYaw(upper,yaw),chest):null;
    const shoulderElevation=localUpper?angleBetweenDeg(localUpper,v3(0,-1,0)):null;
    const shoulderAbduction=localUpper?Math.atan2(Math.abs(localUpper.x),Math.hypot(localUpper.y,localUpper.z))*180/Math.PI:null;
    const elbowJointAngle=upper&&fore?angleBetweenDeg(inverseRootYaw(scale(upper,-1),yaw),inverseRootYaw(fore,yaw)):null;
    const elbow=elbowJointAngle===null?null:180-elbowJointAngle;
    const hip=thigh?angleBetweenDeg(inverseEuler(inverseRootYaw(thigh,yaw),torsoRotation),v3(0,-1,0)):null;
    const kneeJointAngle=thigh&&shin?angleBetweenDeg(scale(thigh,-1),shin):null;
    const knee=kneeJointAngle===null?null:180-kneeJointAngle;
    const wrist=rotation(`${side}Wrist`),forearm=rotation(`${side}Elbow`),ankle=rotation(`${side}Ankle`);
    Object.assign(angles,{
      [`${side}_shoulder_elevation_deg`]:technical(shoulderElevation,"deg"),
      [`${side}_shoulder_abduction_deg`]:technical(shoulderAbduction,"deg"),
      [`${side}_shoulder_rotation_deg`]:technical(rotation(`${side}Shoulder`).y,"deg"),
      [`${side}_elbow_flexion_deg`]:technical(elbow,"deg"),
      [`${side}_forearm_pronation_supination_deg`]:technical(forearm.y,"deg"),
      [`${side}_wrist_flexion_deg`]:technical(wrist.x,"deg"),
      [`${side}_wrist_deviation_deg`]:technical(wrist.z,"deg"),
      [`${side}_hip_flexion_deg`]:technical(hip,"deg"),
      [`${side}_knee_flexion_deg`]:technical(knee,"deg"),
      [`${side}_ankle_relation_deg`]:technical(ankle.x,"deg"),
    });
  }
  return angles;
}

export function createPostureSnapshot(human:ErgonomicsHumanInput,collisions:PostureSnapshot["collisions"]=[],taskProgress:number|null=null):PostureSnapshot{return{humanId:human.id,humanRootCm:{...human.rootPositionCm},jointAngles:calculateJointAngles3d(human),supportState:human.supportState,handState:{left:human.hands.left.preset,right:human.hands.right.preset},heldObjectIds:[...human.heldObjectIds],collisions,taskProgress};}
function addRotation(a:Vector3Cm,b:Vector3Cm):Vector3Cm{return v3(a.x+b.x,a.y+b.y,a.z+b.z)}
function scale(a:Vector3Cm,value:number):Vector3Cm{return v3(a.x*value,a.y*value,a.z*value)}
