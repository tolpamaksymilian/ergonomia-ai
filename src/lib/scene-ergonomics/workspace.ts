import type { Vector3Cm } from "../../types/photo-scene";
import { distance3, rotateEuler, sub3, v3 } from "../photo-scene/vector3.ts";
import { getReachabilityResult } from "../photo-scene/reachability-3d.ts";
import type { ErgonomicsHumanInput, ErgonomicsObjectInput, ReachAssessment, SceneManualContext, WorkHeightResult, WorkZone } from "./types.ts";
import { horizontalDistance, technical } from "./math3d.ts";

type Envelope={primary:Vector3Cm[];functional:Vector3Cm[];maximum:Vector3Cm[]};
const envelopeCache=new Map<string,Envelope>();

export function analyzeWorkHeight(human:ErgonomicsHumanInput,objects:ErgonomicsObjectInput[],context:SceneManualContext):WorkHeightResult|null{
  const surface=objects.find((object)=>["WORK_SURFACE","TABLE","CONVEYOR"].includes(object.type)&&object.geometry?.dimensionsCm.height);
  if(!surface?.geometry)return null;const height=surface.geometry.positionCm.y+(surface.geometry.dimensionsCm.height??0)/2,j=human.jointPositionsCm;
  const elbow=(j.leftElbow.y+j.rightElbow.y)/2,difference=height-elbow;
  return{objectId:surface.id,surfaceHeightCm:technical(height,"cm",surface.provenance),elbowHeightCm:technical(elbow,"cm"),shoulderHeightCm:technical((j.leftShoulder.y+j.rightShoulder.y)/2,"cm"),hipHeightCm:technical(j.pelvis.y,"cm"),eyeHeightCm:technical(j.head.y+human.profile.physicalDimensions.headHeightCm*.12,"cm"),differenceFromElbowCm:technical(difference,"cm"),taskType:context.taskType,classification:context.taskType==="UNKNOWN"?"UNKNOWN":difference>5?"ABOVE_REFERENCE":difference< -5?"BELOW_REFERENCE":"AT_REFERENCE"};
}

