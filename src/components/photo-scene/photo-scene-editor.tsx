"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Eye, EyeOff, Grid2X2, ImagePlus, LocateFixed, Minus, MousePointer2, Move, Plus, Redo2, RotateCcw, Ruler, Save, Undo2, UserRound } from "lucide-react";

import { localPixelsPerCentimeter, moveJointWithIk } from "@/lib/photo-scene/geometry";
import type { HumanJointName, HumanPose, NormalizedBox, NormalizedPoint, SceneDetection, SceneObject, SceneObjectType, SceneState } from "@/types/photo-scene";

type Tool = "SELECT" | "PAN" | "ADD_OBJECT" | "FLOOR" | "ANCHOR" | "HUMAN";
type Tab = "SCENE" | "OBJECTS" | "HUMAN" | "CALIBRATION";
const objectLabels: Record<SceneObjectType, string> = { WORK_SURFACE:"Powierzchnia robocza", TABLE:"Stół", SHELF:"Półka", RACK:"Regał", CHAIR:"Krzesło", STOOL:"Stołek", CONVEYOR:"Przenośnik", MACHINE:"Maszyna", CONTROL_PANEL:"Panel sterowania", MONITOR:"Monitor", CONTAINER:"Pojemnik", PALLET:"Paleta", OTHER:"Inny" };

