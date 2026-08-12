"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Box, ChevronRight, Copy, Eye, EyeOff, Focus, Grid2X2, HelpCircle,
  ImagePlus, LocateFixed, Lock, Minus, MousePointer2, Move, Plus, Redo2, RotateCcw,
  Ruler, Save, Sparkles, Trash2, Undo2, Unlock, UserRound, UsersRound,
} from "lucide-react";

import { HUMAN_PRESETS, createHuman, defaultPose, mapPoints, profileFromHeight, resetHumanPose } from "@/lib/photo-scene/anthropometry";
import { calibrationQuality, calibrationStatus, duplicateReference, estimateLocalScale, referencePixelDistance } from "@/lib/photo-scene/calibration";
import { moveJointWithIk } from "@/lib/photo-scene/geometry";
import { dimensionsFor, objectCompleteness } from "@/lib/photo-scene/object-dimensions";
import { emptyMeasurements, refreshInsights } from "@/lib/photo-scene/schema";
import { missingDimensionSuggestions, sceneCompleteness } from "@/lib/photo-scene/suggestions";
import type {
  CalibrationReference, HumanJointName, HumanPosture, NormalizedBox, NormalizedPoint,
  ObjectDimensionKey, ReferenceDimensionType, SceneDetection, SceneHuman, SceneObject,
  SceneObjectType, SceneState,
} from "@/types/photo-scene";

type Tool = "SELECT" | "PAN" | "ADD_OBJECT" | "FLOOR" | "REFERENCE" | "HUMAN";
type Tab = "SCENE" | "OBJECTS" | "HUMANS" | "DIMENSIONS" | "SUGGESTIONS";
type DraftMeasurement = { start: NormalizedPoint; end: NormalizedPoint; objectId: string | null };
type Drag = { kind: "HUMAN" | "JOINT" | "OBJECT" | "RESIZE" | "PAN"; id?: string; joint?: HumanJointName; start: NormalizedPoint; snapshot: SceneState };

const objectLabels: Record<SceneObjectType, string> = {
  WORK_SURFACE: "Powierzchnia robocza", TABLE: "Stół", SHELF: "Półka", RACK: "Regał",
  CHAIR: "Krzesło", STOOL: "Stołek", CONVEYOR: "Przenośnik", MACHINE: "Maszyna",
  CONTROL_PANEL: "Panel sterowania", MONITOR: "Monitor", CONTAINER: "Pojemnik",
  PALLET: "Paleta", WORK_ZONE: "Strefa robocza", HANDLE: "Uchwyt", OTHER: "Inny",
};
const referenceLabels: Record<ReferenceDimensionType, string> = {
  HEIGHT: "Wysokość", WIDTH: "Szerokość", DEPTH: "Głębokość", DISTANCE: "Odległość",
  WORK_SURFACE_HEIGHT: "Wysokość blatu", SHELF_HEIGHT: "Wysokość półki",
  REACH_HEIGHT: "Wysokość zasięgu", CUSTOM: "Inny wymiar",
};
const humanColors = ["#f97316", "#06b6d4", "#a78bfa", "#84cc16", "#f43f5e"];
const controlClass = "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20";

