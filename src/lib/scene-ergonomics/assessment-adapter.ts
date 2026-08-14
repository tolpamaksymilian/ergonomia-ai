import tables from "./assessment-tables.generated.json" with { type: "json" };
import type { JointAngleSet, MethodEvidence, MethodResult, SceneManualContext } from "./types.ts";

const RULA_VERSION="rula-v1.0-beta.1",REBA_VERSION="reba-v1.0-beta.1";
type Side="LEFT"|"RIGHT";

export function assessSceneRula(angles:JointAngleSet,side:Side,context:SceneManualContext):MethodResult{
  const p=side.toLowerCase(),value=(name:string)=>angles[name]?.valid?angles[name].value:null;
  const upper=metric("upper_arm",value(`${p}_shoulder_elevation_deg`),categoryUpper),lower=metric("lower_arm",value(`${p}_elbow_flexion_deg`),categoryLower),wrist=metric("wrist",value(`${p}_wrist_flexion_deg`),categoryWrist);
  const wristTwist=metric("wrist_twist",value(`${p}_forearm_pronation_supination_deg`),(v)=>Math.abs(v)<=90?1:2),neck=metric("neck",value("neck_flexion_deg"),categoryNeckRula),trunk=metric("trunk",value("trunk_flexion_deg"),categoryTrunk);
  const upperAdj=angleAdjustment("upper_arm_adjustment",[value(`${p}_shoulder_abduction_deg`)],(v)=>Math.abs(v[0])>30?1:0,[-1,0,1,2]),lowerAdj=unknown("lower_arm_adjustment",[0,1],["cross_body_relation_for_current_pose"]),wristAdj=angleAdjustment("wrist_adjustment",[value(`${p}_wrist_deviation_deg`)],(v)=>Math.abs(v[0])>10?1:0,[0,1]);
  const neckAdj=angleAdjustment("neck_adjustment",[value("neck_rotation_deg"),value("neck_side_bend_deg")],(v)=>(Math.abs(v[0])>10?1:0)+(Math.abs(v[1])>10?1:0),[0,1,2]),trunkAdj=angleAdjustment("trunk_adjustment",[value("trunk_twist_deg"),value("trunk_side_bend_deg")],(v)=>(Math.abs(v[0])>10?1:0)+(Math.abs(v[1])>10?1:0),[0,1,2]);
  const legs=unknown("legs",[1,2],["weight_distribution_and_support"]),muscle=user("muscle_use",context.rulaMuscleUse,[0,1]),force=user("force_load",context.rulaForceLoad,[0,1,2,3]);
  const components={upper_arm:upper,lower_arm:lower,wrist,wrist_twist:wristTwist,neck,trunk,legs,muscle_use:muscle,force_load:force,upper_arm_adjustment:upperAdj,lower_arm_adjustment:lowerAdj,wrist_adjustment:wristAdj,neck_adjustment:neckAdj,trunk_adjustment:trunkAdj};
  const scores:number[]=[];for(const ua of combine(upper,upperAdj,1,6))for(const la of combine(lower,lowerAdj,1,3))for(const wr of combine(wrist,wristAdj,1,4))for(const wt of options(wristTwist))for(const ne of combine(neck,neckAdj,1,6))for(const tr of combine(trunk,trunkAdj,1,6))for(const le of options(legs))for(const mu of options(muscle))for(const fo of options(force)){const a=rulaA(ua,la,wr,wt),b=rulaB(ne,tr,le);scores.push(rulaC(a+mu+fo,b+mu+fo))}
  return method("RULA",side,components,scores,RULA_VERSION,tables.rula.version);
}