export function PhotoSceneEditor(props: { analysisId:string; title:string; imageUrl:string; imageWidth:number; imageHeight:number; initialState:SceneState; detection:SceneDetection|null; processingStage:string|null; detectionError:string|null; lastSavedAt:string }) {
  const initial = useMemo(() => mergeDetections(props.initialState, props.detection), [props.initialState, props.detection]);
  const [state, setState] = useState(initial);
  const [history, setHistory] = useState<SceneState[]>([]);
  const [future, setFuture] = useState<SceneState[]>([]);
  const [tool, setTool] = useState<Tool>("SELECT");
  const [tab, setTab] = useState<Tab>("SCENE");
  const [saveStatus, setSaveStatus] = useState<"SAVED"|"DIRTY"|"SAVING"|"ERROR">("SAVED");
  const [draftStart, setDraftStart] = useState<NormalizedPoint|null>(null);
  const [draftPoint, setDraftPoint] = useState<NormalizedPoint|null>(null);
  const [drag, setDrag] = useState<{ kind:"HUMAN"|"JOINT"|"OBJECT"|"RESIZE"|"PAN"; id?:string; joint?:HumanJointName; start:NormalizedPoint; snapshot:SceneState }|null>(null);
  const canvasRef = useRef<SVGSVGElement|null>(null);
  const latestRef = useRef(state);
  useEffect(() => { latestRef.current = state; }, [state]);

  const commit = useCallback((next: SceneState) => { setHistory((items) => [...items.slice(-49), latestRef.current]); setFuture([]); setState(next); setSaveStatus("DIRTY"); }, []);
  const update = useCallback((producer:(current:SceneState)=>SceneState) => commit(producer(latestRef.current)), [commit]);

  const save = useCallback(async () => {
    setSaveStatus("SAVING");
    const response = await fetch(`/api/photo-scenes/${props.analysisId}`, { method:"PATCH", headers:{"content-type":"application/json"}, body:JSON.stringify({ scene_state: latestRef.current }) });
    setSaveStatus(response.ok ? "SAVED" : "ERROR");
  }, [props.analysisId]);

  useEffect(() => {
    if (saveStatus !== "DIRTY") return;
    const timeout = window.setTimeout(() => void save(), 900);
    return () => window.clearTimeout(timeout);
  }, [save, saveStatus, state]);

  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      const element = event.target as HTMLElement | null;
      if (element?.matches("input, textarea, select")) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") { event.preventDefault(); redo(); }
      if (event.key === "Escape") setState((current) => ({ ...current, selectedObjectId: null }));
      if ((event.key === "Delete" || event.key === "Backspace") && latestRef.current.selectedObjectId) {
        event.preventDefault();
        update((current) => ({ ...current, objects: current.objects.map((object) => object.id === current.selectedObjectId ? { ...object, status: "USER_REJECTED" } : object) }));
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  });

  function point(event: React.PointerEvent<SVGSVGElement>): NormalizedPoint {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: clamp((event.clientX-rect.left)/rect.width), y: clamp((event.clientY-rect.top)/rect.height) };
  }
  function pointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.target !== event.currentTarget && tool !== "ADD_OBJECT" && tool !== "FLOOR" && tool !== "ANCHOR") return;
    const p=point(event); event.currentTarget.setPointerCapture(event.pointerId);
    if (["ADD_OBJECT","FLOOR","ANCHOR"].includes(tool)) { setDraftStart(p); setDraftPoint(p); }
    if (tool === "PAN") setDrag({ kind:"PAN", start:p, snapshot:state });
  }
  function pointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const p=point(event); if (draftStart) setDraftPoint(p);
    if (!drag) return;
    const dx=p.x-drag.start.x, dy=p.y-drag.start.y;
    if (drag.kind==="HUMAN" && drag.snapshot.pose) setState({ ...drag.snapshot, pose:translatePose(drag.snapshot.pose,dx,dy) });
    if (drag.kind==="JOINT" && drag.snapshot.pose && drag.joint) setState({...drag.snapshot,pose:moveJointWithIk(drag.snapshot.pose,drag.joint,p,props.imageWidth/props.imageHeight)});
    if (drag.kind==="PAN") setState({...drag.snapshot,viewport:{...drag.snapshot.viewport,pan_x:drag.snapshot.viewport.pan_x+dx,pan_y:drag.snapshot.viewport.pan_y+dy}});
    if ((drag.kind==="OBJECT"||drag.kind==="RESIZE") && drag.id) setState({...drag.snapshot,objects:drag.snapshot.objects.map((object)=>object.id!==drag.id?object:{...object,bbox:drag.kind==="OBJECT"?{...object.bbox,x:clamp(object.bbox.x+dx,0,1-object.bbox.width),y:clamp(object.bbox.y+dy,0,1-object.bbox.height)}:{...object.bbox,width:Math.max(.02,Math.min(1-object.bbox.x,object.bbox.width+dx)),height:Math.max(.02,Math.min(1-object.bbox.y,object.bbox.height+dy))},status:object.status==="DETECTED"?"USER_MODIFIED":object.status})});
  }
  function pointerUp(event: React.PointerEvent<SVGSVGElement>) {
    const p=point(event);
    if (drag) { setHistory((items)=>[...items.slice(-49),drag.snapshot]); setFuture([]); setDrag(null); setSaveStatus("DIRTY"); }
    if (draftStart) {
      if (tool==="ADD_OBJECT") { const box=boxFromPoints(draftStart,p); if(box.width>.01&&box.height>.01) commit({...state,objects:[...state.objects,newObject(box)],selectedObjectId:null}); }
      if (tool==="FLOOR") commit({...state,calibration:{...state.calibration,floorBaseline:{start:draftStart,end:p},status:state.calibration.anchors.length?"CALIBRATED_2D":"PARTIALLY_CALIBRATED"}});
      if (tool==="ANCHOR") { const real=window.prompt("Rzeczywista wysokość odcinka [cm]"); const cm=Number(real); const pixel=Math.hypot((p.x-draftStart.x)*props.imageWidth,(p.y-draftStart.y)*props.imageHeight); if(Number.isFinite(cm)&&cm>0&&pixel>0) { const next={...state,calibration:{...state.calibration,anchors:[...state.calibration.anchors,{id:crypto.randomUUID(),lower:draftStart,upper:p,pixelDistance:pixel,realDistanceCm:cm,objectId:state.selectedObjectId??null,source:"USER_PROVIDED" as const}],status:(state.calibration.floorBaseline?"CALIBRATED_2D":"PARTIALLY_CALIBRATED") as SceneState["calibration"]["status"]}}; commit(applyHumanScaleLock(next,props.imageHeight)); } }
      setDraftStart(null);setDraftPoint(null);setTool("SELECT");
    }
  }
  function undo(){const previous=history.at(-1);if(!previous)return;setFuture((items)=>[state,...items]);setHistory((items)=>items.slice(0,-1));setState(previous);setSaveStatus("DIRTY");}
  function redo(){const next=future[0];if(!next)return;setHistory((items)=>[...items,state]);setFuture((items)=>items.slice(1));setState(next);setSaveStatus("DIRTY");}

  const selected=state.objects.find((item)=>item.id===state.selectedObjectId)??null;
  const localScale=state.pose?localPixelsPerCentimeter(state.calibration,state.pose.joints.leftHip,props.imageHeight):null;
  const reachRadius=state.human&&localScale ? (state.human.functionalReachCm*localScale)/props.imageHeight : null;

  return <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(320px,3fr)]">
    <section className="ui-card min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
        <ToolButton active={tool==="SELECT"} onClick={()=>setTool("SELECT")} icon={MousePointer2} label="Wybierz"/><ToolButton active={tool==="PAN"} onClick={()=>setTool("PAN")} icon={Move} label="Przesuń widok"/><ToolButton active={tool==="ADD_OBJECT"} onClick={()=>setTool("ADD_OBJECT")} icon={ImagePlus} label="Dodaj element"/><ToolButton active={tool==="FLOOR"} onClick={()=>setTool("FLOOR")} icon={LocateFixed} label="Podłoga"/><ToolButton active={tool==="ANCHOR"} onClick={()=>setTool("ANCHOR")} icon={Ruler} label="Kalibracja"/><ToolButton active={tool==="HUMAN"} onClick={()=>{setTool("HUMAN");setTab("HUMAN");}} icon={UserRound} label="Człowiek"/>
        <span className="mx-1 h-7 w-px bg-border"/><ToolButton disabled={!history.length} onClick={undo} icon={Undo2} label="Cofnij"/><ToolButton disabled={!future.length} onClick={redo} icon={Redo2} label="Ponów"/><ToolButton onClick={()=>update((s)=>({...s,viewport:{...s.viewport,zoom:Math.min(4,s.viewport.zoom+.2)}}))} icon={Plus} label="Powiększ"/><ToolButton onClick={()=>update((s)=>({...s,viewport:{...s.viewport,zoom:Math.max(.5,s.viewport.zoom-.2)}}))} icon={Minus} label="Pomniejsz"/><ToolButton onClick={()=>update((s)=>({...s,viewport:{zoom:1,pan_x:0,pan_y:0}}))} icon={Grid2X2} label="Dopasuj"/>
      </div>
      <div className="relative overflow-auto bg-neutral-950 p-2 sm:p-4">
        <svg ref={canvasRef} viewBox={`0 0 ${props.imageWidth} ${props.imageHeight}`} role="application" aria-label="Edytor sceny ze zdjęcia" className="mx-auto block max-h-[72vh] w-full touch-none select-none" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onWheel={(event)=>{event.preventDefault();setState(s=>({...s,viewport:{...s.viewport,zoom:Math.max(.5,Math.min(4,s.viewport.zoom+(event.deltaY<0?.1:-.1)))}}));setSaveStatus("DIRTY")}} style={{aspectRatio:`${props.imageWidth}/${props.imageHeight}`,transform:`translate(${state.viewport.pan_x*100}%, ${state.viewport.pan_y*100}%) scale(${state.viewport.zoom})`,transformOrigin:"center"}}>
          <image href={props.imageUrl} x="0" y="0" width={props.imageWidth} height={props.imageHeight} pointerEvents="none"/>
          {state.objects.filter((o)=>o.visible&&o.status!=="USER_REJECTED").map((object)=><g key={object.id} onPointerDown={(e)=>{e.stopPropagation();setState((s)=>({...s,selectedObjectId:object.id}));setDrag({kind:"OBJECT",id:object.id,start:pointFromSvg(e),snapshot:state});}}><rect {...svgBox(object.bbox,props.imageWidth,props.imageHeight)} fill="rgba(249,115,22,.10)" stroke={object.id===state.selectedObjectId?"#f97316":"#fafafa"} strokeWidth={object.id===state.selectedObjectId?Math.max(3,props.imageWidth*.003):Math.max(2,props.imageWidth*.0015)}/><text x={object.bbox.x*props.imageWidth+8} y={object.bbox.y*props.imageHeight+20} fill="white" fontSize={Math.max(14,props.imageHeight*.022)} fontWeight="700">{object.name}</text>{object.id===state.selectedObjectId&&<rect x={(object.bbox.x+object.bbox.width)*props.imageWidth-9} y={(object.bbox.y+object.bbox.height)*props.imageHeight-9} width="18" height="18" rx="4" fill="#f97316" onPointerDown={(e)=>{e.stopPropagation();setDrag({kind:"RESIZE",id:object.id,start:pointFromSvg(e),snapshot:state});}}/>}</g>)}
          {state.calibration.floorBaseline&&<line x1={state.calibration.floorBaseline.start.x*props.imageWidth} y1={state.calibration.floorBaseline.start.y*props.imageHeight} x2={state.calibration.floorBaseline.end.x*props.imageWidth} y2={state.calibration.floorBaseline.end.y*props.imageHeight} stroke="#f97316" strokeWidth="4" strokeDasharray="12 8"/>}
          {state.calibration.anchors.map((a)=><g key={a.id}><line x1={a.lower.x*props.imageWidth} y1={a.lower.y*props.imageHeight} x2={a.upper.x*props.imageWidth} y2={a.upper.y*props.imageHeight} stroke="#fff" strokeWidth="4"/><text x={a.upper.x*props.imageWidth+8} y={a.upper.y*props.imageHeight} fill="white" fontSize={Math.max(14,props.imageHeight*.022)}>{a.realDistanceCm} cm</text></g>)}
          {state.pose&&<HumanOverlay pose={state.pose} width={props.imageWidth} height={props.imageHeight} reachRadius={state.reachVisible?reachRadius:null} onStart={(kind,joint,event)=>{event.stopPropagation();setDrag({kind,joint,start:pointFromSvg(event),snapshot:state});}}/>}
          {draftStart&&draftPoint&&<rect {...svgBox(boxFromPoints(draftStart,draftPoint),props.imageWidth,props.imageHeight)} fill="rgba(249,115,22,.12)" stroke="#f97316" strokeWidth="4" strokeDasharray="10 8"/>}
        </svg>
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-3 text-xs text-muted-foreground"><span>Oryginał pozostaje niezmieniony · overlay zapisuje współrzędne 0–1</span><span>{saveStatus==="SAVED"?"Zapisano":saveStatus==="SAVING"?"Zapisywanie…":saveStatus==="DIRTY"?"Niezapisane zmiany":"Błąd zapisu"}</span></footer>
    </section>
    <aside className="ui-card min-w-0 overflow-hidden">
      <nav className="grid grid-cols-2 border-b border-border sm:grid-cols-4 xl:grid-cols-2">{(["SCENE","OBJECTS","HUMAN","CALIBRATION"] as Tab[]).map((item)=><button key={item} onClick={()=>setTab(item)} className={`min-h-11 px-3 text-xs font-bold ${tab===item?"bg-primary/10 text-primary":"text-muted-foreground"}`}>{({SCENE:"Scena",OBJECTS:"Elementy",HUMAN:"Człowiek",CALIBRATION:"Kalibracja"})[item]}</button>)}</nav>
      <div className="max-h-[74vh] space-y-5 overflow-y-auto p-5">
        {tab==="SCENE"&&<ScenePanel analysisId={props.analysisId} title={props.title} state={state} stage={props.processingStage} error={props.detectionError} save={save}/>} 
        {tab==="OBJECTS"&&<ObjectsPanel state={state} selected={selected} update={update}/>} 
        {tab==="HUMAN"&&<HumanPanel state={state} update={update} pixelsPerCm={localScale} imageHeight={props.imageHeight}/>} 
        {tab==="CALIBRATION"&&<CalibrationPanel state={state} setTool={setTool} update={update}/>} 
      </div>
    </aside>
  </div>;
}

