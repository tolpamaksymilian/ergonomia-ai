import type { CollisionResult3D, GeometryQuality, Human3DJointName, SceneHuman, SceneObject, Vector3Cm } from "../../types/photo-scene";
import { getHumanJointPositions3d } from "./human-3d-model.ts";
import { getFingerJointPositions } from "./hand-rig.ts";
import { add3, distance3, lerp3, sub3, v3 } from "./vector3.ts";

type Capsule = { part: string; start: Vector3Cm; end: Vector3Cm; radius: number };
type Aabb = { min: Vector3Cm; max: Vector3Cm };
const SEGMENTS: [string, Human3DJointName, Human3DJointName, keyof SceneHuman["profile"]["physicalDimensions"]][] = [
  ["leftUpperArm","leftShoulder","leftElbow","upperArmThicknessCm"], ["leftForearm","leftElbow","leftWrist","forearmThicknessCm"], ["rightUpperArm","rightShoulder","rightElbow","upperArmThicknessCm"], ["rightForearm","rightElbow","rightWrist","forearmThicknessCm"], ["leftThigh","leftHip","leftKnee","thighThicknessCm"], ["leftLowerLeg","leftKnee","leftAnkle","calfThicknessCm"], ["rightThigh","rightHip","rightKnee","thighThicknessCm"], ["rightLowerLeg","rightKnee","rightAnkle","calfThicknessCm"],
];

export function getCollisionResult(human: SceneHuman, object: SceneObject): CollisionResult3D[] {
  const geometry = object.geometry3d;
  if (!geometry || geometry.geometryQuality !== "COMPLETE" || !geometry.collisionEnabled) return [unknown(object.id, geometry?.geometryQuality ?? "UNKNOWN")];
  const aabb = objectAabb(object); if (!aabb) return [unknown(object.id, geometry.geometryQuality)];
  const capsules = humanCapsules(human), results: CollisionResult3D[] = [];
  for (const capsule of capsules) {
    if (!aabbOverlap(capsuleAabb(capsule), aabb)) continue;
    const nearest = nearestSegmentPointToAabb(capsule, aabb), penetration = capsule.radius - nearest.distance;
    if (penetration >= -.15) results.push({ level: penetration > .15 ? "PENETRATION" : "CONTACT", humanPart: capsule.part, objectId: object.id, contactPointCm: nearest.point, penetrationDepthCm: Math.max(0, penetration), geometryQuality: geometry.geometryQuality });
  }
  return results.length ? results : [{ level: "CLEAR", humanPart: null, objectId: object.id, contactPointCm: null, penetrationDepthCm: 0, geometryQuality: geometry.geometryQuality }];
}
export function getSceneCollisions(human: SceneHuman, objects: SceneObject[]) { return objects.flatMap((object) => getCollisionResult(human, object)).filter((r) => r.level !== "CLEAR"); }
export function getSelfCollisionResult(human: SceneHuman): CollisionResult3D[] { const capsules = humanCapsules(human), forbidden: [string,string][] = [["leftForearm","torso"],["rightForearm","torso"],["leftThigh","rightThigh"]], output: CollisionResult3D[] = []; for (const [a,b] of forbidden) { const first=capsules.find((c)=>c.part===a), second=capsules.find((c)=>c.part===b); if (!first||!second) continue; const d=segmentDistanceApprox(first,second), penetration=first.radius+second.radius-d; if (penetration>0) output.push({ level:"PENETRATION",humanPart:`${a}:${b}`,objectId:null,contactPointCm:lerp3(first.end,second.end,.5),penetrationDepthCm:penetration,geometryQuality:"COMPLETE" }); } return output; }
export function getFloorCollisions(human: SceneHuman): CollisionResult3D[] {
  return humanCapsules(human).flatMap((capsule) => {
    const lowest = Math.min(capsule.start.y, capsule.end.y) - capsule.radius;
    return lowest < -.1 ? [{ level: "PENETRATION" as const, humanPart: capsule.part, objectId: "scene-floor", contactPointCm: v3(capsule.end.x, 0, capsule.end.z), penetrationDepthCm: -lowest, geometryQuality: "COMPLETE" as const }] : [];
  });
}
export function getHeldObjectCollisions(human: SceneHuman, held: SceneObject, sceneObjects: SceneObject[]) { if (!held.geometry3d) return [unknown(held.id,"UNKNOWN")]; return sceneObjects.filter((object)=>object.id!==held.id).flatMap((object)=>object.geometry3d ? objectAabbCollision(held,object) : [unknown(object.id,"UNKNOWN")]); }
export function getFingerObjectCollisions(human: SceneHuman, object: SceneObject, hand: "LEFT" | "RIGHT"): CollisionResult3D[] {
  const aabb = objectAabb(object), geometry = object.geometry3d;
  if (!aabb || !geometry || geometry.geometryQuality !== "COMPLETE" || !geometry.collisionEnabled) return [unknown(object.id, geometry?.geometryQuality ?? "UNKNOWN")];
  const side = hand === "LEFT" ? "left" : "right", joints = getHumanJointPositions3d(human.human3d);
  const points = getFingerJointPositions(human.profile, human.human3d.hands[side], side, joints[`${side}Wrist`]);
  const radius = Math.max(.35, human.profile.physicalDimensions.handWidthCm * .045), results: CollisionResult3D[] = [];
  for (const finger of ["thumb", "index", "middle", "ring", "little"] as const) {
    const chain = [points[`${finger}MCP`], points[`${finger}PIP`], points[`${finger}DIP`], points[`${finger}TIP`]];
    for (let index = 0; index < chain.length - 1; index += 1) {
      const capsule = { part: `${side}-${finger}-${index + 1}`, start: chain[index], end: chain[index + 1], radius };
      if (!aabbOverlap(capsuleAabb(capsule), aabb)) continue;
      const nearest = nearestSegmentPointToAabb(capsule, aabb), penetration = radius - nearest.distance;
      if (penetration >= -.1) results.push({ level: penetration > .1 ? "PENETRATION" : "CONTACT", humanPart: capsule.part, objectId: object.id, contactPointCm: nearest.point, penetrationDepthCm: Math.max(0, penetration), geometryQuality: geometry.geometryQuality });
    }
  }
  return results.length ? results : [{ level: "CLEAR", humanPart: null, objectId: object.id, contactPointCm: null, penetrationDepthCm: 0, geometryQuality: geometry.geometryQuality }];
}