export function assessSceneReba(angles:JointAngleSet,side:Side,context:SceneManualContext):MethodResult{
  const p=side.toLowerCase(),value=(name:string)=>angles[name]?.valid?angles[name].value:null;
  const neck=metric("neck",value("neck_flexion_deg"),(v)=>v<=20?1:2),trunk=metric("trunk",value("trunk_flexion_deg"),categoryTrunk),legs=unknown("legs",[1,2,3,4],["weight_distribution_and_support"]),upper=metric("upper_arm",value(`${p}_shoulder_elevation_deg`),categoryUpper),lower=metric("lower_arm",value(`${p}_elbow_flexion_deg`),(v)=>v>=60&&v<=100?1:2),wrist=metric("wrist",value(`${p}_wrist_flexion_deg`),categoryWrist);
  const neckAdj=angleAdjustment("neck_adjustment",[value("neck_rotation_deg"),value("neck_side_bend_deg")],(v)=>Math.abs(v[0])>10||Math.abs(v[1])>10?1:0,[0,1]),trunkAdj=angleAdjustment("trunk_adjustment",[value("trunk_twist_deg"),value("trunk_side_bend_deg")],(v)=>Math.abs(v[0])>10||Math.abs(v[1])>10?1:0,[0,1]),upperAdj=angleAdjustment("upper_arm_adjustment",[value(`${p}_shoulder_abduction_deg`)],(v)=>Math.abs(v[0])>30?1:0,[-1,0,1,2]),wristAdj=angleAdjustment("wrist_adjustment",[value(`${p}_wrist_deviation_deg`)],(v)=>Math.abs(v[0])>10?1:0,[0,1]);
  const load=user("load_force",context.rebaLoadForce,[0,1,2,3]),coupling=user("coupling",context.rebaCoupling,[0,1,2,3]),activity=user("activity",context.rebaActivity,[0,1,2,3]);
  const components={neck,trunk,legs,upper_arm:upper,lower_arm:lower,wrist,neck_adjustment:neckAdj,trunk_adjustment:trunkAdj,upper_arm_adjustment:upperAdj,wrist_adjustment:wristAdj,load_force:load,coupling,activity};
  const scores:number[]=[];for(const ne of combine(neck,neckAdj,1,3))for(const tr of combine(trunk,trunkAdj,1,5))for(const le of options(legs))for(const ua of combine(upper,upperAdj,1,6))for(const la of options(lower))for(const wr of combine(wrist,wristAdj,1,3))for(const lo of options(load))for(const co of options(coupling))for(const ac of options(activity)){scores.push(Math.min(15,rebaC(rebaA(tr,ne,le)+lo,rebaB(ua,la,wr)+co)+ac))}
  return method("REBA",side,components,scores,REBA_VERSION,tables.reba.version);
}

function metric(name:string,value:number|null,category:(value:number)=>number):MethodEvidence{return value===null||!Number.isFinite(value)?unknown(name,[],[name]):{name,rawInput:value,scoreComponent:category(value),possibleScores:[],source:"DERIVED",quality:.95,missingEvidence:[]}}
function adjustment(name:string,value:number):MethodEvidence{return{name,rawInput:value,scoreComponent:value,possibleScores:[],source:"DERIVED",quality:.9,missingEvidence:[]}}
function angleAdjustment(name:string,values:(number|null)[],category:(values:number[])=>number,possibleScores:number[]):MethodEvidence{return values.some((value)=>value===null||!Number.isFinite(value))?unknown(name,possibleScores,[name]):adjustment(name,category(values as number[]))}
function user(name:string,value:number|null,possible:number[]):MethodEvidence{return value===null?unknown(name,possible,[name]):{name,rawInput:value,scoreComponent:value,possibleScores:[],source:"USER_PROVIDED",quality:1,missingEvidence:[]}}
function unknown(name:string,possibleScores:number[],missingEvidence:string[]):MethodEvidence{return{name,rawInput:null,scoreComponent:null,possibleScores,source:"UNKNOWN",quality:0,missingEvidence}}
function options(value:MethodEvidence){return value.scoreComponent!==null?[value.scoreComponent]:value.possibleScores}
function combine(base:MethodEvidence,adj:MethodEvidence,min:number,max:number){return[...new Set(options(base).flatMap((b)=>options(adj).map((a)=>Math.max(min,Math.min(max,b+a)))))]}
function method(methodName:"RULA"|"REBA",side:Side,components:Record<string,MethodEvidence>,scores:number[],methodVersion:string,tableVersion:string):MethodResult{const unique=[...new Set(scores)].sort((a,b)=>a-b),missing=Object.values(components).filter((c)=>c.source==="UNKNOWN");if(!unique.length)return{method:methodName,side,status:"INSUFFICIENT_DATA",score:null,scoreRange:null,components,methodVersion,tableSourceVersion:tableVersion};const complete=missing.length===0;return{method:methodName,side,status:complete?"COMPLETE":"PARTIAL",score:complete?unique[0]:null,scoreRange:{min:unique[0],max:unique.at(-1)!},components,methodVersion,tableSourceVersion:tableVersion}}
function categoryUpper(v:number){return v<=20?1:v<=45?2:v<=90?3:4}function categoryLower(v:number){return v>=60&&v<=100?1:2}function categoryWrist(v:number){const a=Math.abs(v);return a<=1e-6?1:a<=15?2:3}function categoryNeckRula(v:number){return v<=10?1:v<=20?2:3}function categoryTrunk(v:number){return v<=1e-6?1:v<=20?2:v<=60?3:4}
function rulaA(ua:number,la:number,w:number,tw:number){return tables.rula.table_a[(ua-1)*3+la-1][(w-1)*2+tw-1]}function rulaB(n:number,t:number,l:number){return tables.rula.table_b[n-1][(t-1)*2+l-1]}function rulaC(c:number,d:number){return tables.rula.table_c[Math.min(c,8)-1][Math.min(d,7)-1]}
function rebaA(t:number,n:number,l:number){return tables.reba.table_a[(t-1)*3+n-1][l-1]}function rebaB(u:number,l:number,w:number){return tables.reba.table_b[(u-1)*2+l-1][w-1]}function rebaC(a:number,b:number){return tables.reba.table_c[Math.min(a,12)-1][Math.min(b,12)-1]}
