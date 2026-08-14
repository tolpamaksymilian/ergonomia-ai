"use client";

import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useMemo, useState } from "react";
import * as THREE from "three";
import type { Human3DJointName, SceneHuman, SceneObject, Vector3Cm } from "@/types/photo-scene";
import { getFingerJointPositions } from "@/lib/photo-scene/hand-rig";
import { getHumanJointPositions3d } from "@/lib/photo-scene/human-3d-model";
import { resolveAttachedObject } from "@/lib/photo-scene/object-interaction-3d";
import type { BodyRegion } from "@/lib/scene-ergonomics/types";

type CameraPreset = "PERSPECTIVE" | "FRONT" | "SIDE" | "TOP" | "HUMAN";
const BODY_SEGMENTS: [Human3DJointName,Human3DJointName,string,BodyRegion][] = [
  ["pelvis","spineLower","torso","TORSO"],["spineLower","spineMid","torso","TORSO"],["spineMid","chest","torso","TORSO"],["chest","neck","neck","NECK"],["neck","head","head","HEAD"],["head","headTop","head","HEAD"],
  ["chest","leftClavicle","arm","LEFT_ARM"],["leftClavicle","leftShoulder","arm","LEFT_ARM"],["leftShoulder","leftElbow","arm","LEFT_ARM"],["leftElbow","leftWrist","forearm","LEFT_ARM"],["rightClavicle","rightShoulder","arm","RIGHT_ARM"],["chest","rightClavicle","arm","RIGHT_ARM"],["rightShoulder","rightElbow","arm","RIGHT_ARM"],["rightElbow","rightWrist","forearm","RIGHT_ARM"],
  ["pelvis","leftHip","pelvis","LEFT_LEG"],["leftHip","leftKnee","thigh","LEFT_LEG"],["leftKnee","leftAnkle","calf","LEFT_LEG"],["leftAnkle","leftFoot","foot","LEFT_LEG"],["pelvis","rightHip","pelvis","RIGHT_LEG"],["rightHip","rightKnee","thigh","RIGHT_LEG"],["rightKnee","rightAnkle","calf","RIGHT_LEG"],["rightAnkle","rightFoot","foot","RIGHT_LEG"],
];

export function Scene3DViewport({ humans, objects, selectedHumanId, ergonomicFocus = null, debug = false }: { humans: SceneHuman[]; objects: SceneObject[]; selectedHumanId: string|null; ergonomicFocus?: BodyRegion|null; debug?: boolean }) {
  const [preset,setPreset]=useState<CameraPreset>("PERSPECTIVE");
  const renderedObjects = useMemo(() => objects.map((object) => {
    const holder = humans.find((human) => human.human3d.attachments.leftObjectId === object.id || human.human3d.attachments.rightObjectId === object.id);
    return holder ? resolveAttachedObject(holder, object) : object;
  }), [humans, objects]);
  return <div className="relative min-h-[520px] overflow-hidden rounded-xl bg-slate-950" role="application" aria-label="Interaktywny widok stanowiska 3D w centymetrach">
    <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-1 rounded-lg border border-white/10 bg-slate-950/85 p-1 text-[11px] text-white">{(["PERSPECTIVE","FRONT","SIDE","TOP","HUMAN"] as CameraPreset[]).map((item)=><button key={item} aria-pressed={preset===item} onClick={()=>setPreset(item)} className={`rounded px-2 py-1 ${preset===item?"bg-cyan-500 text-slate-950":"hover:bg-white/10"}`}>{({PERSPECTIVE:"Perspektywa",FRONT:"Przód",SIDE:"Bok",TOP:"Góra",HUMAN:"Operator"})[item]}</button>)}</div>
    {ergonomicFocus && <span className="absolute right-3 top-3 z-10 rounded-lg border border-amber-300/40 bg-slate-950/90 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-amber-200">Fokus: {ergonomicFocus.replaceAll("_"," ")}</span>}
    <span className="absolute bottom-3 left-3 z-10 rounded bg-slate-950/80 px-2 py-1 text-[10px] text-cyan-200">Świat 3D · cm · podłoga Y=0</span>
    <Canvas shadows camera={{ position: cameraPosition(preset), fov: 38, near: 1, far: 2500 }} key={preset} dpr={[1,1.5]}>
      <color attach="background" args={["#07111f"]}/><ambientLight intensity={1.1}/><directionalLight castShadow position={[180,300,160]} intensity={2.2}/><directionalLight position={[-180,140,-120]} intensity={.7} color="#22d3ee"/>
      <gridHelper args={[600,60,"#164e63","#172554"]} position={[0,0,0]}/><mesh rotation={[-Math.PI/2,0,0]} position={[0,-.6,0]} receiveShadow><planeGeometry args={[600,600]}/><meshStandardMaterial color="#081426" roughness={.92}/></mesh>
      {renderedObjects.filter((o)=>o.visible&&o.geometry3d).map((object)=><ObjectMesh key={object.id} object={object}/>) }
      {humans.filter((h)=>h.visible).map((human)=><HumanMesh key={human.id} human={human} selected={human.id===selectedHumanId} ergonomicFocus={human.id===selectedHumanId?ergonomicFocus:null} debug={debug}/>) }
      <OrbitControls makeDefault target={[0,90,0]} enableDamping minDistance={90} maxDistance={900} maxPolarAngle={Math.PI*.49}/>
    </Canvas>
  </div>;
}