function humanCapsules(human: SceneHuman): Capsule[] { const joints=getHumanJointPositions3d(human.human3d), d=human.profile.physicalDimensions, torso:Capsule={part:"torso",start:joints.pelvis,end:joints.chest,radius:Math.max(d.waistWidthCm,d.chestDepthCm)*.36}; return [torso,...SEGMENTS.map(([part,a,b,key])=>({part,start:joints[a],end:joints[b],radius:Number(d[key])*.5}))]; }
function objectAabb(object: SceneObject): Aabb|null { const g=object.geometry3d;if(!g)return null; const {width,height,depth,diameter,length}=g.dimensionsCm; const x=(width??diameter),y=(height??(g.type==="CYLINDER"||g.type==="HANDLE"?diameter:length)),z=(depth??diameter); if(!x||!y||!z)return null; const half=v3(x/2,y/2,z/2);return{min:sub3(g.positionCm,half),max:add3(g.positionCm,half)}; }
function objectAabbCollision(a:SceneObject,b:SceneObject):CollisionResult3D[]{const aa=objectAabb(a),bb=objectAabb(b);if(!aa||!bb)return[unknown(b.id,"UNKNOWN")];if(!aabbOverlap(aa,bb))return[];const px=Math.min(aa.max.x,bb.max.x)-Math.max(aa.min.x,bb.min.x),py=Math.min(aa.max.y,bb.max.y)-Math.max(aa.min.y,bb.min.y),pz=Math.min(aa.max.z,bb.max.z)-Math.max(aa.min.z,bb.min.z);return[{level:"PENETRATION",humanPart:"heldObject",objectId:b.id,contactPointCm:v3((Math.max(aa.min.x,bb.min.x)+Math.min(aa.max.x,bb.max.x))/2,(Math.max(aa.min.y,bb.min.y)+Math.min(aa.max.y,bb.max.y))/2,(Math.max(aa.min.z,bb.min.z)+Math.min(aa.max.z,bb.max.z))/2),penetrationDepthCm:Math.min(px,py,pz),geometryQuality:b.geometry3d?.geometryQuality??"UNKNOWN"}];}
function capsuleAabb(c:Capsule):Aabb{return{min:v3(Math.min(c.start.x,c.end.x)-c.radius,Math.min(c.start.y,c.end.y)-c.radius,Math.min(c.start.z,c.end.z)-c.radius),max:v3(Math.max(c.start.x,c.end.x)+c.radius,Math.max(c.start.y,c.end.y)+c.radius,Math.max(c.start.z,c.end.z)+c.radius)}}
function aabbOverlap(a:Aabb,b:Aabb){return a.min.x<=b.max.x&&a.max.x>=b.min.x&&a.min.y<=b.max.y&&a.max.y>=b.min.y&&a.min.z<=b.max.z&&a.max.z>=b.min.z}
function nearestSegmentPointToAabb(c:Capsule,b:Aabb){let best={distance:Infinity,point:c.start};for(let i=0;i<=12;i++){const p=lerp3(c.start,c.end,i/12),q=v3(clamp(p.x,b.min.x,b.max.x),clamp(p.y,b.min.y,b.max.y),clamp(p.z,b.min.z,b.max.z)),d=distance3(p,q);if(d<best.distance)best={distance:d,point:q}}return best}
function segmentDistanceApprox(a:Capsule,b:Capsule){let best=Infinity;for(let i=0;i<=8;i++)for(let j=0;j<=8;j++)best=Math.min(best,distance3(lerp3(a.start,a.end,i/8),lerp3(b.start,b.end,j/8)));return best}
function unknown(objectId:string,quality:GeometryQuality):CollisionResult3D{return{level:"UNKNOWN_GEOMETRY",humanPart:null,objectId,contactPointCm:null,penetrationDepthCm:null,geometryQuality:quality}}
function clamp(v:number,min:number,max:number){return Math.max(min,Math.min(max,v))}