export function analyzeReachPoints(human:ErgonomicsHumanInput,objects:ErgonomicsObjectInput[]):ReachAssessment[]{
  const output:ReachAssessment[]=[];for(const object of objects)for(const point of object.interactionPoints)for(const hand of handsFor(point.hand))output.push(analyzeReachPoint(human,object,point,hand));return output;
}
export function analyzeReachPoint(human:ErgonomicsHumanInput,object:ErgonomicsObjectInput,point:ErgonomicsObjectInput["interactionPoints"][number],hand:"LEFT"|"RIGHT"):ReachAssessment{
  const side=hand==="LEFT"?"left":"right",shoulder=human.jointPositionsCm[`${side}Shoulder`],knee=human.jointPositionsCm[`${side}Knee`];
  const pseudo={profile:human.profile,human3d:{rootPositionCm:human.rootPositionCm,rootRotationDeg:human.rootRotationDeg,jointPositionsCm:unworld(human),jointRotationsDeg:human.jointRotationsDeg,poleTargetsCm:{leftElbow:v3(-35,human.profile.heightCm*.68,-25),rightElbow:v3(35,human.profile.heightCm*.68,-25),leftKnee:v3(-12,human.profile.heightCm*.25,25),rightKnee:v3(12,human.profile.heightCm*.25,25)},hands:{left:{preset:"RELAXED",fingers:{} as never,palmRotationDeg:v3()},right:{preset:"RELAXED",fingers:{} as never,palmRotationDeg:v3()}},attachments:{leftObjectId:null,rightObjectId:null},modelVersion:"digital-human-3d-v1",migrationStatus:"NATIVE_3D",legacy2dBackup:null} as never};
  const arm=getReachabilityResult(pseudo,hand,point.positionCm,"ARM_ONLY",point.id),whole=getReachabilityResult(pseudo,hand,point.positionCm,"WHOLE_BODY",point.id),zone=classifyWorkZone(human,hand,point.positionCm);
  const local=inverseHuman(point.positionCm,human),crossBody=hand==="RIGHT"?local.x< -human.profile.physicalDimensions.chestWidthCm*.15:local.x>human.profile.physicalDimensions.chestWidthCm*.15;
  const extra=whole.level==="UNREACHABLE"?"UNREACHABLE":arm.level==="REACHABLE"?"NONE":Math.abs(whole.reachMarginCm??-999)<5?"SMALL":Math.abs(whole.reachMarginCm??-999)<15?"MODERATE":"LARGE";
  return{humanId:human.id,objectId:object.id,pointId:point.id,pointName:point.name,hand,zone,reachMarginCm:arm.reachMarginCm,armOnly:arm.level,wholeBody:whole.level,movementRequirement:extra,crossBody,targetHeightRelativeToShoulderCm:point.positionCm.y-shoulder.y,targetHeightRelativeToKneeCm:point.positionCm.y-knee.y,horizontalFromShoulderCm:horizontalDistance(point.positionCm,shoulder),quality:object.geometry?.geometryQuality==="COMPLETE"?1:object.geometry?0.65:0.4};
}
export function classifyWorkZone(human:ErgonomicsHumanInput,hand:"LEFT"|"RIGHT",target:Vector3Cm):WorkZone{
  const side=hand==="LEFT"?"left":"right",shoulder=human.jointPositionsCm[`${side}Shoulder`],localTarget=rotateEuler(sub3(target,shoulder),v3(0,-human.rootRotationDeg.y,0)),envelope=getEnvelope(human);
  if(nearest(localTarget,envelope.primary)<=9)return"PRIMARY_ZONE";if(nearest(localTarget,envelope.functional)<=9)return"FUNCTIONAL_ZONE";if(nearest(localTarget,envelope.maximum)<=11)return"MAXIMUM_ZONE";
  const max=human.profile.physicalDimensions.upperArmLengthCm+human.profile.physicalDimensions.forearmLengthCm+human.profile.physicalDimensions.handLengthCm;return distance3(target,shoulder)<=max?"MAXIMUM_ZONE":"OUTSIDE_ZONE";
}
export function generateReachHeatmap(human:ErgonomicsHumanInput,object:ErgonomicsObjectInput,hand:"LEFT"|"RIGHT"|"BOTH",spacingCm=10){const g=object.geometry;if(!g||!g.dimensionsCm.width||!g.dimensionsCm.depth||!g.dimensionsCm.height)return[];const points=[];for(let x=-g.dimensionsCm.width/2;x<=g.dimensionsCm.width/2;x+=spacingCm)for(let z=-g.dimensionsCm.depth/2;z<=g.dimensionsCm.depth/2;z+=spacingCm){const p=v3(g.positionCm.x+x,g.positionCm.y+g.dimensionsCm.height/2,g.positionCm.z+z),left=classifyWorkZone(human,"LEFT",p),right=classifyWorkZone(human,"RIGHT",p);points.push({positionCm:p,left,right,combined:hand==="LEFT"?left:hand==="RIGHT"?right:bestZone(left,right)})}return points;}
export function analyzeStandingZone(human:ErgonomicsHumanInput,target:Vector3Cm,spacingCm=20,radiusCm=60){const output=[];for(let x=-radiusCm;x<=radiusCm;x+=spacingCm)for(let z=-radiusCm;z<=radiusCm;z+=spacingCm){const moved={...human,rootPositionCm:v3(human.rootPositionCm.x+x,0,human.rootPositionCm.z+z),jointPositionsCm:Object.fromEntries(Object.entries(human.jointPositionsCm).map(([name,p])=>[name,v3(p.x+x,p.y,p.z+z)]))};output.push({positionCm:moved.rootPositionCm,left:classifyWorkZone(moved,"LEFT",target),right:classifyWorkZone(moved,"RIGHT",target)})}return output;}
function getEnvelope(human:ErgonomicsHumanInput){const d=human.profile.physicalDimensions,key=[d.upperArmLengthCm,d.forearmLengthCm,d.handLengthCm].join(":");const cached=envelopeCache.get(key);if(cached)return cached;const result:Envelope={primary:[],functional:[],maximum:[]};for(let elevation=-40;elevation<=140;elevation+=10)for(let azimuth=-100;azimuth<=100;azimuth+=10)for(let elbow=0;elbow<=150;elbow+=15){const upper=rotateEuler(v3(0,-d.upperArmLengthCm,0),v3(0,0,elevation));const fore=rotateEuler(v3(0,-(d.forearmLengthCm+d.handLengthCm*.7),0),v3(0,0,elevation+elbow));const point=rotateEuler(v3(upper.x+fore.x,upper.y+fore.y,upper.z+fore.z),v3(0,azimuth,0));result.maximum.push(point);if(Math.abs(elevation)<=90&&Math.abs(azimuth)<=70&&elbow>=30)result.functional.push(point);if(Math.abs(elevation)<=45&&Math.abs(azimuth)<=45&&elbow>=60&&elbow<=120)result.primary.push(point)}envelopeCache.set(key,result);return result;}
function nearest(target:Vector3Cm,points:Vector3Cm[]){let best=Infinity;for(const point of points)best=Math.min(best,distance3(target,point));return best}
function handsFor(hand:"LEFT"|"RIGHT"|"BOTH"|null):("LEFT"|"RIGHT")[]{return hand==="LEFT"?["LEFT"]:hand==="RIGHT"?["RIGHT"]:["LEFT","RIGHT"]}
function inverseHuman(target:Vector3Cm,human:ErgonomicsHumanInput){return rotateEuler(sub3(target,human.rootPositionCm),v3(0,-human.rootRotationDeg.y,0))}
function unworld(human:ErgonomicsHumanInput){return Object.fromEntries(Object.entries(human.jointPositionsCm).map(([name,p])=>[name,rotateEuler(sub3(p,human.rootPositionCm),v3(0,-human.rootRotationDeg.y,0))]))}
const zoneRank:Record<WorkZone,number>={PRIMARY_ZONE:0,FUNCTIONAL_ZONE:1,MAXIMUM_ZONE:2,OUTSIDE_ZONE:3,UNKNOWN:4};function bestZone(a:WorkZone,b:WorkZone){return zoneRank[a]<=zoneRank[b]?a:b}
