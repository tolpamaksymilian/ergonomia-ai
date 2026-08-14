import type { Vector3Cm } from "../../types/photo-scene";
import { cross3, dot3, length3, normalize3, rotateEuler, sub3, v3 } from "../photo-scene/vector3.ts";

export function validVector(value: Vector3Cm | undefined): value is Vector3Cm { return Boolean(value && [value.x,value.y,value.z].every(Number.isFinite)); }
export function angleBetweenDeg(a:Vector3Cm,b:Vector3Cm):number|null { const la=length3(a),lb=length3(b);if(la<1e-8||lb<1e-8||!Number.isFinite(la+lb))return null;return Math.acos(Math.max(-1,Math.min(1,dot3(a,b)/(la*lb))))*180/Math.PI; }
export function signedAngleDeg(a:Vector3Cm,b:Vector3Cm,normal:Vector3Cm):number|null { const angle=angleBetweenDeg(a,b);if(angle===null)return null;return angle*Math.sign(dot3(cross3(a,b),normal)||1); }
export function inverseRootYaw(vector:Vector3Cm,yawDeg:number):Vector3Cm{return rotateEuler(vector,v3(0,-yawDeg,0));}
export function inverseEuler(vector:Vector3Cm,rotation:Vector3Cm):Vector3Cm{return rotateEuler(vector,v3(-rotation.x,-rotation.y,-rotation.z));}
export function segmentVector(joints:Record<string,Vector3Cm>,from:string,to:string):Vector3Cm|null { const a=joints[from],b=joints[to];return validVector(a)&&validVector(b)?sub3(b,a):null; }
export function horizontalDistance(a:Vector3Cm,b:Vector3Cm){return Math.hypot(a.x-b.x,a.z-b.z)}
export function directionAngles(from:Vector3Cm,to:Vector3Cm,forward=v3(0,0,1)){const d=sub3(to,from),horizontal=Math.hypot(d.x,d.z);return{distance:length3(d),vertical:Math.atan2(d.y,horizontal)*180/Math.PI,horizontal:signedAngleDeg(normalize3(v3(d.x,0,d.z)),forward,v3(0,1,0))??0}}
export function technical(value:number|null,unit:string,source:"USER_PROVIDED"|"DERIVED"|"SCENE_CALIBRATED"|"SCENE_ESTIMATED"|"UNKNOWN"="DERIVED",quality=.95,frame="human_anatomical") { const valid=value!==null&&Number.isFinite(value);return{value:valid?Math.round(value*1e6)/1e6:null,unit,valid,quality:valid?Math.max(0,Math.min(1,quality)):0,source:valid?source:"UNKNOWN" as const,frame,rejectionReason:valid?null:"invalid_or_missing_geometry"}; }