export function PhotoSceneEditor(props: {
  analysisId: string; title: string; imageUrl: string; imageWidth: number; imageHeight: number;
  initialState: SceneState; detection: SceneDetection | null; processingStage: string | null;
  detectionError: string | null; lastSavedAt: string;
}) {
  const initial = useMemo(() => refreshInsights(mergeDetections(props.initialState, props.detection)), [props.initialState, props.detection]);
  const [state, setState] = useState(initial);
  const [history, setHistory] = useState<SceneState[]>([]), [future, setFuture] = useState<SceneState[]>([]);
  const [tool, setTool] = useState<Tool>("SELECT"), [tab, setTab] = useState<Tab>("SCENE");
  const [saveStatus, setSaveStatus] = useState<"SAVED" | "DIRTY" | "SAVING" | "ERROR">("SAVED");
  const [draftStart, setDraftStart] = useState<NormalizedPoint | null>(null), [draftPoint, setDraftPoint] = useState<NormalizedPoint | null>(null);
  const [draftMeasurement, setDraftMeasurement] = useState<DraftMeasurement | null>(null), [drag, setDrag] = useState<Drag | null>(null);
  const latestRef = useRef(state);
  useEffect(() => { latestRef.current = state; }, [state]);

  const commit = useCallback((next: SceneState) => {
    setHistory((items) => [...items.slice(-49), latestRef.current]); setFuture([]);
    const refreshed = refreshInsights(next); setState(refreshed); latestRef.current = refreshed; setSaveStatus("DIRTY");
  }, []);
  const update = useCallback((producer: (current: SceneState) => SceneState) => commit(producer(latestRef.current)), [commit]);
  const save = useCallback(async () => {
    setSaveStatus("SAVING");
    const response = await fetch(`/api/photo-scenes/${props.analysisId}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ scene_state: latestRef.current }) });
    setSaveStatus(response.ok ? "SAVED" : "ERROR");
  }, [props.analysisId]);
  useEffect(() => { if (saveStatus !== "DIRTY") return; const timeout = window.setTimeout(() => void save(), 900); return () => window.clearTimeout(timeout); }, [save, saveStatus, state]);

  function undo() { const previous = history.at(-1); if (!previous) return; setFuture((items) => [state, ...items]); setHistory((items) => items.slice(0, -1)); setState(previous); setSaveStatus("DIRTY"); }
  function redo() { const next = future[0]; if (!next) return; setHistory((items) => [...items, state]); setFuture((items) => items.slice(1)); setState(next); setSaveStatus("DIRTY"); }
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if ((event.target as HTMLElement | null)?.matches("input, textarea, select")) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") { event.preventDefault(); redo(); }
      if (event.key === "Escape") { setDraftMeasurement(null); setDraftStart(null); setTool("SELECT"); }
      if ((event.key === "Delete" || event.key === "Backspace") && latestRef.current.selectedObjectId) update((current) => ({ ...current, objects: current.objects.map((object) => object.id === current.selectedObjectId ? { ...object, status: "USER_REJECTED" } : object) }));
    }
    window.addEventListener("keydown", keyboard); return () => window.removeEventListener("keydown", keyboard);
  });

  function point(event: React.PointerEvent<SVGSVGElement>): NormalizedPoint { const rect = event.currentTarget.getBoundingClientRect(); return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) }; }
  function pointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.target !== event.currentTarget && !["ADD_OBJECT", "FLOOR", "REFERENCE"].includes(tool)) return;
    const p = point(event); event.currentTarget.setPointerCapture(event.pointerId);
    if (["ADD_OBJECT", "FLOOR", "REFERENCE"].includes(tool)) { setDraftStart(p); setDraftPoint(p); }
    if (tool === "PAN") setDrag({ kind: "PAN", start: p, snapshot: state });
  }
  function pointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const p = point(event); if (draftStart) setDraftPoint(p); if (!drag) return;
    const dx = p.x - drag.start.x, dy = p.y - drag.start.y;
    if (drag.kind === "PAN") setState({ ...drag.snapshot, viewport: { ...drag.snapshot.viewport, pan_x: drag.snapshot.viewport.pan_x + dx, pan_y: drag.snapshot.viewport.pan_y + dy } });
    if ((drag.kind === "OBJECT" || drag.kind === "RESIZE") && drag.id) setState({ ...drag.snapshot, objects: drag.snapshot.objects.map((object) => object.id !== drag.id || object.locked ? object : { ...object, bbox: drag.kind === "OBJECT" ? moveBox(object.bbox, dx, dy) : resizeBox(object.bbox, dx, dy), status: object.status === "DETECTED" ? "USER_MODIFIED" : object.status }) });
    if (drag.kind === "HUMAN" && drag.id) setState(moveHumanInPerspective(drag.snapshot, drag.id, dx, dy, props.imageWidth, props.imageHeight));
    if (drag.kind === "JOINT" && drag.id && drag.joint) setState({ ...drag.snapshot, humans: drag.snapshot.humans.map((human) => human.id === drag.id && !human.locked ? { ...human, pose: moveJointWithIk(human.pose, drag.joint!, p, props.imageWidth / props.imageHeight) } : human) });
  }
  function pointerUp(event: React.PointerEvent<SVGSVGElement>) {
    const p = point(event);
    if (drag) { const next = refreshInsights(state); setState(next); setHistory((items) => [...items.slice(-49), drag.snapshot]); setFuture([]); setDrag(null); setSaveStatus("DIRTY"); }
    if (!draftStart) return;
    if (tool === "ADD_OBJECT") { const bbox = boxFromPoints(draftStart, p); if (bbox.width > .01 && bbox.height > .01) commit({ ...state, objects: [...state.objects, newObject(bbox)] }); }
    if (tool === "FLOOR") commit({ ...state, calibration: { ...state.calibration, floorBaseline: { start: draftStart, end: p } } });
    if (tool === "REFERENCE" && referencePixelDistance(draftStart, p, props.imageWidth, props.imageHeight) > 2) { setDraftMeasurement({ start: draftStart, end: p, objectId: state.selectedObjectId }); setTab("DIMENSIONS"); }
    setDraftStart(null); setDraftPoint(null); if (tool !== "REFERENCE") setTool("SELECT");
  }
  function addReference(input: { name: string; type: ReferenceDimensionType; valueCm: number; affectsScale: boolean }) {
    if (!draftMeasurement || !Number.isFinite(input.valueCm) || input.valueCm <= 0) return;
    const reference: CalibrationReference = { id: crypto.randomUUID(), name: input.name.trim() || referenceLabels[input.type], dimensionType: input.type, valueCm: input.valueCm, unit: "cm", start: draftMeasurement.start, end: draftMeasurement.end, pixelDistance: referencePixelDistance(draftMeasurement.start, draftMeasurement.end, props.imageWidth, props.imageHeight), objectId: draftMeasurement.objectId, active: true, visible: true, locked: false, affectsScale: input.affectsScale, source: "USER_PROVIDED" };
    update((current) => { const calibration = { ...current.calibration, references: [...current.calibration.references, reference] }; calibration.status = calibrationStatus(calibration); return rescaleLockedHumans({ ...current, calibration }, props.imageWidth, props.imageHeight); });
    setDraftMeasurement(null); setTool("SELECT");
  }

  const selectedObject = state.objects.find((object) => object.id === state.selectedObjectId) ?? null;
  const selectedHuman = state.humans.find((human) => human.id === state.selectedHumanId) ?? null;
  const quality = calibrationQuality(state.calibration), completion = sceneCompleteness(state);

  return <div className="grid min-w-0 gap-4 2xl:grid-cols-[minmax(0,1fr)_390px]">
    <section className="ui-card min-w-0 overflow-hidden">
      <Toolbar tool={tool} setTool={setTool} history={history.length} future={future.length} undo={undo} redo={redo} update={update} setTab={setTab} />
      <div className="relative overflow-hidden bg-neutral-950 p-2 sm:p-4">
        <svg viewBox={`0 0 ${props.imageWidth} ${props.imageHeight}`} role="application" aria-label="Edytor sceny ze zdjęcia" className="mx-auto block max-h-[76vh] w-full touch-none select-none" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} style={{ aspectRatio: `${props.imageWidth}/${props.imageHeight}`, transform: `translate(${state.viewport.pan_x * 100}%,${state.viewport.pan_y * 100}%) scale(${state.viewport.zoom})`, transformOrigin: "center" }}>
          <defs><marker id="dimension-arrow" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M7 0L0 3.5L7 7" fill="none" stroke="context-stroke" strokeWidth="1.5" /></marker></defs>
          <image href={props.imageUrl} width={props.imageWidth} height={props.imageHeight} pointerEvents="none" />
          {state.objects.filter((object) => object.visible && object.status !== "USER_REJECTED").map((object) => <ObjectOverlay key={object.id} object={object} selected={object.id === state.selectedObjectId} width={props.imageWidth} height={props.imageHeight} onStart={(kind, event) => { event.stopPropagation(); setState((current) => ({ ...current, selectedObjectId: object.id })); setDrag({ kind, id: object.id, start: pointFromSvg(event), snapshot: state }); }} />)}
          {state.calibration.floorBaseline && <line {...lineProps(state.calibration.floorBaseline.start, state.calibration.floorBaseline.end, props.imageWidth, props.imageHeight)} stroke="#fb923c" strokeWidth="4" strokeDasharray="14 9" />}
          {visibleReferences(state).map((reference) => <MeasurementOverlay key={reference.id} reference={reference} width={props.imageWidth} height={props.imageHeight} selected={reference.id === state.selectedReferenceId} onSelect={() => { setState((current) => ({ ...current, selectedReferenceId: reference.id })); setTab("DIMENSIONS"); }} />)}
          {state.humans.filter((human) => human.visible).map((human) => <HumanOverlay key={human.id} human={human} width={props.imageWidth} height={props.imageHeight} calibration={state.calibration} reachVisible={state.reachVisible} selected={human.id === state.selectedHumanId} onStart={(kind, joint, event) => { event.stopPropagation(); setState((current) => ({ ...current, selectedHumanId: human.id })); setDrag({ kind, id: human.id, joint, start: pointFromSvg(event), snapshot: state }); }} />)}
          {draftStart && draftPoint && <line {...lineProps(draftStart, draftPoint, props.imageWidth, props.imageHeight)} stroke="#f97316" strokeWidth="4" strokeDasharray="12 8" />}
        </svg>
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-border p-3 text-xs text-muted-foreground"><span>Oryginał pozostaje niezmieniony · geometria zapisywana w układzie 0–1</span><span className={saveStatus === "ERROR" ? "text-red-500" : ""}>{saveStatus === "SAVED" ? "Zapisano" : saveStatus === "SAVING" ? "Zapisywanie…" : saveStatus === "DIRTY" ? "Niezapisane zmiany" : "Błąd zapisu"}</span></footer>
    </section>
    <aside className="ui-card min-w-0 overflow-hidden">
      <div className={`border-b px-4 py-3 text-xs font-semibold ${quality === "GOOD" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : quality === "ATTENTION_REQUIRED" ? "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300" : "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300"}`}>{qualityLabel(quality)} · kompletność danych {Math.round(completion.ratio * 100)}%</div>
      <nav className="grid grid-cols-5 border-b border-border">{(["SCENE", "OBJECTS", "HUMANS", "DIMENSIONS", "SUGGESTIONS"] as Tab[]).map((item) => <button key={item} title={tabLabel(item)} aria-pressed={tab === item} onClick={() => setTab(item)} className={`min-h-12 px-1 text-[10px] font-bold sm:text-xs ${tab === item ? "bg-primary/10 text-primary" : "text-muted-foreground"}`}>{tabShortLabel(item)}</button>)}</nav>
      <div className="max-h-[76vh] space-y-5 overflow-y-auto p-4">
        {tab === "SCENE" && <ScenePanel {...props} state={state} quality={quality} completion={completion} save={save} setTab={setTab} />}
        {tab === "OBJECTS" && <ObjectsPanel state={state} selected={selectedObject} update={update} setTool={setTool} setTab={setTab} />}
        {tab === "HUMANS" && <HumansPanel state={state} selected={selectedHuman} update={update} imageWidth={props.imageWidth} imageHeight={props.imageHeight} />}
        {tab === "DIMENSIONS" && <DimensionsPanel state={state} draft={draftMeasurement} addReference={addReference} cancelDraft={() => setDraftMeasurement(null)} update={update} setTool={setTool} />}
        {tab === "SUGGESTIONS" && <SuggestionsPanel state={state} update={update} setTab={setTab} setTool={setTool} />}
      </div>
    </aside>
  </div>;
}

function Toolbar({ tool, setTool, history, future, undo, redo, update, setTab }: { tool: Tool; setTool: (tool: Tool) => void; history: number; future: number; undo: () => void; redo: () => void; update: (fn: (state: SceneState) => SceneState) => void; setTab: (tab: Tab) => void }) {
  return <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
    <ToolbarGroup label="Nawigacja"><ToolButton active={tool === "SELECT"} icon={MousePointer2} label="Wybierz" onClick={() => setTool("SELECT")} /><ToolButton active={tool === "PAN"} icon={Move} label="Przesuń" onClick={() => setTool("PAN")} /></ToolbarGroup>
    <ToolbarGroup label="Dodawanie"><ToolButton active={tool === "ADD_OBJECT"} icon={ImagePlus} label="Obiekt" onClick={() => setTool("ADD_OBJECT")} /><ToolButton active={tool === "HUMAN"} icon={UserRound} label="Człowiek" onClick={() => { setTool("HUMAN"); setTab("HUMANS"); }} /></ToolbarGroup>
    <ToolbarGroup label="Kalibracja"><ToolButton active={tool === "REFERENCE"} icon={Ruler} label="Wymiar" onClick={() => { setTool("REFERENCE"); setTab("DIMENSIONS"); }} /><ToolButton active={tool === "FLOOR"} icon={LocateFixed} label="Podłoga" onClick={() => setTool("FLOOR")} /></ToolbarGroup>
    <ToolbarGroup label="Historia i widok"><ToolButton disabled={!history} icon={Undo2} label="Cofnij" onClick={undo} /><ToolButton disabled={!future} icon={Redo2} label="Ponów" onClick={redo} /><ToolButton icon={Plus} label="Powiększ" onClick={() => update((state) => ({ ...state, viewport: { ...state.viewport, zoom: Math.min(4, state.viewport.zoom + .2) } }))} /><ToolButton icon={Minus} label="Pomniejsz" onClick={() => update((state) => ({ ...state, viewport: { ...state.viewport, zoom: Math.max(.5, state.viewport.zoom - .2) } }))} /><ToolButton icon={Grid2X2} label="Dopasuj" onClick={() => update((state) => ({ ...state, viewport: { zoom: 1, pan_x: 0, pan_y: 0 } }))} /></ToolbarGroup>
  </div>;
}

function ScenePanel({ analysisId, title, state, processingStage, detectionError, quality, completion, save, setTab }: Parameters<typeof PhotoSceneEditor>[0] & { state: SceneState; quality: ReturnType<typeof calibrationQuality>; completion: ReturnType<typeof sceneCompleteness>; save: () => Promise<void>; setTab: (tab: Tab) => void }) {
  async function retry() { const response = await fetch(`/api/photo-scenes/${analysisId}`, { method: "POST" }); if (response.ok) window.location.reload(); }
  return <><div><p className="text-xs uppercase tracking-wider text-muted-foreground">Projekt sceny</p><h2 className="mt-1 text-xl font-bold">{title}</h2></div>
    <div className="grid grid-cols-2 gap-2"><Datum label="Obiekty" value={String(state.objects.filter((object) => object.status !== "USER_REJECTED").length)} /><Datum label="Postacie" value={String(state.humans.length)} /><Datum label="Referencje" value={String(state.calibration.references.length)} /><Datum label="Kalibracja" value={qualityLabel(quality)} /></div>
    {quality !== "GOOD" && <ActionCard icon={Ruler} title="Potrzebna kalibracja" text="Aby poprawnie ustawić postać, dodaj przynajmniej 2–3 wymiary referencyjne w różnych obszarach zdjęcia." action="Przejdź do wymiarów" onClick={() => setTab("DIMENSIONS")} />}
    {completion.missingCritical > 0 && <ActionCard icon={Sparkles} title={`${completion.missingCritical} ważnych danych do uzupełnienia`} text="System przygotował sugestie na podstawie potwierdzonych obiektów." action="Pokaż sugestie" onClick={() => setTab("SUGGESTIONS")} />}
    {detectionError && <div className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm"><p>Detekcja nie powiodła się. Scenę można zbudować ręcznie.</p><button onClick={() => void retry()} className="ui-button-secondary mt-3 w-full justify-center">Ponów detekcję</button></div>}
    <p className="rounded-xl border border-border bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">To techniczny model 2D/pseudo-2.5D. Nie wykonuje oceny ergonomicznej ani nie odtwarza niewidocznej głębokości.</p>
    <button onClick={() => void save()} className="ui-button-primary w-full justify-center"><Save className="size-4" />Zapisz teraz</button>
    <p className="text-center text-[11px] text-muted-foreground">Etap: {stageLabel(processingStage)}</p></>;
}

function ObjectsPanel({ state, selected, update, setTool, setTab }: { state: SceneState; selected: SceneObject | null; update: (fn: (state: SceneState) => SceneState) => void; setTool: (tool: Tool) => void; setTab: (tab: Tab) => void }) {
  return <><button onClick={() => update((state) => ({ ...state, objects: [...state.objects, newObject({ x: .25, y: .25, width: .25, height: .2 })] }))} className="ui-button-primary w-full justify-center"><Plus className="size-4" />Dodaj obiekt</button>
    <div className="space-y-2">{state.objects.map((object) => { const completeness = objectCompleteness(object.type, object.measurements); return <button key={object.id} onClick={() => update((state) => ({ ...state, selectedObjectId: object.id }))} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left ${object.id === state.selectedObjectId ? "border-primary bg-primary/5" : "border-border"}`}><Box className="size-4 shrink-0" /><span className="min-w-0 flex-1"><strong className="block truncate text-sm">{object.name}</strong><small className="text-muted-foreground">{objectLabels[object.type]} · {Math.round(completeness.ratio * 100)}% danych</small></span><ChevronRight className="size-4" /></button>; })}</div>
    {selected && <div className="space-y-3 border-t border-border pt-4">
      <Field label="Nazwa"><input value={selected.name} onChange={(event) => updateObject(update, selected.id, { name: event.target.value, status: "USER_MODIFIED" })} className={controlClass} /></Field>
      <Field label="Typ"><select value={selected.type} onChange={(event) => updateObject(update, selected.id, { type: event.target.value as SceneObjectType, status: "USER_MODIFIED" })} className={controlClass}>{Object.entries(objectLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field>
      <div className="grid grid-cols-2 gap-2">{dimensionsFor(selected.type).map((definition) => <NumberField key={definition.key} label={`${definition.label} [cm]`} value={selected.measurements[definition.key]} onChange={(value) => updateMeasurement(update, selected.id, definition.key, value)} />)}</div>
      <div className="grid grid-cols-2 gap-2"><button onClick={() => updateObject(update, selected.id, { visible: !selected.visible })} className="ui-button-secondary justify-center">{selected.visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}{selected.visible ? "Ukryj" : "Pokaż"}</button><button onClick={() => updateObject(update, selected.id, { locked: !selected.locked })} className="ui-button-secondary justify-center">{selected.locked ? <Unlock className="size-4" /> : <Lock className="size-4" />}{selected.locked ? "Odblokuj" : "Zablokuj"}</button></div>
      <button onClick={() => { setTool("REFERENCE"); setTab("DIMENSIONS"); }} className="ui-button-secondary w-full justify-center"><Ruler className="size-4" />Narysuj wymiar dla obiektu</button>
      {selected.status === "DETECTED" && <button onClick={() => updateObject(update, selected.id, { status: "USER_CONFIRMED" })} className="ui-button-primary w-full justify-center">Potwierdź wykrycie</button>}
      <button onClick={() => updateObject(update, selected.id, { status: selected.status === "USER_REJECTED" ? "USER_MODIFIED" : "USER_REJECTED" })} className="ui-button-secondary w-full justify-center"><Trash2 className="size-4" />{selected.status === "USER_REJECTED" ? "Przywróć" : "Odrzuć obiekt"}</button>
    </div>}</>;
}

function HumansPanel({ state, selected, update, imageWidth, imageHeight }: { state: SceneState; selected: SceneHuman | null; update: (fn: (state: SceneState) => SceneState) => void; imageWidth: number; imageHeight: number }) {
  function add(preset: keyof typeof HUMAN_PRESETS = "MEDIUM") { const human = createHuman(`Operator ${state.humans.length + 1}`, humanColors[state.humans.length % humanColors.length], preset); update((state) => ({ ...state, humans: [...state.humans, human], selectedHumanId: human.id })); }
  return <><div className="grid grid-cols-3 gap-2">{Object.entries(HUMAN_PRESETS).map(([id, profile]) => <button key={id} onClick={() => add(id as keyof typeof HUMAN_PRESETS)} className="rounded-xl border border-border p-2 text-xs font-semibold hover:border-primary"><span className="block">{profile.label}</span><small className="text-muted-foreground">{profile.heightCm} cm</small></button>)}</div>
    <button onClick={() => add()} className="ui-button-primary w-full justify-center"><UsersRound className="size-4" />Dodaj kolejną postać</button>
    <div className="space-y-2">{state.humans.map((human) => <button key={human.id} onClick={() => update((state) => ({ ...state, selectedHumanId: human.id }))} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left ${human.id === state.selectedHumanId ? "border-primary bg-primary/5" : "border-border"}`}><span className="size-3 rounded-full" style={{ background: human.color }} /><span className="flex-1 text-sm font-semibold">{human.name}</span><small>{human.profile.heightCm} cm</small></button>)}</div>
    {selected && <HumanEditor human={selected} state={state} update={update} imageWidth={imageWidth} imageHeight={imageHeight} />}</>;
}

function HumanEditor({ human, state, update, imageWidth, imageHeight }: { human: SceneHuman; state: SceneState; update: (fn: (state: SceneState) => SceneState) => void; imageWidth: number; imageHeight: number }) {
  const scale = estimateLocalScale(state.calibration, human.placement.contactPoint, imageWidth, imageHeight);
  function patchHuman(patch: Partial<SceneHuman>) { update((state) => ({ ...state, humans: state.humans.map((item) => item.id === human.id ? { ...item, ...patch } : item) })); }
  function setHeight(value: number | null) { if (!value) return; const profile = { ...profileFromHeight(human.profile.name, value, "CUSTOM"), name: human.profile.name }; update((state) => rescaleLockedHumans({ ...state, humans: state.humans.map((item) => item.id === human.id ? { ...item, profile } : item) }, imageWidth, imageHeight)); }
  function toggleFloorPin(enabled: boolean) { update((state) => ({ ...state, humans: state.humans.map((item) => item.id === human.id ? snapHumanToFloor({ ...item, placement: { ...item.placement, floorPinned: enabled } }, state.calibration.floorBaseline) : item) })); }
  function attachToObject(objectId: string) { update((state) => { const object = state.objects.find((item) => item.id === objectId); if (!object) return { ...state, humans: state.humans.map((item) => item.id === human.id ? { ...item, placement: { ...item.placement, attachedObjectId: null, attachmentMode: "NONE" } } : item) }; const target = { x: clamp(object.bbox.x - .04), y: clamp(object.bbox.y + object.bbox.height) }; const current = human.placement.contactPoint, moved = { ...human, pose: translatePose(human.pose, target.x - current.x, target.y - current.y), placement: { ...human.placement, contactPoint: target, attachedObjectId: objectId, attachmentMode: human.pose.preset === "SEATED" ? "SEATED_AT_OBJECT" as const : "WORK_SURFACE" as const } }; return { ...state, humans: state.humans.map((item) => item.id === human.id ? scaleHumanAtPosition(moved, state.calibration, imageWidth, imageHeight) : item) }; }); }
  return <div className="space-y-3 border-t border-border pt-4"><Field label="Nazwa"><input value={human.name} onChange={(event) => patchHuman({ name: event.target.value, profile: { ...human.profile, name: event.target.value } })} className={controlClass} /></Field>
    <div className="grid grid-cols-2 gap-2"><NumberField label="Wzrost [cm]" value={human.profile.heightCm} onChange={setHeight} /><NumberField label="Rozpiętość ramion [cm]" value={human.profile.armSpanCm} onChange={(value) => value && patchHuman({ profile: { ...human.profile, armSpanCm: value, preset: "CUSTOM" } })} /><NumberField label="Zasięg komfortowy [cm]" value={human.profile.functionalReachCm} onChange={(value) => value && patchHuman({ profile: { ...human.profile, functionalReachCm: value } })} /><NumberField label="Zasięg maksymalny [cm]" value={human.profile.maximumReachCm} onChange={(value) => value && patchHuman({ profile: { ...human.profile, maximumReachCm: value } })} /></div>
    <details className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-xs font-semibold">Dodatkowe wymiary antropometryczne</summary><div className="mt-3 grid grid-cols-2 gap-2">{([['shoulderHeightCm','Wysokość barku'],['hipHeightCm','Wysokość biodra'],['upperArmLengthCm','Długość ramienia'],['forearmLengthCm','Długość przedramienia'],['handLengthCm','Długość dłoni'],['thighLengthCm','Długość uda'],['lowerLegLengthCm','Długość podudzia']] as const).map(([key,label]) => <NumberField key={key} label={`${label} [cm]`} value={human.profile[key]} onChange={(value) => patchHuman({ profile: { ...human.profile, [key]: value, preset: "CUSTOM", geometrySource: "USER_MEASUREMENTS" } })} />)}</div></details>
    <Field label="Postawa"><select value={human.pose.preset} onChange={(event) => patchHuman({ pose: defaultPose(event.target.value as HumanPosture) })} className={controlClass}>{postureOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
    <div className="rounded-xl border border-border p-3 text-xs"><strong>Skala lokalna</strong><p className="mt-1 text-muted-foreground">{scale ? `${scale.pixelsPerCm.toFixed(2)} px/cm · ${scale.confidence.toLowerCase()} · ${scale.referencesUsed.length} referencje` : "Brak danych — model ma wyłącznie skalę poglądową"}</p></div>
    <div className="grid grid-cols-2 gap-2"><button onClick={() => patchHuman({ pose: resetHumanPose(human).pose })} className="ui-button-secondary justify-center"><RotateCcw className="size-4" />Naturalna postawa</button><button onClick={() => patchHuman({ pose: defaultPose(human.pose.preset) })} className="ui-button-secondary justify-center"><Focus className="size-4" />Wyzeruj kończyny</button></div>
    <label className="flex items-center gap-2 rounded-xl border border-border p-3 text-xs"><input type="checkbox" checked={human.placement.floorPinned} onChange={(event) => toggleFloorPin(event.target.checked)} />Przypnij stopy do podłogi</label>
    <Field label="Ustaw przy obiekcie"><select value={human.placement.attachedObjectId ?? ""} onChange={(event) => attachToObject(event.target.value)} className={controlClass}><option value="">Brak</option>{state.objects.filter((object) => object.status !== "USER_REJECTED").map((object) => <option key={object.id} value={object.id}>{object.name}</option>)}</select></Field>
    <div className="grid grid-cols-2 gap-2"><button onClick={() => patchHuman({ visible: !human.visible })} className="ui-button-secondary justify-center">{human.visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}{human.visible ? "Ukryj" : "Pokaż"}</button><button onClick={() => patchHuman({ locked: !human.locked })} className="ui-button-secondary justify-center">{human.locked ? <Unlock className="size-4" /> : <Lock className="size-4" />}{human.locked ? "Odblokuj" : "Zablokuj"}</button></div>
    <button onClick={() => update((state) => ({ ...state, humans: state.humans.filter((item) => item.id !== human.id), selectedHumanId: null }))} className="ui-button-secondary w-full justify-center"><Trash2 className="size-4" />Usuń postać</button>
  </div>;
}

function DimensionsPanel({ state, draft, addReference, cancelDraft, update, setTool }: { state: SceneState; draft: DraftMeasurement | null; addReference: (input: { name: string; type: ReferenceDimensionType; valueCm: number; affectsScale: boolean }) => void; cancelDraft: () => void; update: (fn: (state: SceneState) => SceneState) => void; setTool: (tool: Tool) => void }) {
  return <><div className="grid grid-cols-2 gap-2"><button onClick={() => setTool("REFERENCE")} className="ui-button-primary justify-center"><Ruler className="size-4" />Nowy wymiar</button><button onClick={() => setTool("FLOOR")} className="ui-button-secondary justify-center"><LocateFixed className="size-4" />Podłoga</button></div>
    <p className="text-xs leading-5 text-muted-foreground">Narysuj odcinek na zdjęciu, a następnie opisz jego rodzaj i rzeczywistą długość. Referencje z różnych miejsc budują lokalny model skali.</p>
    {draft && <ReferenceDraftForm objectName={state.objects.find((object) => object.id === draft.objectId)?.name ?? null} add={addReference} cancel={cancelDraft} />}
    <Field label="Widoczne pomiary"><select value={state.measurementFilter} onChange={(event) => update((state) => ({ ...state, measurementFilter: event.target.value as SceneState["measurementFilter"] }))} className={controlClass}><option value="ALL">Wszystkie</option><option value="ACTIVE">Tylko aktywne</option><option value="SELECTED_OBJECT">Wybrany obiekt</option><option value="CALIBRATION">Tylko kalibracja</option></select></Field>
    <div className="space-y-2">{state.calibration.references.map((reference) => <ReferenceCard key={reference.id} reference={reference} update={update} />)}</div>
    {!state.calibration.references.length && <EmptyState text="Brak wymiarów. Zacznij od wysokości blatu oraz pionowej referencji blisko planowanego ustawienia postaci." />}</>;
}

function ReferenceDraftForm({ objectName, add, cancel }: { objectName: string | null; add: (input: { name: string; type: ReferenceDimensionType; valueCm: number; affectsScale: boolean }) => void; cancel: () => void }) {
  const [name, setName] = useState(objectName ? `Wymiar: ${objectName}` : ""), [type, setType] = useState<ReferenceDimensionType>("HEIGHT"), [value, setValue] = useState(""), [affectsScale, setAffectsScale] = useState(true);
  return <div className="space-y-3 rounded-xl border-2 border-primary/40 bg-primary/5 p-3"><h3 className="font-semibold">Opisz narysowany wymiar</h3><Field label="Nazwa"><input value={name} onChange={(event) => setName(event.target.value)} className={controlClass} /></Field><Field label="Typ"><select value={type} onChange={(event) => setType(event.target.value as ReferenceDimensionType)} className={controlClass}>{Object.entries(referenceLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field><NumberField label="Wartość [cm]" value={value ? Number(value) : null} onChange={(next) => setValue(next ? String(next) : "")} /><label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={affectsScale} onChange={(event) => setAffectsScale(event.target.checked)} />Wpływa na lokalną skalę</label><div className="grid grid-cols-2 gap-2"><button onClick={cancel} className="ui-button-secondary justify-center">Anuluj</button><button disabled={!value || Number(value) <= 0} onClick={() => add({ name, type, valueCm: Number(value), affectsScale })} className="ui-button-primary justify-center">Dodaj</button></div></div>;
}

function ReferenceCard({ reference, update }: { reference: CalibrationReference; update: (fn: (state: SceneState) => SceneState) => void }) {
  function patch(next: Partial<CalibrationReference>) { update((state) => { const calibration = { ...state.calibration, references: state.calibration.references.map((item) => item.id === reference.id ? { ...item, ...next } : item) }; calibration.status = calibrationStatus(calibration); return { ...state, calibration }; }); }
  return <div className="space-y-2 rounded-xl border border-border p-3"><div className="flex items-start gap-2"><button onClick={() => patch({ visible: !reference.visible })}>{reference.visible ? <Eye className="size-4" /> : <EyeOff className="size-4" />}</button><div className="min-w-0 flex-1"><input value={reference.name} onChange={(event) => patch({ name: event.target.value })} className="w-full bg-transparent text-sm font-semibold outline-none" /><small className="text-muted-foreground">{referenceLabels[reference.dimensionType]} · {reference.valueCm} cm</small></div><button onClick={() => patch({ locked: !reference.locked })}>{reference.locked ? <Lock className="size-4" /> : <Unlock className="size-4" />}</button></div><div className="flex flex-wrap gap-2 text-[11px]"><label><input type="checkbox" checked={reference.active} onChange={(event) => patch({ active: event.target.checked })} /> aktywny</label><label><input type="checkbox" checked={reference.affectsScale} onChange={(event) => patch({ affectsScale: event.target.checked })} /> wpływa na skalę</label></div><div className="grid grid-cols-2 gap-2"><button onClick={() => update((state) => ({ ...state, calibration: { ...state.calibration, references: [...state.calibration.references, duplicateReference(reference)] } }))} className="ui-button-secondary justify-center text-xs"><Copy className="size-3" />Duplikuj</button><button onClick={() => update((state) => ({ ...state, calibration: { ...state.calibration, references: state.calibration.references.filter((item) => item.id !== reference.id) } }))} className="ui-button-secondary justify-center text-xs"><Trash2 className="size-3" />Usuń</button></div></div>;
}

function SuggestionsPanel({ state, update, setTab, setTool }: { state: SceneState; update: (fn: (state: SceneState) => SceneState) => void; setTab: (tab: Tab) => void; setTool: (tool: Tool) => void }) {
  const suggestions = missingDimensionSuggestions(state), completion = sceneCompleteness(state);
  return <><div className="rounded-xl border border-border p-4"><div className="flex items-center justify-between"><strong>Kompletność sceny</strong><span className="text-lg font-bold text-primary">{Math.round(completion.ratio * 100)}%</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${completion.ratio * 100}%` }} /></div><p className="mt-2 text-xs text-muted-foreground">{completion.completed} z {completion.total} kluczowych wymiarów</p></div>
    <div className="space-y-2">{suggestions.map((suggestion) => <button key={suggestion.id} onClick={() => { update((state) => ({ ...state, selectedObjectId: suggestion.objectId })); setTab("OBJECTS"); setTool("REFERENCE"); }} className="w-full rounded-xl border border-border p-3 text-left hover:border-primary"><span className={`text-[10px] font-bold uppercase ${suggestion.priority === "CRITICAL" ? "text-red-500" : suggestion.priority === "RECOMMENDED" ? "text-amber-500" : "text-muted-foreground"}`}>{priorityLabel(suggestion.priority)}</span><p className="mt-1 text-sm">{suggestion.message}</p><small className="mt-2 inline-flex items-center gap-1 text-primary">Wskaż wymiar <ChevronRight className="size-3" /></small></button>)}</div>
    {!suggestions.length && <EmptyState text="Wszystkie sugerowane wymiary zostały uzupełnione." />}
    {state.technicalInsights.filter((insight) => insight.code !== "MISSING_OBJECT_DIMENSION").map((insight) => <div key={insight.id} className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs"><AlertTriangle className="size-4 shrink-0" />{insight.message}</div>)}</>;
}

function HumanOverlay({ human, width, height, calibration, reachVisible, selected, onStart }: { human: SceneHuman; width: number; height: number; calibration: SceneState["calibration"]; reachVisible: boolean; selected: boolean; onStart: (kind: "HUMAN" | "JOINT", joint: HumanJointName | undefined, event: React.PointerEvent<SVGElement>) => void }) {
  const j = human.pose.joints, scale = estimateLocalScale(calibration, human.placement.contactPoint, width, height)?.pixelsPerCm ?? null;
  const radii = scale ? { comfort: human.profile.functionalReachCm * scale, functional: human.profile.maximumReachCm * .9 * scale, maximum: human.profile.maximumReachCm * scale } : null;
  const torso = `${j.leftShoulder.x * width},${j.leftShoulder.y * height} ${j.rightShoulder.x * width},${j.rightShoulder.y * height} ${j.rightHip.x * width},${j.rightHip.y * height} ${j.leftHip.x * width},${j.leftHip.y * height}`;
  const limbs: [HumanJointName, HumanJointName, number][] = [["leftShoulder","leftElbow",.022],["leftElbow","leftWrist",.017],["rightShoulder","rightElbow",.022],["rightElbow","rightWrist",.017],["leftHip","leftKnee",.03],["leftKnee","leftAnkle",.023],["rightHip","rightKnee",.03],["rightKnee","rightAnkle",.023]];
  const armWarning = human.pose.reachState.leftArm === "OUT_OF_REACH" || human.pose.reachState.rightArm === "OUT_OF_REACH";
  return <g opacity={human.locked ? .75 : 1}>
    {reachVisible && radii && [j.leftShoulder, j.rightShoulder].map((shoulder, index) => <g key={index}><circle cx={shoulder.x * width} cy={shoulder.y * height} r={radii.maximum} fill={`${human.color}0a`} stroke={human.color} strokeOpacity=".35" strokeDasharray="12 10" /><circle cx={shoulder.x * width} cy={shoulder.y * height} r={radii.functional} fill="none" stroke={human.color} strokeOpacity=".55" strokeDasharray="7 7" /><circle cx={shoulder.x * width} cy={shoulder.y * height} r={radii.comfort} fill={`${human.color}12`} stroke={human.color} strokeOpacity=".8" /></g>)}
    <polygon points={torso} fill="#172033" stroke={selected ? human.color : "#cbd5e1"} strokeWidth={selected ? 5 : 3} onPointerDown={(event) => onStart("HUMAN", undefined, event)} />
    {limbs.map(([a, b, thickness]) => <g key={`${a}-${b}`}><line {...lineProps(j[a], j[b], width, height)} stroke="#0f172a" strokeWidth={Math.max(10, height * thickness)} strokeLinecap="round" /><line {...lineProps(j[a], j[b], width, height)} stroke={human.color} strokeOpacity=".55" strokeWidth={Math.max(2, height * thickness * .18)} strokeLinecap="round" /></g>)}
    <ellipse cx={j.head.x * width} cy={j.head.y * height} rx={Math.max(15, height * .025)} ry={Math.max(22, height * .043)} fill="#172033" stroke={human.color} strokeWidth="3" />
    <line {...lineProps(j.leftWrist, j.leftHand, width, height)} stroke={armWarning ? "#ef4444" : "#0f172a"} strokeWidth={Math.max(7, height * .012)} strokeLinecap="round" /><line {...lineProps(j.rightWrist, j.rightHand, width, height)} stroke={armWarning ? "#ef4444" : "#0f172a"} strokeWidth={Math.max(7, height * .012)} strokeLinecap="round" />
    {(["leftHand", "rightHand"] as HumanJointName[]).map((name) => <ellipse key={name} cx={j[name].x * width} cy={j[name].y * height} rx={Math.max(7, height * .012)} ry={Math.max(4, height * .007)} fill={human.color} stroke="white" strokeWidth="2" onPointerDown={(event) => onStart("JOINT", name, event)} />)}
    {["leftFoot", "rightFoot"].map((name) => { const foot = j[name as HumanJointName]; return <ellipse key={name} cx={foot.x * width} cy={foot.y * height} rx={Math.max(13, height * .022)} ry={Math.max(5, height * .009)} fill="#0f172a" stroke={human.color} strokeWidth="2" />; })}
    {(["leftWrist", "rightWrist", "leftAnkle", "rightAnkle"] as HumanJointName[]).map((name) => <circle key={name} cx={j[name].x * width} cy={j[name].y * height} r={Math.max(7, height * .011)} fill={human.pose.reachState[name.startsWith("left") ? name.includes("Wrist") ? "leftArm" : "leftLeg" : name.includes("Wrist") ? "rightArm" : "rightLeg"] === "OUT_OF_REACH" ? "#ef4444" : human.color} stroke="white" strokeWidth="3" onPointerDown={(event) => onStart("JOINT", name, event)} />)}
    {armWarning && <text x={j.neck.x * width + 12} y={j.neck.y * height - 12} fill="#ef4444" fontSize={Math.max(13, height * .018)} fontWeight="700">Poza naturalnym zasięgiem</text>}
  </g>;
}

function ObjectOverlay({ object, selected, width, height, onStart }: { object: SceneObject; selected: boolean; width: number; height: number; onStart: (kind: "OBJECT" | "RESIZE", event: React.PointerEvent<SVGElement>) => void }) { return <g><rect {...svgBox(object.bbox, width, height)} fill="rgba(249,115,22,.10)" stroke={selected ? "#f97316" : "#f8fafc"} strokeWidth={selected ? 4 : 2} onPointerDown={(event) => onStart("OBJECT", event)} /><rect x={object.bbox.x * width + 4} y={object.bbox.y * height + 4} width={Math.max(80, object.name.length * 8)} height="25" rx="5" fill="rgba(15,23,42,.88)" /><text x={object.bbox.x * width + 10} y={object.bbox.y * height + 21} fill="white" fontSize="14" fontWeight="700">{object.name}</text>{selected && !object.locked && <rect x={(object.bbox.x + object.bbox.width) * width - 10} y={(object.bbox.y + object.bbox.height) * height - 10} width="20" height="20" rx="4" fill="#f97316" onPointerDown={(event) => onStart("RESIZE", event)} />}</g>; }
function MeasurementOverlay({ reference, width, height, selected, onSelect }: { reference: CalibrationReference; width: number; height: number; selected: boolean; onSelect: () => void }) { const color = reference.dimensionType === "HEIGHT" || reference.dimensionType === "WORK_SURFACE_HEIGHT" ? "#22d3ee" : reference.dimensionType === "DEPTH" ? "#a78bfa" : "#fbbf24"; const middle = { x: (reference.start.x + reference.end.x) / 2 * width, y: (reference.start.y + reference.end.y) / 2 * height }; return <g onPointerDown={(event) => { event.stopPropagation(); onSelect(); }} opacity={reference.active ? 1 : .45}><line {...lineProps(reference.start, reference.end, width, height)} stroke={color} strokeWidth={selected ? 5 : 3} markerStart="url(#dimension-arrow)" markerEnd="url(#dimension-arrow)" /><rect x={middle.x - 48} y={middle.y - 25} width="96" height="22" rx="6" fill="rgba(15,23,42,.92)" /><text x={middle.x} y={middle.y - 9} textAnchor="middle" fill="white" fontSize="13" fontWeight="700">{reference.valueCm} cm</text></g>; }

function visibleReferences(state: SceneState) { return state.calibration.references.filter((reference) => reference.visible && (state.measurementFilter === "ALL" || state.measurementFilter === "ACTIVE" && reference.active || state.measurementFilter === "SELECTED_OBJECT" && reference.objectId === state.selectedObjectId || state.measurementFilter === "CALIBRATION" && reference.affectsScale)); }
function moveHumanInPerspective(state: SceneState, id: string, dx: number, dy: number, width: number, height: number) { const humans = state.humans.map((human) => { if (human.id !== id || human.locked) return human; const movedPose = translatePose(human.pose, dx, dy), moved = { ...human, pose: movedPose, placement: { ...human.placement, contactPoint: { x: clamp(human.placement.contactPoint.x + dx), y: clamp(human.placement.contactPoint.y + dy) } } }; return snapHumanToFloor(scaleHumanAtPosition(moved, state.calibration, width, height), state.calibration.floorBaseline); }); return { ...state, humans }; }
function scaleHumanAtPosition(human: SceneHuman, calibration: SceneState["calibration"], width: number, height: number) { if (!human.pose.scaleLocked) return human; const scale = estimateLocalScale(calibration, human.placement.contactPoint, width, height); if (!scale) return human; return { ...human, pose: scalePoseHeight(human.pose, human.profile.heightCm * scale.pixelsPerCm / height) }; }
function rescaleLockedHumans(state: SceneState, width: number, height: number) { return { ...state, humans: state.humans.map((human) => scaleHumanAtPosition(human, state.calibration, width, height)) }; }
function scalePoseHeight(pose: SceneHuman["pose"], targetHeight: number) { const points = Object.values(pose.joints), top = Math.min(...points.map((point) => point.y)), bottom = Math.max(pose.joints.leftFoot.y, pose.joints.rightFoot.y), current = Math.max(.001, bottom - top), ratio = clamp(targetHeight / current, .35, 2.5), center = (pose.joints.leftHip.x + pose.joints.rightHip.x) / 2; return { ...pose, joints: mapPoints(pose.joints, (point) => ({ x: clamp(center + (point.x - center) * ratio), y: clamp(bottom - (bottom - point.y) * ratio) })) }; }
function snapHumanToFloor(human: SceneHuman, floor: SceneState["calibration"]["floorBaseline"]) { if (!floor || !human.placement.floorPinned) return human; const contact = human.placement.contactPoint, dx = floor.end.x - floor.start.x, ratio = Math.abs(dx) < .0001 ? .5 : (contact.x - floor.start.x) / dx, floorY = floor.start.y + (floor.end.y - floor.start.y) * ratio, dy = floorY - contact.y; return { ...human, pose: translatePose(human.pose, 0, dy), placement: { ...human.placement, contactPoint: { x: contact.x, y: floorY } } }; }
function translatePose(pose: SceneHuman["pose"], dx: number, dy: number) { const points = Object.values(pose.joints), safeDx = Math.max(-Math.min(...points.map((point) => point.x)), Math.min(1 - Math.max(...points.map((point) => point.x)), dx)), safeDy = Math.max(-Math.min(...points.map((point) => point.y)), Math.min(1 - Math.max(...points.map((point) => point.y)), dy)); return { ...pose, preset: "CUSTOM" as const, joints: mapPoints(pose.joints, (point) => ({ x: point.x + safeDx, y: point.y + safeDy })) }; }
function newObject(bbox: NormalizedBox): SceneObject { return { id: crypto.randomUUID(), sourceClass: null, type: "OTHER", name: "Nowy element", bbox, detectorConfidence: null, source: "USER", status: "USER_ADDED", visible: true, locked: false, measurements: emptyMeasurements(), referencePoint: null }; }
function mergeDetections(state: SceneState, detection: SceneDetection | null): SceneState { if (!detection || state.objects.length) return state; return { ...state, objects: detection.candidates.map((candidate) => ({ ...newObject(candidate.bounding_box), id: candidate.id, sourceClass: candidate.source_class, type: candidate.suggested_scene_type, name: objectLabels[candidate.suggested_scene_type], detectorConfidence: candidate.confidence, source: candidate.source, status: "DETECTED" })) }; }
function updateObject(update: (fn: (state: SceneState) => SceneState) => void, id: string, patch: Partial<SceneObject>) { update((state) => ({ ...state, objects: state.objects.map((object) => object.id === id ? { ...object, ...patch } : object) })); }
function updateMeasurement(update: (fn: (state: SceneState) => SceneState) => void, id: string, key: ObjectDimensionKey, value: number | null) { update((state) => ({ ...state, objects: state.objects.map((object) => object.id === id ? { ...object, measurements: { ...object.measurements, [key]: value }, status: object.status === "DETECTED" ? "USER_MODIFIED" : object.status } : object) })); }
function boxFromPoints(a: NormalizedPoint, b: NormalizedPoint): NormalizedBox { return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) }; }
function moveBox(box: NormalizedBox, dx: number, dy: number): NormalizedBox { return { ...box, x: clamp(box.x + dx, 0, 1 - box.width), y: clamp(box.y + dy, 0, 1 - box.height) }; }
function resizeBox(box: NormalizedBox, dx: number, dy: number): NormalizedBox { return { ...box, width: Math.max(.02, Math.min(1 - box.x, box.width + dx)), height: Math.max(.02, Math.min(1 - box.y, box.height + dy)) }; }
function svgBox(box: NormalizedBox, width: number, height: number) { return { x: box.x * width, y: box.y * height, width: box.width * width, height: box.height * height }; }
function lineProps(a: NormalizedPoint, b: NormalizedPoint, width: number, height: number) { return { x1: a.x * width, y1: a.y * height, x2: b.x * width, y2: b.y * height }; }
function pointFromSvg(event: React.PointerEvent<SVGElement>): NormalizedPoint { const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect(); return rect ? { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) } : { x: 0, y: 0 }; }
function clamp(value: number, min = 0, max = 1) { return Math.max(min, Math.min(max, value)); }
function ToolButton({ icon: Icon, label, active = false, disabled = false, onClick }: { icon: typeof Move; label: string; active?: boolean; disabled?: boolean; onClick: () => void }) { return <button title={label} aria-pressed={active} disabled={disabled} onClick={onClick} className={`flex min-h-10 items-center gap-2 rounded-lg px-2 text-xs font-semibold disabled:opacity-30 ${active ? "bg-primary text-white" : "bg-muted hover:bg-primary/10"}`}><Icon className="size-4" /><span className="hidden lg:inline">{label}</span></button>; }
function ToolbarGroup({ label, children }: { label: string; children: React.ReactNode }) { return <div className="flex items-center gap-1 rounded-xl border border-border p-1" aria-label={label}>{children}</div>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block text-xs font-semibold">{label}<span className="mt-1 block">{children}</span></label>; }
function NumberField({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) { return <Field label={label}><input type="number" min="0.1" step="0.1" value={value ?? ""} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)} className={controlClass} /></Field>; }
function Datum({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-border p-3"><dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>; }
function ActionCard({ icon: Icon, title, text, action, onClick }: { icon: typeof Ruler; title: string; text: string; action: string; onClick: () => void }) { return <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3"><div className="flex gap-2"><Icon className="mt-0.5 size-4 shrink-0" /><div><strong className="text-sm">{title}</strong><p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p></div></div><button onClick={onClick} className="mt-3 text-xs font-semibold text-primary">{action} →</button></div>; }
function EmptyState({ text }: { text: string }) { return <div className="rounded-xl border border-dashed border-border p-5 text-center text-xs leading-5 text-muted-foreground"><HelpCircle className="mx-auto mb-2 size-5" />{text}</div>; }
function qualityLabel(quality: ReturnType<typeof calibrationQuality>) { return quality === "GOOD" ? "Dobra kalibracja" : quality === "PARTIAL" ? "Częściowa kalibracja" : quality === "ATTENTION_REQUIRED" ? "Kalibracja wymaga uwagi" : "Brak kalibracji"; }
function stageLabel(stage: string | null) { return stage === "scene-ready" ? "Scena gotowa" : stage === "scene-detection-failed" ? "Tryb ręczny" : stage === "scene-detection-processing" ? "Wykrywanie obiektów" : "Oczekiwanie"; }
function tabLabel(tab: Tab) { return ({ SCENE: "Scena", OBJECTS: "Obiekty", HUMANS: "Człowiek", DIMENSIONS: "Wymiary", SUGGESTIONS: "Sugestie" })[tab]; }
function tabShortLabel(tab: Tab) { return ({ SCENE: "Scena", OBJECTS: "Obiekty", HUMANS: "Osoby", DIMENSIONS: "Wymiary", SUGGESTIONS: "Sugestie" })[tab]; }
function priorityLabel(priority: "CRITICAL" | "RECOMMENDED" | "OPTIONAL") { return priority === "CRITICAL" ? "Krytyczne" : priority === "RECOMMENDED" ? "Zalecane" : "Opcjonalne"; }
const postureOptions: [HumanPosture, string][] = [["STANDING", "Stojąca"], ["SEATED", "Siedząca"], ["REACHING", "Sięganie"], ["FORWARD_LEAN", "Pochylenie do przodu"], ["WORK_SURFACE", "Praca przy blacie"], ["ONE_HANDED", "Praca jednorącz"], ["TWO_HANDED", "Praca oburącz"]];