function ToolButton({icon:Icon,label,active=false,disabled=false,onClick}:{icon:typeof Move;label:string;active?:boolean;disabled?:boolean;onClick:()=>void}){return <button type="button" title={label} aria-pressed={active} disabled={disabled} onClick={onClick} className={`flex min-h-10 items-center gap-2 rounded-lg px-3 text-xs font-semibold disabled:opacity-30 ${active?"bg-primary text-white":"bg-muted text-foreground hover:bg-primary/10"}`}><Icon className="size-4"/><span className="hidden sm:inline">{label}</span></button>}
function ScenePanel({analysisId,title,state,stage,error,save}:{analysisId:string;title:string;state:SceneState;stage:string|null;error:string|null;save:()=>Promise<void>}){async function retry(){const response=await fetch(`/api/photo-scenes/${analysisId}`,{method:"POST"});if(response.ok)window.location.reload()}return <><div><p className="text-xs uppercase tracking-wider text-muted-foreground">Projekt</p><h2 className="mt-1 text-xl font-bold">{title}</h2></div><dl className="grid grid-cols-2 gap-3 text-sm"><Datum label="Elementy" value={String(state.objects.filter(o=>o.status!=="USER_REJECTED").length)}/><Datum label="Kalibracja" value={calibrationLabel(state.calibration.status)}/><Datum label="Detekcja" value={stageLabel(stage)}/><Datum label="Model" value={state.human?"Dodany":"Brak"}/></dl>{error&&<div className="space-y-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100"><p>Detekcja nie powiodła się: {error}. Możesz zbudować scenę ręcznie.</p><button onClick={()=>void retry()} className="ui-button-secondary w-full justify-center">Ponów detekcję</button></div>}<div className="rounded-xl border border-border bg-muted/50 p-3 text-sm text-muted-foreground">Scena 2D nie zawiera informacji o głębokości i nie wykonuje jeszcze oceny ergonomicznej.</div><button onClick={()=>void save()} className="ui-button-primary w-full justify-center"><Save className="size-4"/>Zapisz teraz</button></>}
function ObjectsPanel({state,selected,update}:{state:SceneState;selected:SceneObject|null;update:(p:(s:SceneState)=>SceneState)=>void}){return <><button onClick={()=>update(s=>({...s,objects:[...s.objects,newObject({x:.25,y:.25,width:.25,height:.2})]}))} className="ui-button-primary w-full justify-center"><Plus className="size-4"/>Dodaj element</button><div className="space-y-2">{state.objects.map((o)=><button key={o.id} onClick={()=>update(s=>({...s,selectedObjectId:o.id}))} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left ${o.id===state.selectedObjectId?"border-primary bg-primary/5":"border-border"}`}><span onClick={(e)=>{e.stopPropagation();update(s=>({...s,objects:s.objects.map(x=>x.id===o.id?{...x,visible:!x.visible}:x)}))}}>{o.visible?<Eye className="size-4"/>:<EyeOff className="size-4"/>}</span><span className="min-w-0 flex-1"><strong className="block truncate text-sm">{o.name}</strong><small className="text-muted-foreground">{objectLabels[o.type]} · {statusLabel(o.status)}</small></span></button>)}</div>{selected&&<div className="space-y-3 border-t border-border pt-4"><label className="text-xs font-semibold">Nazwa<input value={selected.name} onChange={e=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,name:e.target.value,status:"USER_MODIFIED"}:o)}))} className="mt-1 w-full rounded-lg border border-border bg-card p-2"/></label><label className="text-xs font-semibold">Typ<select value={selected.type} onChange={e=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,type:e.target.value as SceneObjectType,status:"USER_MODIFIED"}:o)}))} className="mt-1 w-full rounded-lg border border-border bg-card p-2">{Object.entries(objectLabels).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><div className="grid grid-cols-2 gap-2"><Measurement label="Wysokość [cm]" value={selected.measurements.heightCm} onChange={v=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,measurements:{...o.measurements,heightCm:v}}:o)}))}/><Measurement label="Szerokość [cm]" value={selected.measurements.widthCm} onChange={v=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,measurements:{...o.measurements,widthCm:v}}:o)}))}/><Measurement label="Głębokość [cm]" value={selected.measurements.depthCm} onChange={v=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,measurements:{...o.measurements,depthCm:v}}:o)}))}/><Measurement label="Powierzchnia robocza [cm]" value={selected.measurements.workSurfaceHeightCm} onChange={v=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,measurements:{...o.measurements,workSurfaceHeightCm:v}}:o)}))}/></div>{selected.status==="DETECTED"&&<button onClick={()=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,status:"USER_CONFIRMED"}:o)}))} className="ui-button-primary w-full justify-center">Potwierdź wykrycie</button>}<button onClick={()=>update(s=>({...s,objects:s.objects.map(o=>o.id===selected.id?{...o,status:o.status==="USER_REJECTED"?"USER_MODIFIED":"USER_REJECTED"}:o)}))} className="ui-button-secondary w-full justify-center">{selected.status==="USER_REJECTED"?"Przywróć":"Odrzuć element"}</button></div>}</>}
function HumanPanel({state,update,pixelsPerCm,imageHeight}:{state:SceneState;update:(p:(s:SceneState)=>SceneState)=>void;pixelsPerCm:number|null;imageHeight:number}){
  const human=state.human;
  function create(){update(s=>({...s,human:defaultHuman(),pose:defaultPose("STANDING")}))}
  function humanField<K extends keyof NonNullable<SceneState["human"]>>(key:K,value:NonNullable<SceneState["human"]>[K]){update(s=>{const next={...s,human:s.human?{...s.human,[key]:value}:null};return key==="heightCm"&&typeof value==="number"&&pixelsPerCm&&next.pose?.scaleLocked?{...next,pose:scalePoseHeight(next.pose,(value*pixelsPerCm)/imageHeight)}:next})}
  if(!human)return <><p className="text-sm text-muted-foreground">Wzrost i zasięg są podawane ręcznie. Pozostałe proporcje są tylko wizualnym przybliżeniem.</p><button onClick={create} className="ui-button-primary w-full justify-center"><UserRound className="size-4"/>Dodaj profil człowieka</button></>;
  return <>
    <label className="text-xs font-semibold">Nazwa<input value={human.name} onChange={e=>humanField("name",e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-card p-2"/></label>
    <Measurement label="Wzrost [cm]" value={human.heightCm} required onChange={v=>v&&humanField("heightCm",v)}/>
    <Measurement label="Rozpiętość ramion [cm]" value={human.armSpanCm} required onChange={v=>v&&humanField("armSpanCm",v)}/>
    <Measurement label="Maksymalny zasięg funkcjonalny ręki [cm]" value={human.functionalReachCm} required onChange={v=>v&&humanField("functionalReachCm",v)}/>
    <details className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-xs font-bold">Dodatkowe wymiary</summary><div className="mt-3 grid grid-cols-2 gap-2"><Measurement label="Bark stojąc [cm]" value={human.shoulderHeightCm} onChange={v=>humanField("shoulderHeightCm",v)}/><Measurement label="Łokieć stojąc [cm]" value={human.elbowHeightCm} onChange={v=>humanField("elbowHeightCm",v)}/><Measurement label="Oczy stojąc [cm]" value={human.eyeHeightCm} onChange={v=>humanField("eyeHeightCm",v)}/><Measurement label="Biodro [cm]" value={human.hipHeightCm} onChange={v=>humanField("hipHeightCm",v)}/><Measurement label="Kończyna górna [cm]" value={human.upperLimbLengthCm} onChange={v=>humanField("upperLimbLengthCm",v)}/><Measurement label="Przedramię [cm]" value={human.forearmLengthCm} onChange={v=>humanField("forearmLengthCm",v)}/><Measurement label="Dłoń [cm]" value={human.handLengthCm} onChange={v=>humanField("handLengthCm",v)}/><Measurement label="Kończyna dolna [cm]" value={human.lowerLimbLengthCm} onChange={v=>humanField("lowerLimbLengthCm",v)}/></div></details>
    <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">Wizualne przybliżenie proporcji — możesz uzupełnić dodatkowe wymiary. Dane nie są używane do scoringu.</p>
    <div className="grid grid-cols-2 gap-2">{(["STANDING","SEATED","REACHING"] as const).map(p=><button key={p} onClick={()=>update(s=>({...s,pose:defaultPose(p)}))} className="ui-button-secondary justify-center text-xs">{p==="STANDING"?"Stojąca":p==="SEATED"?"Siedząca":"Sięganie"}</button>)}<button onClick={()=>update(s=>({...s,pose:defaultPose("STANDING")}))} className="ui-button-secondary justify-center text-xs"><RotateCcw className="size-4"/>Resetuj</button></div>
    <div className="grid grid-cols-2 gap-2"><button onClick={()=>update(s=>({...s,pose:s.pose?{...s.pose,mirrored:!s.pose.mirrored,joints:mapJoints(s.pose.joints,p=>({x:1-p.x,y:p.y}))}:null}))} className="ui-button-secondary justify-center text-xs">Odbij postać</button><label className="flex items-center justify-center gap-2 rounded-xl border border-border px-2 text-xs"><input type="checkbox" checked={state.pose?.scaleLocked??true} onChange={e=>update(s=>({...s,pose:s.pose?{...s.pose,scaleLocked:e.target.checked}:null}))}/>Blokada skali</label></div>
    {state.calibration.floorBaseline&&<button onClick={()=>update(s=>({...s,pose:s.pose?snapPoseToFloor(s.pose,s.calibration.floorBaseline!):null}))} className="ui-button-secondary w-full justify-center text-xs"><LocateFixed className="size-4"/>Przyciągnij stopy do podłogi</button>}
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={state.reachVisible??true} onChange={e=>update(s=>({...s,reachVisible:e.target.checked}))}/>Pokaż zasięg lewej i prawej ręki</label>
    {!state.calibration.anchors.length&&<p className="text-xs text-muted-foreground">Do wyświetlenia rzeczywistego zasięgu skalibruj scenę.</p>}
  </>;
}
function CalibrationPanel({state,setTool,update}:{state:SceneState;setTool:(t:Tool)=>void;update:(p:(s:SceneState)=>SceneState)=>void}){return <><Datum label="Status" value={calibrationLabel(state.calibration.status)}/><button onClick={()=>setTool("FLOOR")} className="ui-button-secondary w-full justify-center"><LocateFixed className="size-4"/>Ustaw poziom podłogi</button><button onClick={()=>setTool("ANCHOR")} className="ui-button-primary w-full justify-center"><Ruler className="size-4"/>Dodaj odcinek referencyjny</button><div className="space-y-2">{state.calibration.anchors.map(a=><div key={a.id} className="flex items-center justify-between rounded-xl border border-border p-3 text-sm"><span>{a.realDistanceCm} cm · anchor lokalny</span><button onClick={()=>update(s=>({...s,calibration:{...s.calibration,anchors:s.calibration.anchors.filter(x=>x.id!==a.id),status:s.calibration.anchors.length>1?"PARTIALLY_CALIBRATED":"UNCALIBRATED"}}))} aria-label="Usuń anchor">×</button></div>)}</div><p className="text-xs leading-5 text-muted-foreground">Skala jest liczona lokalnie z maksymalnie trzech najbliższych anchorów. Nie jest traktowana jako jedna globalna skala dla obrazu z perspektywą.</p></>}
function HumanOverlay({pose,width,height,reachRadius,onStart}:{pose:HumanPose;width:number;height:number;reachRadius:number|null;onStart:(kind:"HUMAN"|"JOINT",joint:HumanJointName|undefined,e:React.PointerEvent<SVGElement>)=>void}){const j=pose.joints;const pairs:[HumanJointName,HumanJointName][]=[["head","neck"],["leftShoulder","rightShoulder"],["leftShoulder","leftElbow"],["leftElbow","leftWrist"],["rightShoulder","rightElbow"],["rightElbow","rightWrist"],["leftShoulder","leftHip"],["rightShoulder","rightHip"],["leftHip","rightHip"],["leftHip","leftKnee"],["leftKnee","leftAnkle"],["rightHip","rightKnee"],["rightKnee","rightAnkle"]];const limb=Math.max(10,height*.025);return <g>{reachRadius&&[j.leftShoulder,j.rightShoulder].map((s,i)=><circle key={i} cx={s.x*width} cy={s.y*height} r={reachRadius*height} fill="rgba(249,115,22,.08)" stroke="#f97316" strokeDasharray="10 8"/>)}<polygon points={`${j.leftShoulder.x*width},${j.leftShoulder.y*height} ${j.rightShoulder.x*width},${j.rightShoulder.y*height} ${j.rightHip.x*width},${j.rightHip.y*height} ${j.leftHip.x*width},${j.leftHip.y*height}`} fill="rgba(38,38,38,.70)" stroke="#f97316" strokeWidth="4" onPointerDown={e=>onStart("HUMAN",undefined,e)}/>{pairs.map(([a,b])=><line key={`${a}-${b}`} x1={j[a].x*width} y1={j[a].y*height} x2={j[b].x*width} y2={j[b].y*height} stroke="#262626" strokeWidth={limb} strokeLinecap="round"/>)}<ellipse cx={j.head.x*width} cy={j.head.y*height} rx={Math.max(15,width*.024)} ry={Math.max(20,height*.044)} fill="#262626" stroke="#f97316" strokeWidth="3"/>{Object.entries(j).filter(([name])=>!["head","neck","leftShoulder","rightShoulder","leftHip","rightHip"].includes(name)).map(([name,p])=><circle key={name} cx={p.x*width} cy={p.y*height} r={Math.max(7,height*.014)} fill="#f97316" stroke="white" strokeWidth="3" onPointerDown={e=>onStart("JOINT",name as HumanJointName,e)}/>)}</g>}
function Measurement({label,value,onChange,required=false}:{label:string;value:number|null;onChange:(v:number|null)=>void;required?:boolean}){return <label className="block text-xs font-semibold">{label}<input type="number" min="0.1" step="0.1" required={required} value={value??""} onChange={e=>onChange(e.target.value?Number(e.target.value):null)} className="mt-1 w-full rounded-lg border border-border bg-card p-2"/></label>}
function Datum({label,value}:{label:string;value:string}){return <div className="rounded-xl border border-border p-3"><dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>}
function newObject(bbox:NormalizedBox):SceneObject{return{id:crypto.randomUUID(),sourceClass:null,type:"OTHER",name:"Nowy element",bbox,detectorConfidence:null,source:"USER",status:"USER_ADDED",visible:true,measurements:{heightCm:null,widthCm:null,depthCm:null,workSurfaceHeightCm:null,lowerEdgeHeightCm:null,upperEdgeHeightCm:null},referencePoint:null}}
function mergeDetections(state:SceneState,detection:SceneDetection|null):SceneState{if(!detection||state.objects.length)return state;return{...state,objects:detection.candidates.map(c=>({...newObject(c.bounding_box),id:c.id,sourceClass:c.source_class,type:c.suggested_scene_type,name:objectLabels[c.suggested_scene_type],detectorConfidence:c.confidence,source:c.source,status:"DETECTED"}))}}
function defaultHuman(){return{name:"Operator",heightCm:175,armSpanCm:175,functionalReachCm:70,shoulderHeightCm:null,elbowHeightCm:null,eyeHeightCm:null,hipHeightCm:null,upperLimbLengthCm:null,forearmLengthCm:null,handLengthCm:null,lowerLimbLengthCm:null,geometrySource:"APPROXIMATE_DISPLAY_GEOMETRY" as const}}
function defaultPose(preset:HumanPose["preset"]):HumanPose{const seated=preset==="SEATED",reach=preset==="REACHING";return{preset,mirrored:false,scaleLocked:true,joints:{head:{x:.5,y:.18},neck:{x:.5,y:.24},leftShoulder:{x:.46,y:.27},rightShoulder:{x:.54,y:.27},leftElbow:reach?{x:.37,y:.32}:{x:.43,y:.39},rightElbow:reach?{x:.63,y:.32}:{x:.57,y:.39},leftWrist:reach?{x:.28,y:.31}:{x:.42,y:.5},rightWrist:reach?{x:.72,y:.31}:{x:.58,y:.5},leftHip:{x:.47,y:.5},rightHip:{x:.53,y:.5},leftKnee:seated?{x:.39,y:.59}:{x:.47,y:.68},rightKnee:seated?{x:.61,y:.59}:{x:.53,y:.68},leftAnkle:seated?{x:.39,y:.76}:{x:.46,y:.88},rightAnkle:seated?{x:.61,y:.76}:{x:.54,y:.88}}}}
function mapJoints(joints:HumanPose["joints"],fn:(p:NormalizedPoint)=>NormalizedPoint){return Object.fromEntries(Object.entries(joints).map(([k,v])=>[k,fn(v)])) as HumanPose["joints"]}
function translatePose(pose:HumanPose,dx:number,dy:number){const points=Object.values(pose.joints);const safeDx=Math.max(-Math.min(...points.map(p=>p.x)),Math.min(1-Math.max(...points.map(p=>p.x)),dx));const safeDy=Math.max(-Math.min(...points.map(p=>p.y)),Math.min(1-Math.max(...points.map(p=>p.y)),dy));return{...pose,preset:"CUSTOM" as const,joints:mapJoints(pose.joints,p=>({x:p.x+safeDx,y:p.y+safeDy}))}}
function scalePoseHeight(pose:HumanPose,targetHeight:number){const points=Object.values(pose.joints);const top=Math.min(...points.map(p=>p.y));const bottom=Math.max(pose.joints.leftAnkle.y,pose.joints.rightAnkle.y);const current=Math.max(.001,bottom-top);const ratio=Math.max(.25,Math.min(3,targetHeight/current));const center=(pose.joints.leftHip.x+pose.joints.rightHip.x)/2;return{...pose,joints:mapJoints(pose.joints,p=>({x:clamp(center+(p.x-center)*ratio),y:clamp(bottom-(bottom-p.y)*ratio)}))}}
function applyHumanScaleLock(state:SceneState,imageHeight:number){if(!state.pose?.scaleLocked||!state.human)return state;const scale=localPixelsPerCentimeter(state.calibration,state.pose.joints.leftHip,imageHeight);return scale?{...state,pose:scalePoseHeight(state.pose,(state.human.heightCm*scale)/imageHeight)}:state}
function snapPoseToFloor(pose:HumanPose,floor:NonNullable<SceneState["calibration"]["floorBaseline"]>){const x=(pose.joints.leftAnkle.x+pose.joints.rightAnkle.x)/2;const dx=floor.end.x-floor.start.x;const t=Math.abs(dx)<.0001?.5:(x-floor.start.x)/dx;const floorY=floor.start.y+(floor.end.y-floor.start.y)*t;const ankleY=Math.max(pose.joints.leftAnkle.y,pose.joints.rightAnkle.y);return translatePose(pose,0,floorY-ankleY)}
function boxFromPoints(a:NormalizedPoint,b:NormalizedPoint):NormalizedBox{return{x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(a.x-b.x),height:Math.abs(a.y-b.y)}}
function svgBox(b:NormalizedBox,width:number,height:number){return{x:b.x*width,y:b.y*height,width:b.width*width,height:b.height*height}}
function pointFromSvg(e:React.PointerEvent<SVGElement>):NormalizedPoint{const svg=e.currentTarget.ownerSVGElement;const rect=svg?.getBoundingClientRect();return rect?{x:clamp((e.clientX-rect.left)/rect.width),y:clamp((e.clientY-rect.top)/rect.height)}:{x:0,y:0}}
function clamp(v:number,min=0,max=1){return Math.max(min,Math.min(max,v))}
function calibrationLabel(s:SceneState["calibration"]["status"]){return s==="CALIBRATED_2D"?"Skalibrowana 2D":s==="PARTIALLY_CALIBRATED"?"Częściowo skalibrowana":"Nieskalibrowana"}
function statusLabel(s:SceneObject["status"]){return({DETECTED:"Wykryty przez AI",USER_CONFIRMED:"Potwierdzony",USER_MODIFIED:"Zmieniony",USER_ADDED:"Dodany ręcznie",USER_REJECTED:"Odrzucony"})[s]}
function stageLabel(s:string|null){return s==="scene-ready"?"Gotowa":s==="scene-detection-failed"?"Błąd — tryb ręczny":s==="scene-detection-processing"?"Wykrywanie…":"Oczekuje"}