function HumanMesh({human,selected,ergonomicFocus,debug}:{human:SceneHuman;selected:boolean;ergonomicFocus:BodyRegion|null;debug:boolean}){
  const joints=useMemo(()=>getHumanJointPositions3d(human.human3d),[human.human3d]); const d=human.profile.physicalDimensions;
  const radius=(kind:string)=>kind==="torso"?Math.max(d.chestDepthCm,d.waistWidthCm)*.26:kind==="thigh"?d.thighThicknessCm*.5:kind==="calf"?d.calfThicknessCm*.5:kind==="arm"?d.upperArmThicknessCm*.5:kind==="forearm"?d.forearmThicknessCm*.5:kind==="foot"?d.footLengthCm*.12:kind==="head"?d.headHeightCm*.25:d.neckLengthCm*.28;
  const fingers=(["left","right"] as const).flatMap((side)=>{const positions=getFingerJointPositions(human.profile,human.human3d.hands[side],side,joints[`${side}Wrist`]);return (["thumb","index","middle","ring","little"] as const).flatMap((name)=>{const chain=[positions.palmCenter,positions[`${name}MCP`],positions[`${name}PIP`],positions[`${name}DIP`],positions[`${name}TIP`]];return chain.slice(1).map((point,index)=>({side,name,index,start:chain[index],end:point}))})});
  return <group>{BODY_SEGMENTS.map(([a,b,kind,region])=><Segment key={`${a}-${b}`} start={joints[a]} end={joints[b]} radius={radius(kind)} color={ergonomicFocus===region?"#fbbf24":selected?human.color:"#64748b"}/>) }
    <mesh position={toTuple(joints.head)} castShadow><sphereGeometry args={[d.headHeightCm*.32,16,12]}/><meshStandardMaterial color={selected?human.color:"#64748b"} roughness={.55}/></mesh>
    {fingers.map((finger)=><Segment key={`${finger.side}-${finger.name}-${finger.index}`} start={finger.start} end={finger.end} radius={Math.max(.6,d.handWidthCm*.07)*(1-finger.index*.12)} color={ergonomicFocus===`${finger.side.toUpperCase()}_HAND`?"#fbbf24":selected?"#67e8f9":"#94a3b8"}/>) }
    {ergonomicFocus && focusJoints(ergonomicFocus).map((name)=><mesh key={`focus-${name}`} position={toTuple(joints[name])}><sphereGeometry args={[2.5,12,10]}/><meshBasicMaterial color="#fde047"/></mesh>)}
    {debug&&Object.entries(joints).map(([name,p])=><mesh key={name} position={toTuple(p)}><sphereGeometry args={[1.4,8,8]}/><meshBasicMaterial color="#fbbf24"/></mesh>)}
  </group>;
}
function Segment({start,end,radius,color}:{start:Vector3Cm;end:Vector3Cm;radius:number;color:string}){const midpoint=new THREE.Vector3((start.x+end.x)/2,(start.y+end.y)/2,(start.z+end.z)/2),direction=new THREE.Vector3(end.x-start.x,end.y-start.y,end.z-start.z),length=direction.length(),quaternion=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize());return <mesh position={midpoint} quaternion={quaternion} castShadow><cylinderGeometry args={[radius*.82,radius,Math.max(.01,length),10]}/><meshStandardMaterial color={color} roughness={.48} metalness={.08}/></mesh>}
function ObjectMesh({object}:{object:SceneObject}){const g=object.geometry3d!;const d=g.dimensionsCm,color=g.geometryQuality==="COMPLETE"?"#0e7490":"#d97706";return <mesh position={toTuple(g.positionCm)} rotation={degTuple(g.rotationDeg)} castShadow receiveShadow>{g.type==="SPHERE"?<sphereGeometry args={[(d.diameter??10)/2,20,16]}/>:g.type==="CYLINDER"||g.type==="HANDLE"||g.type==="BOTTLE"?<cylinderGeometry args={[(d.diameter??5)/2,(d.diameter??5)/2,d.length??20,16]}/>:<boxGeometry args={[d.width??1,d.height??1,d.depth??1]}/>}<meshStandardMaterial color={color} transparent={g.type==="PLANE_PROXY"} opacity={g.type==="PLANE_PROXY"?.45:1} roughness={.65}/></mesh>}
function toTuple(p:Vector3Cm):[number,number,number]{return[p.x,p.y,p.z]}
function degTuple(p:Vector3Cm):[number,number,number]{return[p.x,p.y,p.z].map((v)=>v*Math.PI/180) as [number,number,number]}
function cameraPosition(preset:CameraPreset):[number,number,number]{return preset==="FRONT"?[0,110,420]:preset==="SIDE"?[420,110,0]:preset==="TOP"?[0,520,.01]:preset==="HUMAN"?[0,165,30]:[260,210,340]}
function focusJoints(region:BodyRegion):Human3DJointName[]{const joints:Record<BodyRegion,Human3DJointName[]>={HEAD:["head"],NECK:["neck"],TORSO:["chest","pelvis"],LEFT_ARM:["leftShoulder","leftElbow","leftWrist"],RIGHT_ARM:["rightShoulder","rightElbow","rightWrist"],LEFT_HAND:["leftWrist","leftHand"],RIGHT_HAND:["rightWrist","rightHand"],LEFT_LEG:["leftHip","leftKnee","leftAnkle"],RIGHT_LEG:["rightHip","rightKnee","rightAnkle"]};return joints[region]}
