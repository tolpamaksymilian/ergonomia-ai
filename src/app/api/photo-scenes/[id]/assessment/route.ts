import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth/access";
import { buildSceneErgonomicsInput } from "@/lib/scene-ergonomics/input";
import { assessScene } from "@/lib/scene-ergonomics/processor";
import { buildSceneDesignReport } from "@/lib/scene-ergonomics/report";
import { SCENE_ERGONOMICS_VERSION, type SceneManualContext, type SceneTaskSequence } from "@/lib/scene-ergonomics/types";
import { validateSceneState } from "@/lib/photo-scene/schema";
import type { SceneState } from "@/types/photo-scene";

const validId=(id:string)=>/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id);

export async function GET(_request:Request,{params}:{params:Promise<{id:string}>}){
  const{id}=await params;if(!validId(id))return NextResponse.json({error:"Nieprawidłowy identyfikator."},{status:400});const{supabase}=await requireUser();
  const{data:scene,error}=await supabase.from("photo_scenes").select("scene_assessment_path,scene_assessment_revision,scene_assessed_at").eq("analysis_id",id).maybeSingle();
  if(error)return NextResponse.json({error:"Nie udało się odczytać metadanych oceny."},{status:500});if(!scene?.scene_assessment_path)return NextResponse.json({assessment:null});
  const{data,error:downloadError}=await supabase.storage.from("analysis-scenes").download(scene.scene_assessment_path);if(downloadError||!data)return NextResponse.json({error:"Nie udało się pobrać prywatnego artefaktu oceny."},{status:500});
  try{return NextResponse.json({assessment:JSON.parse(await data.text()),revision:scene.scene_assessment_revision,assessedAt:scene.scene_assessed_at})}catch{return NextResponse.json({error:"Artefakt oceny ma nieprawidłowy format."},{status:500})}
}

export async function POST(request:Request,{params}:{params:Promise<{id:string}>}){
  const{id}=await params;if(!validId(id))return NextResponse.json({error:"Nieprawidłowy identyfikator."},{status:400});const{supabase,user}=await requireUser();let body:unknown;try{body=await request.json()}catch{return NextResponse.json({error:"Nieprawidłowy JSON."},{status:400})}
  const payload=body as {task?:SceneTaskSequence|null;manual_context?:SceneManualContext};
  const{data:savedScene,error:sceneError}=await supabase.from("photo_scenes").select("scene_state").eq("analysis_id",id).maybeSingle();if(sceneError||!savedScene||!validateSceneState(savedScene.scene_state))return NextResponse.json({error:"Nie można odczytać zapisanego stanu sceny."},{status:422});
  const input=buildSceneErgonomicsInput(id,savedScene.scene_state as SceneState,{task:payload.task??null,manualContext:payload.manual_context});let assessment;try{assessment=assessScene(input)}catch(error){return NextResponse.json({error:error instanceof Error?error.message:"Nie udało się obliczyć oceny."},{status:422})}
  const report=buildSceneDesignReport(input,assessment),base=`${user.id}/${id}/results`,assessmentPath=`${base}/scene-ergonomic-assessment.json`,reportPath=`${base}/scene-design-report.json`,options={contentType:"application/json; charset=utf-8",upsert:true};
  const assessmentBlob=new Blob([JSON.stringify(assessment,null,2)],{type:"application/json"}),reportBlob=new Blob([JSON.stringify(report,null,2)],{type:"application/json"});
  const{error:uploadError}=await supabase.storage.from("analysis-scenes").upload(assessmentPath,assessmentBlob,options);if(uploadError)return NextResponse.json({error:"Nie udało się zapisać artefaktu oceny."},{status:500});
  const{error:reportError}=await supabase.storage.from("analysis-scenes").upload(reportPath,reportBlob,options);if(reportError)return NextResponse.json({error:"Nie udało się zapisać artefaktu raportu."},{status:500});
  const summary={status:assessment.status,quality:assessment.quality,findings:assessment.findings.slice(0,7).map((finding)=>({type:finding.type,priority:finding.priority,humanId:finding.humanId,objectId:finding.objectId})),humanCount:Object.keys(assessment.humans).length,reportPath};
  const{error:updateError}=await supabase.from("photo_scenes").update({scene_assessment_path:assessmentPath,scene_assessment_version:SCENE_ERGONOMICS_VERSION,scene_assessment_revision:assessment.sceneRevision,scene_assessment_summary:summary,scene_assessed_at:assessment.calculatedAt}).eq("analysis_id",id);if(updateError)return NextResponse.json({error:"Artefakt zapisano, ale nie udało się zapisać metadanych."},{status:500});
  return NextResponse.json({assessment,assessmentPath,reportPath});
}
