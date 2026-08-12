"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  AlertTriangle, Box, ChevronRight, Copy, Eye, EyeOff, Focus, Grid2X2, HelpCircle,
  ImagePlus, LocateFixed, Lock, Minus, MousePointer2, Move, Plus, Redo2, RotateCcw,
  Ruler, Save, Sparkles, Trash2, Undo2, Unlock, UserRound, UsersRound,
} from "lucide-react";

import { HumanMannequin, type HumanDragKind } from "@/components/photo-scene/human-mannequin";
import { HUMAN_PRESETS, buildAnthropometricPose, createConstraintGraph, createHuman, profileFromHeight, profileWithArmSpan, resetHumanPose, withUserSegment } from "@/lib/photo-scene/anthropometry";
import { calibrationAssistant, calibrationQuality, calibrationStatus, duplicateReference, estimateLocalScale, rebuildPerspectiveField, referencePixelDistance } from "@/lib/photo-scene/calibration";
import { moveHumanJointWithConstraints, moveHumanRootUniform } from "@/lib/photo-scene/geometry";
import { layoutMeasurementLabels } from "@/lib/photo-scene/label-layout";
import { dimensionsFor, objectCompleteness } from "@/lib/photo-scene/object-dimensions";
import { emptyMeasurements, refreshInsights, workerSuggestionToMeasurement } from "@/lib/photo-scene/schema";
import { missingDimensionSuggestions, nextBestAction, sceneCompleteness } from "@/lib/photo-scene/suggestions";
import type {
  CalibrationReference, GeometryMeasurement, HumanJointName, HumanPosture, NormalizedBox,
  NormalizedPoint, ObjectDimensionKey, ObjectInteractionPointType, ReferenceDimensionType,
  SceneDetection, SceneHuman, SceneLayerKey, SceneObject, SceneObjectType, SceneState,
  SceneViewPreset,
} from "@/types/photo-scene";

type Tool = "SELECT" | "PAN" | "ADD_OBJECT" | "FLOOR" | "REFERENCE" | "HUMAN";
type Tab = "SCENE" | "OBJECTS" | "HUMANS" | "DIMENSIONS" | "SUGGESTIONS";
type DraftMeasurement = { start: NormalizedPoint; end: NormalizedPoint; objectId: string | null };
type Drag = { kind: HumanDragKind | "OBJECT" | "RESIZE" | "PAN"; id?: string; joint?: HumanJointName; start: NormalizedPoint; snapshot: SceneState };

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
  const debugScene = useSyncExternalStore(
    () => () => undefined,
    () => process.env.NODE_ENV === "development" && new URLSearchParams(window.location.search).get("debugScene") === "1",
    () => false,
  );
  const latestRef = useRef(state);
  const previewStateRef = useRef<SceneState | null>(null), animationFrameRef = useRef<number | null>(null);
  useEffect(() => { latestRef.current = state; }, [state]);
  useEffect(() => () => { if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current); }, []);

  function queuePreview(next: SceneState) {
    previewStateRef.current = next;
    if (animationFrameRef.current !== null) return;
    animationFrameRef.current = requestAnimationFrame(() => {
      if (previewStateRef.current) setState(previewStateRef.current);
      previewStateRef.current = null; animationFrameRef.current = null;
    });
  }

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
      const shortcut = event.key.toLowerCase();
      if (shortcut === "v") setTool("SELECT"); if (shortcut === "h") setTool("PAN");
      if (shortcut === "m") { setTool("REFERENCE"); setTab("DIMENSIONS"); }
      if (shortcut === "o") setTool("ADD_OBJECT"); if (shortcut === "p") { setTool("HUMAN"); setTab("HUMANS"); }
      if (shortcut === "f") update((state) => ({ ...state, viewport: { zoom: 1, pan_x: 0, pan_y: 0 } }));
      if ((event.key === "Delete" || event.key === "Backspace") && latestRef.current.selectedObjectId) update((current) => ({ ...current, objects: current.objects.map((object) => object.id === current.selectedObjectId ? { ...object, status: "USER_REJECTED" } : object) }));
    }
    window.addEventListener("keydown", keyboard); return () => window.removeEventListener("keydown", keyboard);
  });

  function point(event: React.PointerEvent<SVGSVGElement>): NormalizedPoint { const rect = event.currentTarget.getBoundingClientRect(); return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) }; }
  function pointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.target !== event.currentTarget && !["ADD_OBJECT", "FLOOR", "REFERENCE", "HUMAN"].includes(tool)) return;
    const p = point(event); event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === "HUMAN" && state.selectedHumanId) { commit(placeHumanAt(state, state.selectedHumanId, p, props.imageWidth, props.imageHeight)); setTool("SELECT"); return; }
    if (["ADD_OBJECT", "FLOOR", "REFERENCE"].includes(tool)) { setDraftStart(p); setDraftPoint(p); }
    if (tool === "PAN") setDrag({ kind: "PAN", start: p, snapshot: state });
  }
  function pointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const p = point(event); if (draftStart) setDraftPoint(p); if (!drag) return;
    const dx = p.x - drag.start.x, dy = p.y - drag.start.y;
    let preview: SceneState | null = null;
    if (drag.kind === "PAN") preview = { ...drag.snapshot, viewport: { ...drag.snapshot.viewport, pan_x: drag.snapshot.viewport.pan_x + dx, pan_y: drag.snapshot.viewport.pan_y + dy } };
    if ((drag.kind === "OBJECT" || drag.kind === "RESIZE") && drag.id) preview = { ...drag.snapshot, objects: drag.snapshot.objects.map((object) => object.id !== drag.id || object.locked ? object : { ...object, bbox: drag.kind === "OBJECT" ? moveBox(object.bbox, dx, dy) : resizeBox(object.bbox, dx, dy), status: object.status === "DETECTED" ? "USER_MODIFIED" : object.status }) };
    if ((drag.kind === "HUMAN_ROOT" || drag.kind === "STANDING") && drag.id) preview = moveHumanInPerspective(drag.snapshot, drag.id, dx, dy, props.imageWidth, props.imageHeight);
    if (drag.kind === "JOINT" && drag.id && drag.joint) preview = { ...drag.snapshot, humans: drag.snapshot.humans.map((human) => { if (human.id !== drag.id || human.locked) return human; const scale = estimateLocalScale(drag.snapshot.calibration, human.placement.contactPoint, props.imageWidth, props.imageHeight)?.pixelsPerCm ?? human.placement.lastScalePxPerCm ?? 3; return moveHumanJointWithConstraints(human, drag.joint!, p, scale, props.imageWidth, props.imageHeight); }) };
    if (drag.kind === "ORIENTATION" && drag.id) preview = { ...drag.snapshot, humans: drag.snapshot.humans.map((human) => human.id === drag.id ? rotateHuman(human, p, props.imageWidth, props.imageHeight) : human) };
    if (preview) queuePreview(preview);
  }
  function pointerUp(event: React.PointerEvent<SVGSVGElement>) {
    const p = point(event);
    if (drag) { if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current); const next = refreshInsights(previewStateRef.current ?? state); previewStateRef.current = null; animationFrameRef.current = null; setState(next); setHistory((items) => [...items.slice(-49), drag.snapshot]); setFuture([]); setDrag(null); setSaveStatus("DIRTY"); }
    if (!draftStart) return;
    if (tool === "ADD_OBJECT") { const bbox = boxFromPoints(draftStart, p); if (bbox.width > .01 && bbox.height > .01) commit({ ...state, objects: [...state.objects, newObject(bbox)] }); }
    if (tool === "FLOOR") commit({ ...state, calibration: { ...state.calibration, floorBaseline: { start: draftStart, end: p } } });
    if (tool === "REFERENCE" && referencePixelDistance(draftStart, p, props.imageWidth, props.imageHeight) > 2) { setDraftMeasurement({ start: draftStart, end: p, objectId: state.selectedObjectId }); setTab("DIMENSIONS"); }
    setDraftStart(null); setDraftPoint(null); if (tool !== "REFERENCE") setTool("SELECT");
  }
  function addReference(input: { name: string; type: ReferenceDimensionType; valueCm: number; affectsScale: boolean }) {
    if (!draftMeasurement || !Number.isFinite(input.valueCm) || input.valueCm <= 0) return;
    const reference: CalibrationReference = { id: crypto.randomUUID(), name: input.name.trim() || referenceLabels[input.type], dimensionType: input.type, valueCm: input.valueCm, unit: "cm", start: draftMeasurement.start, end: draftMeasurement.end, pixelDistance: referencePixelDistance(draftMeasurement.start, draftMeasurement.end, props.imageWidth, props.imageHeight), objectId: draftMeasurement.objectId, active: true, visible: true, locked: false, affectsScale: input.affectsScale, source: "USER_PROVIDED", residual: null, residualStatus: "UNASSESSED", manualOverride: false };
    update((current) => { const calibration = { ...current.calibration, references: [...current.calibration.references, reference] }; calibration.status = calibrationStatus(calibration); return rescaleLockedHumans({ ...current, calibration }, props.imageWidth, props.imageHeight); });
    setDraftMeasurement(null); setTool("SELECT");
  }

  const selectedObject = state.objects.find((object) => object.id === state.selectedObjectId) ?? null;
  const selectedHuman = state.humans.find((human) => human.id === state.selectedHumanId) ?? null;
  const quality = calibrationQuality(state.calibration), completion = sceneCompleteness(state);

  return <div className="grid min-w-0 gap-4 2xl:grid-cols-[minmax(0,1fr)_390px]">
    <section className="ui-card min-w-0 overflow-hidden">
      <Toolbar state={state} tool={tool} setTool={setTool} history={history.length} future={future.length} undo={undo} redo={redo} update={update} setTab={setTab} />
      <div className="relative overflow-hidden bg-neutral-950 p-2 sm:p-4">
        <svg viewBox={`0 0 ${props.imageWidth} ${props.imageHeight}`} role="application" aria-label="Edytor sceny ze zdjęcia" className="mx-auto block max-h-[76vh] w-full touch-none select-none" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} style={{ aspectRatio: `${props.imageWidth}/${props.imageHeight}`, transform: `translate(${state.viewport.pan_x * 100}%,${state.viewport.pan_y * 100}%) scale(${state.viewport.zoom})`, transformOrigin: "center" }}>
          <defs><marker id="dimension-arrow" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M7 0L0 3.5L7 7" fill="none" stroke="context-stroke" strokeWidth="1.5" /></marker><marker id="facing-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7Z" fill="context-stroke" /></marker></defs>
          <image href={props.imageUrl} width={props.imageWidth} height={props.imageHeight} pointerEvents="none" />
          {state.objects.filter((object) => object.visible && object.status !== "USER_REJECTED").map((object) => <ObjectOverlay key={object.id} object={object} selected={object.id === state.selectedObjectId} width={props.imageWidth} height={props.imageHeight} onStart={(kind, event) => { event.stopPropagation(); setState((current) => ({ ...current, selectedObjectId: object.id })); setDrag({ kind, id: object.id, start: pointFromSvg(event), snapshot: state }); }} />)}
          {state.view.layers.CALIBRATION && state.calibration.floorBaseline && <line {...lineProps(state.calibration.floorBaseline.start, state.calibration.floorBaseline.end, props.imageWidth, props.imageHeight)} stroke="#22d3ee" strokeWidth="3" strokeDasharray="14 9" />}
          {visibleReferences(state).map((reference) => <MeasurementOverlay key={reference.id} reference={reference} width={props.imageWidth} height={props.imageHeight} selected={reference.id === state.selectedReferenceId} zoom={state.viewport.zoom} onSelect={() => { setState((current) => ({ ...current, selectedReferenceId: reference.id })); setTab("DIMENSIONS"); }} />)}
          <GeometryMeasurementsOverlay state={state} width={props.imageWidth} height={props.imageHeight} />
          {state.objects.flatMap((object) => object.interactionPoints.map((interaction) => ({ ...interaction, objectId: object.id }))).map((interaction) => interaction.visible && <g key={interaction.id}><circle cx={interaction.position.x * props.imageWidth} cy={interaction.position.y * props.imageHeight} r="7" fill="#0f172a" stroke="#f59e0b" strokeWidth="2" /><text x={interaction.position.x * props.imageWidth + 10} y={interaction.position.y * props.imageHeight + 4} fill="white" fontSize="11">{interaction.name}</text></g>)}
          {state.humans.filter((human) => human.visible).map((human) => <HumanMannequin key={human.id} human={human} width={props.imageWidth} height={props.imageHeight} calibration={state.calibration} reachVisible={state.reachVisible && state.view.layers.HUMAN_REACH} reachMode={state.view.reachMode} debug={debugScene} zoom={state.viewport.zoom} selected={human.id === state.selectedHumanId} onSelect={() => { setState((current) => ({ ...current, selectedHumanId: human.id })); setTab("HUMANS"); }} onStart={(kind, joint, event) => { event.stopPropagation(); setDrag({ kind, id: human.id, joint, start: pointFromSvg(event), snapshot: state }); }} />)}
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
        {tab === "HUMANS" && <HumansPanel state={state} selected={selectedHuman} update={update} setTool={setTool} imageWidth={props.imageWidth} imageHeight={props.imageHeight} />}
        {tab === "DIMENSIONS" && <DimensionsPanel state={state} draft={draftMeasurement} addReference={addReference} cancelDraft={() => setDraftMeasurement(null)} update={update} setTool={setTool} />}
        {tab === "SUGGESTIONS" && <SuggestionsPanel state={state} update={update} setTab={setTab} setTool={setTool} />}
      </div>
    </aside>
  </div>;
}

function Toolbar({ state, tool, setTool, history, future, undo, redo, update, setTab }: { state: SceneState; tool: Tool; setTool: (tool: Tool) => void; history: number; future: number; undo: () => void; redo: () => void; update: (fn: (state: SceneState) => SceneState) => void; setTab: (tab: Tab) => void }) {
  return <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
    <ToolbarGroup label="Nawigacja"><ToolButton active={tool === "SELECT"} icon={MousePointer2} label="Wybierz" onClick={() => setTool("SELECT")} /><ToolButton active={tool === "PAN"} icon={Move} label="Przesuń" onClick={() => setTool("PAN")} /></ToolbarGroup>
    <ToolbarGroup label="Dodawanie"><ToolButton active={tool === "ADD_OBJECT"} icon={ImagePlus} label="Obiekt" onClick={() => setTool("ADD_OBJECT")} /><ToolButton active={tool === "HUMAN"} icon={UserRound} label="Człowiek" onClick={() => { setTool("HUMAN"); setTab("HUMANS"); }} /></ToolbarGroup>
    <ToolbarGroup label="Kalibracja"><ToolButton active={tool === "REFERENCE"} icon={Ruler} label="Wymiar" onClick={() => { setTool("REFERENCE"); setTab("DIMENSIONS"); }} /><ToolButton active={tool === "FLOOR"} icon={LocateFixed} label="Podłoga" onClick={() => setTool("FLOOR")} /></ToolbarGroup>
    <ToolbarGroup label="Historia i widok"><ToolButton disabled={!history} icon={Undo2} label="Cofnij" onClick={undo} /><ToolButton disabled={!future} icon={Redo2} label="Ponów" onClick={redo} /><ToolButton icon={Plus} label="Powiększ" onClick={() => update((state) => ({ ...state, viewport: { ...state.viewport, zoom: Math.min(4, state.viewport.zoom + .2) } }))} /><ToolButton icon={Minus} label="Pomniejsz" onClick={() => update((state) => ({ ...state, viewport: { ...state.viewport, zoom: Math.max(.5, state.viewport.zoom - .2) } }))} /><ToolButton icon={Grid2X2} label="Dopasuj" onClick={() => update((state) => ({ ...state, viewport: { zoom: 1, pan_x: 0, pan_y: 0 } }))} /></ToolbarGroup>
    <details className="relative"><summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-lg border border-border bg-muted px-3 text-xs font-semibold"><Eye className="size-4" />Warstwy</summary><div className="absolute right-0 z-30 mt-2 w-64 space-y-2 rounded-xl border border-border bg-card p-3 shadow-xl">{([['OBJECT_DIMENSIONS','Wymiary obiektów'],['USER_MEASUREMENTS','Pomiary użytkownika'],['CALIBRATION','Kalibracja'],['HUMAN_REACH','Zasięgi'],['SUGGESTIONS','Sugestie']] as [SceneLayerKey,string][]).map(([key,label]) => <label key={key} className="flex items-center justify-between text-xs"><span>{label}</span><input type="checkbox" checked={state.view.layers[key]} onChange={(event) => update((current) => ({ ...current, view: { ...current.view, layers: { ...current.view.layers, [key]: event.target.checked } } }))} /></label>)}<label className="flex items-center justify-between border-t border-border pt-2 text-xs"><span>Tryb skupienia</span><input type="checkbox" checked={state.view.focusMode} onChange={(event) => update((current) => ({ ...current, view: { ...current.view, focusMode: event.target.checked } }))} /></label></div></details>
    <div className="ml-auto hidden gap-1 xl:flex">{([['CLEAN','Czysty'],['DIMENSIONS','Wymiary'],['CALIBRATION','Kalibracja'],['HUMAN','Człowiek']] as const).map(([preset,label]) => <button key={preset} onClick={() => update((current) => applyViewPreset(current, preset))} className={`rounded-lg px-2 py-1.5 text-[11px] font-semibold ${state.view.preset === preset ? 'bg-primary/10 text-primary' : 'text-muted-foreground'}`}>{label}</button>)}</div>
  </div>;
}

function ScenePanel({ analysisId, title, state, processingStage, detectionError, quality, completion, save, setTab }: Parameters<typeof PhotoSceneEditor>[0] & { state: SceneState; quality: ReturnType<typeof calibrationQuality>; completion: ReturnType<typeof sceneCompleteness>; save: () => Promise<void>; setTab: (tab: Tab) => void }) {
  async function retry() { const response = await fetch(`/api/photo-scenes/${analysisId}`, { method: "POST" }); if (response.ok) window.location.reload(); }
  const next = nextBestAction(state);
  return <><div><p className="text-xs uppercase tracking-wider text-muted-foreground">Projekt sceny</p><h2 className="mt-1 text-xl font-bold">{title}</h2></div>
    <div className="rounded-xl border-2 border-primary/30 bg-primary/5 p-4"><p className="text-[10px] font-bold uppercase tracking-wider text-primary">Następny krok</p><h3 className="mt-1 text-sm font-bold">{next.title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{next.message}</p>{next.cta && <button onClick={() => setTab(next.kind === "HUMAN" ? "HUMANS" : next.kind === "OBJECT" ? "OBJECTS" : "DIMENSIONS")} className="mt-3 text-xs font-bold text-primary">{next.cta} →</button>}</div>
    <div className="grid grid-cols-2 gap-2"><Datum label="Geometria" value={`${completion.categories.geometry.completed}/${completion.categories.geometry.total}`} /><Datum label="Kalibracja" value={`${completion.categories.calibration.completed}/${completion.categories.calibration.total}`} /><Datum label="Obiekty" value={`${completion.categories.objects.completed}/${completion.categories.objects.total}`} /><Datum label="Człowiek" value={completion.categories.human.completed ? "Profil kompletny" : "Wymaga ustawienia"} /></div>
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
      <details open className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Wymiary</summary><div className="mt-3 grid grid-cols-2 gap-2">{dimensionsFor(selected.type).map((definition) => <NumberField key={definition.key} label={`${definition.label} [cm]`} value={selected.measurements[definition.key]} onChange={(value) => updateMeasurement(update, selected.id, definition.key, value)} />)}</div><button onClick={() => { setTool("REFERENCE"); setTab("DIMENSIONS"); }} className="ui-button-secondary mt-3 w-full justify-center"><Ruler className="size-4" />Narysuj geometrię wymiaru</button>{selected.geometryMeasurements.length > 0 && <div className="mt-3 space-y-2">{selected.geometryMeasurements.map((measurement) => <div key={measurement.id} className="rounded-lg bg-muted/50 p-2 text-xs"><div className="flex items-center justify-between gap-2"><span>{measurement.name}</span><strong>{measurement.valueCm === null ? "do pomiaru" : `${measurement.source === "SCENE_ESTIMATED" ? "≈ " : ""}${measurement.valueCm} cm`}</strong></div><small className="text-muted-foreground">{provenanceLabel(measurement.source)}</small>{measurement.source === "SCENE_ESTIMATED" && <button onClick={() => confirmEstimatedMeasurement(update, selected.id, measurement.id)} className="mt-1 block font-semibold text-primary">Potwierdź wartość</button>}</div>)}</div>}</details>
      <details className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Punkty robocze</summary><div className="mt-3 grid grid-cols-2 gap-2">{([['WORKING_POINT','Punkt pracy'],['GRIP_POINT','Uchwyt'],['CONTROL_POINT','Sterowanie'],['PLACEMENT_POINT','Odkładanie']] as const).map(([type,label]) => <button key={type} onClick={() => addInteractionPoint(update, selected, type, label)} className="ui-button-secondary justify-center text-xs"><Plus className="size-3" />{label}</button>)}</div><div className="mt-2 space-y-1">{selected.interactionPoints.map((point) => <div key={point.id} className="flex items-center justify-between rounded-lg bg-muted/50 px-2 py-1.5 text-xs"><span>{point.name}</span><button onClick={() => updateObject(update, selected.id, { interactionPoints: selected.interactionPoints.filter((item) => item.id !== point.id) })}><Trash2 className="size-3" /></button></div>)}</div></details>
      <details className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Sugestie geometrii</summary><div className="mt-3"><button onClick={() => { setTab("SUGGESTIONS"); update((current) => ({ ...current, view: { ...current.view, layers: { ...current.view.layers, SUGGESTIONS: true } } })); }} className="ui-button-primary w-full justify-center"><Sparkles className="size-4" />Zaproponuj wymiary</button><p className="mt-2 text-[11px] text-muted-foreground">Pokazuje heurystyczne linie Workera. Nie zapisuje ich jako pomiarów bez akceptacji.</p></div></details>
      <div className="grid grid-cols-2 gap-2"><button onClick={() => updateObject(update, selected.id, { visible: !selected.visible })} className="ui-button-secondary justify-center">{selected.visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}{selected.visible ? "Ukryj" : "Pokaż"}</button><button onClick={() => updateObject(update, selected.id, { locked: !selected.locked })} className="ui-button-secondary justify-center">{selected.locked ? <Unlock className="size-4" /> : <Lock className="size-4" />}{selected.locked ? "Odblokuj" : "Zablokuj"}</button></div>
      {selected.status === "DETECTED" && <button onClick={() => updateObject(update, selected.id, { status: "USER_CONFIRMED" })} className="ui-button-primary w-full justify-center">Potwierdź wykrycie</button>}
      <button onClick={() => updateObject(update, selected.id, { status: selected.status === "USER_REJECTED" ? "USER_MODIFIED" : "USER_REJECTED" })} className="ui-button-secondary w-full justify-center"><Trash2 className="size-4" />{selected.status === "USER_REJECTED" ? "Przywróć" : "Odrzuć obiekt"}</button>
    </div>}</>;
}

function HumansPanel({ state, selected, update, setTool, imageWidth, imageHeight }: { state: SceneState; selected: SceneHuman | null; update: (fn: (state: SceneState) => SceneState) => void; setTool: (tool: Tool) => void; imageWidth: number; imageHeight: number }) {
  function add(preset: keyof typeof HUMAN_PRESETS = "MEDIUM") { const human = { ...createHuman(`Operator ${state.humans.length + 1}`, humanColors[state.humans.length % humanColors.length], preset), visible: false }; update((current) => ({ ...current, humans: [...current.humans, human], selectedHumanId: human.id, view: { ...current.view, preset: "HUMAN", layers: { ...current.view.layers, HUMAN_REACH: false } } })); setTool("HUMAN"); }
  return <><div className="rounded-xl border border-primary/30 bg-primary/5 p-3 text-xs"><strong>Dodaj osobę</strong><p className="mt-1 text-muted-foreground">Wybierz profil, a następnie kliknij punkt stania na zdjęciu.</p><div className="mt-3 grid grid-cols-3 gap-2">{Object.entries(HUMAN_PRESETS).map(([id, profile]) => <button key={id} onClick={() => add(id as keyof typeof HUMAN_PRESETS)} className="rounded-lg border border-border bg-card p-2 font-semibold hover:border-primary"><span className="block">{profile.label}</span><small className="text-muted-foreground">{profile.heightCm} cm</small></button>)}</div></div>
    <button onClick={() => add()} className="ui-button-primary w-full justify-center"><UsersRound className="size-4" />Dodaj kolejną osobę</button>
    <div className="space-y-2">{state.humans.map((human) => <button key={human.id} onClick={() => update((current) => ({ ...current, selectedHumanId: human.id }))} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left ${human.id === state.selectedHumanId ? "border-primary bg-primary/5" : "border-border"}`}><span className="size-3 rounded-full" style={{ background: human.color }} /><span className="flex-1 text-sm font-semibold">{human.name}</span><small>{human.profile.heightCm} cm</small></button>)}</div>
    {selected && <HumanEditor human={selected} state={state} update={update} imageWidth={imageWidth} imageHeight={imageHeight} />}</>;
}

function HumanEditor({ human, state, update, imageWidth, imageHeight }: { human: SceneHuman; state: SceneState; update: (fn: (state: SceneState) => SceneState) => void; imageWidth: number; imageHeight: number }) {
  const scale = estimateLocalScale(state.calibration, human.placement.contactPoint, imageWidth, imageHeight), allPoints = state.objects.flatMap((object) => object.interactionPoints.map((point) => ({ ...point, objectId: object.id, objectName: object.name })));
  function replace(next: SceneHuman) { update((current) => ({ ...current, humans: current.humans.map((item) => item.id === human.id ? next : item) })); }
  function patchHuman(patch: Partial<SceneHuman>) { replace({ ...human, ...patch }); }
  function rebuild(profile = human.profile, posture = human.pose.preset, orientation = human.placement.orientationDeg, facingPreset = human.placement.facingPreset) { const px = scale?.pixelsPerCm ?? human.placement.lastScalePxPerCm ?? 3, pose = buildAnthropometricPose(profile, human.placement.contactPoint, px, imageWidth, imageHeight, posture === "CUSTOM" ? "STANDING" : posture, orientation, human.pose); replace({ ...human, visible: human.placement.lastScalePxPerCm === null ? true : human.visible, profile, constraints: createConstraintGraph(profile), pose, placement: { ...human.placement, root: pose.joints.pelvisRoot, leftFootContact: pose.joints.leftFoot, rightFootContact: pose.joints.rightFoot, orientationDeg: orientation, facingPreset, lastScalePxPerCm: px, scaleStatus: scale?.status ?? "LOCAL_ONLY" } }); }
  function setHeight(value: number | null) { if (!value) return; rebuild({ ...profileFromHeight(human.profile.name, value, "CUSTOM"), name: human.profile.name }); }
  function setSegment(field: "upperArmLengthCm" | "forearmLengthCm" | "handLengthCm" | "thighLengthCm" | "lowerLegLengthCm", segment: "upperArm" | "forearm" | "hand" | "thigh" | "lowerLeg", value: number | null) { const profile = withUserSegment({ ...human.profile, [field]: value, preset: "CUSTOM" }, segment, value); rebuild(profile); }
  function attachToObject(objectId: string) { const object = state.objects.find((item) => item.id === objectId); if (!object) { patchHuman({ placement: { ...human.placement, attachedObjectId: null, positionMode: "FREE", facingPreset: "FRONT" } }); return; } const point = floorPointNearObject(object, state.calibration.floorBaseline), orientation = angleToObject(point, object); const positioned = placeSingleHuman(human, point, state.calibration, imageWidth, imageHeight, orientation, human.pose.preset === "SEATED" ? "SEATED_AT_OBJECT" : "WORKING_AT_OBJECT", object.id); replace(positioned); }
  function setHandTarget(side: "left" | "right", value: string) { const [objectId, pointId] = value.split(":"); const object = state.objects.find((item) => item.id === objectId), target = object?.interactionPoints.find((point) => point.id === pointId); if (!object || !target) { patchHuman({ handTargets: { ...human.handTargets, [side]: null } }); return; } const px = scale?.pixelsPerCm ?? human.placement.lastScalePxPerCm ?? 3, next = moveHumanJointWithConstraints(human, side === "left" ? "leftHand" : "rightHand", target.position, px, imageWidth, imageHeight); const status = next.pose.reachState[side === "left" ? "leftArm" : "rightArm"] === "OUT_OF_REACH" ? "OUT_OF_REACH" : "REACHABLE"; replace({ ...next, handTargets: { ...next.handTargets, [side]: { objectId, interactionPointId: pointId, status } } }); }
  return <div className="space-y-3 border-t border-border pt-4">
    <details open className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Profil</summary><div className="mt-3 space-y-3"><Field label="Nazwa"><input value={human.name} onChange={(event) => patchHuman({ name: event.target.value, profile: { ...human.profile, name: event.target.value } })} className={controlClass} /></Field><div className="grid grid-cols-2 gap-2"><NumberField label="Wzrost [cm]" value={human.profile.heightCm} onChange={setHeight} /><NumberField label="Rozpiętość [cm]" value={human.profile.armSpanCm} onChange={(value) => value && rebuild(profileWithArmSpan(human.profile, value))} /><NumberField label="Zasięg komfortowy [cm]" value={human.profile.functionalReachCm} onChange={(value) => value && rebuild({ ...human.profile, functionalReachCm: value })} /><NumberField label="Zasięg maksymalny [cm]" value={human.profile.maximumReachCm} onChange={(value) => value && rebuild({ ...human.profile, maximumReachCm: value })} /></div><details><summary className="cursor-pointer text-xs font-semibold">Wymiary segmentów</summary><div className="mt-2 grid grid-cols-2 gap-2"><NumberField label="Ramię [cm]" value={human.profile.upperArmLengthCm} onChange={(value) => setSegment("upperArmLengthCm", "upperArm", value)} /><NumberField label="Przedramię [cm]" value={human.profile.forearmLengthCm} onChange={(value) => setSegment("forearmLengthCm", "forearm", value)} /><NumberField label="Dłoń [cm]" value={human.profile.handLengthCm} onChange={(value) => setSegment("handLengthCm", "hand", value)} /><NumberField label="Udo [cm]" value={human.profile.thighLengthCm} onChange={(value) => setSegment("thighLengthCm", "thigh", value)} /><NumberField label="Podudzie [cm]" value={human.profile.lowerLegLengthCm} onChange={(value) => setSegment("lowerLegLengthCm", "lowerLeg", value)} /></div><p className="mt-2 text-[11px] text-muted-foreground">Wpisane wartości: USER_PROVIDED. Pozostałe: DERIVED_APPROXIMATION.</p></details></div></details>
    <details open className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Pozycja</summary><div className="mt-3 space-y-3"><Field label="Postawa"><select value={human.pose.preset} onChange={(event) => rebuild(human.profile, event.target.value as HumanPosture)} className={controlClass}>{postureOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field><Field label="Orientacja"><select value={human.placement.facingPreset} onChange={(event) => { const preset = event.target.value as SceneHuman["placement"]["facingPreset"], object = human.placement.attachedObjectId ? state.objects.find((item) => item.id === human.placement.attachedObjectId) : null, angle = preset === "LEFT" ? -90 : preset === "RIGHT" ? 90 : preset === "TOWARD_OBJECT" && object ? angleToObject(human.placement.contactPoint, object) : 0; rebuild(human.profile, human.pose.preset, angle, preset); }} className={controlClass}><option value="FRONT">Przodem</option><option value="LEFT">Lewo</option><option value="RIGHT">Prawo</option><option value="TOWARD_OBJECT">W stronę obiektu</option></select></Field><button onClick={() => rebuild()} className="ui-button-primary w-full justify-center"><Focus className="size-4" />Dopasuj postać do sceny</button><div className="grid grid-cols-2 gap-2"><button onClick={() => replace(resetHumanPose(human, human.pose.preset, imageWidth, imageHeight))} className="ui-button-secondary justify-center"><RotateCcw className="size-4" />Naturalna postawa</button><label className="flex items-center justify-center gap-2 rounded-xl border border-border px-2 text-xs"><input type="checkbox" checked={human.placement.floorPinned} onChange={(event) => patchHuman({ placement: { ...human.placement, floorPinned: event.target.checked } })} />Przypnij stopy</label></div><div className="rounded-lg bg-muted/50 p-2 text-[11px] text-muted-foreground">{scale ? `${scale.pixelsPerCm.toFixed(2)} px/cm · ${scale.status} · uncertainty ${Math.round(scale.uncertainty * 100)}%` : "Brak wiarygodnej skali — ustawienie poglądowe"}</div></div></details>
    <details open className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Interakcja</summary><div className="mt-3 space-y-3"><Field label="Pracuje przy"><select value={human.placement.attachedObjectId ?? ""} onChange={(event) => attachToObject(event.target.value)} className={controlClass}><option value="">Brak — tryb swobodny</option>{state.objects.filter((object) => object.status !== "USER_REJECTED").map((object) => <option key={object.id} value={object.id}>{object.name}</option>)}</select></Field>{([['left','Lewa dłoń'],['right','Prawa dłoń']] as const).map(([side,label]) => <Field key={side} label={label}><select value={human.handTargets[side] ? `${human.handTargets[side]!.objectId}:${human.handTargets[side]!.interactionPointId}` : ""} onChange={(event) => setHandTarget(side, event.target.value)} className={controlClass}><option value="">Bez przypięcia</option>{allPoints.map((point) => <option key={`${point.objectId}:${point.id}`} value={`${point.objectId}:${point.id}`}>{point.objectName} · {point.name}</option>)}</select>{human.handTargets[side]?.status === "OUT_OF_REACH" && <small className="mt-1 block text-amber-600">Punkt poza maksymalnym zasięgiem.</small>}</Field>)}</div></details>
    <details className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Zasięg</summary><div className="mt-3 space-y-3"><label className="flex items-center justify-between text-xs">Pokaż strefę<input type="checkbox" checked={state.view.layers.HUMAN_REACH} onChange={(event) => update((current) => ({ ...current, view: { ...current.view, layers: { ...current.view.layers, HUMAN_REACH: event.target.checked } } }))} /></label><Field label="Zakres"><select value={state.view.reachMode} onChange={(event) => update((current) => ({ ...current, view: { ...current.view, reachMode: event.target.value as SceneState["view"]["reachMode"] } }))} className={controlClass}><option value="COMFORT">Komfortowy</option><option value="FUNCTIONAL">Funkcjonalny</option><option value="MAXIMUM">Maksymalny</option></select></Field></div></details>
    <div className="grid grid-cols-2 gap-2"><button onClick={() => patchHuman({ visible: !human.visible })} className="ui-button-secondary justify-center">{human.visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}{human.visible ? "Ukryj" : "Pokaż"}</button><button onClick={() => patchHuman({ locked: !human.locked })} className="ui-button-secondary justify-center">{human.locked ? <Unlock className="size-4" /> : <Lock className="size-4" />}{human.locked ? "Odblokuj" : "Zablokuj"}</button></div>
    <button onClick={() => update((current) => ({ ...current, humans: current.humans.filter((item) => item.id !== human.id), selectedHumanId: null }))} className="ui-button-secondary w-full justify-center"><Trash2 className="size-4" />Usuń postać</button>
  </div>;
}

function DimensionsPanel({ state, draft, addReference, cancelDraft, update, setTool }: { state: SceneState; draft: DraftMeasurement | null; addReference: (input: { name: string; type: ReferenceDimensionType; valueCm: number; affectsScale: boolean }) => void; cancelDraft: () => void; update: (fn: (state: SceneState) => SceneState) => void; setTool: (tool: Tool) => void }) {
  const assistant = calibrationAssistant(state.calibration);
  return <><div className="grid grid-cols-2 gap-2"><button onClick={() => setTool("REFERENCE")} className="ui-button-primary justify-center"><Ruler className="size-4" />Nowy wymiar</button><button onClick={() => setTool("FLOOR")} className="ui-button-secondary justify-center"><LocateFixed className="size-4" />Podłoga</button></div>
    <p className="text-xs leading-5 text-muted-foreground">Narysuj odcinek na zdjęciu, a następnie opisz jego rodzaj i rzeczywistą długość. Referencje z różnych miejsc budują lokalny model skali.</p>
    <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3 text-xs"><strong>Model skali: {scaleStatusLabel(state.calibration.scaleField.status)}</strong><p className="mt-1 leading-5 text-muted-foreground">{assistant.message}</p>{state.calibration.scaleField.residualRms !== null && <small className="mt-1 block">Błąd modelu: {(state.calibration.scaleField.residualRms * 100).toFixed(1)}%</small>}</div>
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
  return <div className={`space-y-2 rounded-xl border p-3 ${reference.residualStatus === "OUTLIER" ? "border-red-500/50 bg-red-500/5" : reference.residualStatus === "WEAK" ? "border-amber-500/40" : "border-border"}`}><div className="flex items-start gap-2"><button onClick={() => patch({ visible: !reference.visible })}>{reference.visible ? <Eye className="size-4" /> : <EyeOff className="size-4" />}</button><div className="min-w-0 flex-1"><input value={reference.name} onChange={(event) => patch({ name: event.target.value })} className="w-full bg-transparent text-sm font-semibold outline-none" /><small className="text-muted-foreground">{referenceLabels[reference.dimensionType]} · {reference.valueCm} cm · {residualStatusLabel(reference.residualStatus)}</small></div><button onClick={() => patch({ locked: !reference.locked })}>{reference.locked ? <Lock className="size-4" /> : <Unlock className="size-4" />}</button></div><div className="flex flex-wrap gap-2 text-[11px]"><label><input type="checkbox" checked={reference.active} onChange={(event) => patch({ active: event.target.checked })} /> aktywny</label><label><input type="checkbox" checked={reference.affectsScale} onChange={(event) => patch({ affectsScale: event.target.checked })} /> wpływa na skalę</label>{reference.residualStatus === "OUTLIER" && <label><input type="checkbox" checked={reference.manualOverride} onChange={(event) => patch({ manualOverride: event.target.checked })} /> zatwierdź odstępstwo</label>}</div><div className="grid grid-cols-2 gap-2"><button onClick={() => update((state) => ({ ...state, calibration: { ...state.calibration, references: [...state.calibration.references, duplicateReference(reference)] } }))} className="ui-button-secondary justify-center text-xs"><Copy className="size-3" />Duplikuj</button><button onClick={() => update((state) => ({ ...state, calibration: { ...state.calibration, references: state.calibration.references.filter((item) => item.id !== reference.id) } }))} className="ui-button-secondary justify-center text-xs"><Trash2 className="size-3" />Usuń</button></div></div>;
}

function SuggestionsPanel({ state, update, setTab, setTool }: { state: SceneState; update: (fn: (state: SceneState) => SceneState) => void; setTab: (tab: Tab) => void; setTool: (tool: Tool) => void }) {
  const suggestions = missingDimensionSuggestions(state).slice(0, 5), completion = sceneCompleteness(state), workerSuggestions = state.workerSuggestions.filter((suggestion) => (suggestion.status ?? "PENDING") === "PENDING").slice(0, 5);
  return <><div className="rounded-xl border border-border p-4"><div className="flex items-center justify-between"><strong>Kompletność sceny</strong><span className="text-lg font-bold text-primary">{Math.round(completion.ratio * 100)}%</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${completion.ratio * 100}%` }} /></div><p className="mt-2 text-xs text-muted-foreground">{completion.completed} z {completion.total} kluczowych wymiarów</p></div>
    <label className="flex items-center justify-between rounded-xl border border-border p-3 text-xs"><span><strong>Automatyczne sugestie</strong><small className="mt-1 block text-muted-foreground">Tylko propozycje — bez automatycznego zapisu.</small></span><input type="checkbox" checked={state.autoSuggestDimensions} onChange={(event) => update((current) => ({ ...current, autoSuggestDimensions: event.target.checked }))} /></label>
    {workerSuggestions.length > 0 && <div className="space-y-2"><h3 className="text-sm font-bold">Sugestie geometrii</h3>{workerSuggestions.map((suggestion) => { const object = state.objects.find((item) => item.id === suggestion.object_id); return <div key={suggestion.id} className="rounded-xl border border-dashed border-amber-500/40 p-3"><div className="flex items-start justify-between gap-2"><div><strong className="text-sm">{dimensionKeyLabel(suggestion.dimension_type)}</strong><p className="mt-1 text-xs text-muted-foreground">{object?.name ?? "Obiekt"} · {suggestion.reason}</p></div><span className="text-[10px] font-bold text-amber-600">{suggestion.estimated_value_cm === null ? "bez wartości" : `≈ ${suggestion.estimated_value_cm} cm`}</span></div><div className="mt-3 grid grid-cols-3 gap-2"><button onClick={() => acceptWorkerSuggestion(update, state, suggestion.id)} className="ui-button-primary justify-center text-xs">Akceptuj</button><button onClick={() => { update((current) => ({ ...current, selectedObjectId: suggestion.object_id })); setTab("OBJECTS"); setTool("REFERENCE"); }} className="ui-button-secondary justify-center text-xs">Edytuj</button><button onClick={() => rejectWorkerSuggestion(update, suggestion.id)} className="ui-button-secondary justify-center text-xs">Odrzuć</button></div></div>; })}</div>}
    <div className="space-y-2">{suggestions.map((suggestion) => <button key={suggestion.id} onClick={() => { update((state) => ({ ...state, selectedObjectId: suggestion.objectId })); setTab("OBJECTS"); setTool("REFERENCE"); }} className="w-full rounded-xl border border-border p-3 text-left hover:border-primary"><span className={`text-[10px] font-bold uppercase ${suggestion.priority === "CRITICAL" ? "text-red-500" : suggestion.priority === "RECOMMENDED" ? "text-amber-500" : "text-muted-foreground"}`}>{priorityLabel(suggestion.priority)}</span><p className="mt-1 text-sm">{suggestion.message}</p><small className="mt-2 inline-flex items-center gap-1 text-primary">Wskaż wymiar <ChevronRight className="size-3" /></small></button>)}</div>
    {!suggestions.length && !workerSuggestions.length && <EmptyState text="Wszystkie sugerowane wymiary zostały uzupełnione." />}
    {state.technicalInsights.filter((insight) => insight.code !== "MISSING_OBJECT_DIMENSION").map((insight) => <div key={insight.id} className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs"><AlertTriangle className="size-4 shrink-0" />{insight.message}</div>)}</>;
}

function ObjectOverlay({ object, selected, width, height, onStart }: { object: SceneObject; selected: boolean; width: number; height: number; onStart: (kind: "OBJECT" | "RESIZE", event: React.PointerEvent<SVGElement>) => void }) { return <g><rect {...svgBox(object.bbox, width, height)} fill="rgba(249,115,22,.10)" stroke={selected ? "#f97316" : "#f8fafc"} strokeWidth={selected ? 4 : 2} onPointerDown={(event) => onStart("OBJECT", event)} /><rect x={object.bbox.x * width + 4} y={object.bbox.y * height + 4} width={Math.max(80, object.name.length * 8)} height="25" rx="5" fill="rgba(15,23,42,.88)" /><text x={object.bbox.x * width + 10} y={object.bbox.y * height + 21} fill="white" fontSize="14" fontWeight="700">{object.name}</text>{selected && !object.locked && <rect x={(object.bbox.x + object.bbox.width) * width - 10} y={(object.bbox.y + object.bbox.height) * height - 10} width="20" height="20" rx="4" fill="#f97316" onPointerDown={(event) => onStart("RESIZE", event)} />}</g>; }
function MeasurementOverlay({ reference, width, height, selected, zoom, onSelect }: { reference: CalibrationReference; width: number; height: number; selected: boolean; zoom: number; onSelect: () => void }) {
  const baseColor = reference.dimensionType === "HEIGHT" || reference.dimensionType === "WORK_SURFACE_HEIGHT" ? "#22d3ee" : reference.dimensionType === "DEPTH" ? "#a78bfa" : "#fbbf24";
  const color = reference.residualStatus === "OUTLIER" ? "#ef4444" : reference.residualStatus === "WEAK" ? "#f59e0b" : baseColor;
  const middle = { x: (reference.start.x + reference.end.x) / 2 * width, y: (reference.start.y + reference.end.y) / 2 * height };
  const labelWidth = selected ? 118 : zoom < .8 ? 70 : 94;
  return <g onPointerDown={(event) => { event.stopPropagation(); onSelect(); }} opacity={reference.active ? 1 : .4}>
    <line {...lineProps(reference.start, reference.end, width, height)} stroke={color} strokeWidth={selected ? 4 : 2.5} strokeDasharray={reference.residualStatus === "OUTLIER" ? "8 6" : undefined} markerStart="url(#dimension-arrow)" markerEnd="url(#dimension-arrow)" />
    <rect x={middle.x - labelWidth / 2} y={middle.y - 25} width={labelWidth} height="22" rx="6" fill="rgba(15,23,42,.93)" stroke={selected ? color : "transparent"} />
    <text x={middle.x} y={middle.y - 9} textAnchor="middle" fill="white" fontSize={zoom < .8 && !selected ? "11" : "13"} fontWeight="700">{selected || zoom >= .8 ? `${reference.valueCm} cm` : `${reference.valueCm}`}</text>
  </g>;
}

function GeometryMeasurementsOverlay({ state, width, height }: { state: SceneState; width: number; height: number }) {
  const objectMeasurements = state.objects.flatMap((object) => object.geometryMeasurements);
  const measurements = [...state.geometryMeasurements, ...objectMeasurements].filter((measurement) => {
    if (!measurement.visible || !measurement.active) return false;
    if (measurement.source === "USER_MEASURED" && !state.view.layers.USER_MEASUREMENTS) return false;
    if (measurement.source === "WORKER_SUGGESTED" && !state.view.layers.SUGGESTIONS) return false;
    if (measurement.source !== "USER_MEASURED" && measurement.source !== "WORKER_SUGGESTED" && !state.view.layers.OBJECT_DIMENSIONS) return false;
    return !state.view.focusMode || !state.selectedObjectId || measurement.objectId === state.selectedObjectId;
  });
  const layouts = new Map(layoutMeasurementLabels(measurements, state.viewport.zoom).map((item) => [item.id, item]));
  return <>{measurements.map((measurement) => {
    const layout = layouts.get(measurement.id); if (!layout) return null;
    const estimated = measurement.source === "SCENE_ESTIMATED" || measurement.source === "WORKER_SUGGESTED";
    const color = measurement.source === "USER_MEASURED" ? "#f97316" : measurement.source === "USER_CONFIRMED_ESTIMATE" ? "#22d3ee" : "#94a3b8";
    const label = `${estimated ? "≈ " : ""}${measurement.valueCm === null ? measurement.name : `${measurement.valueCm} cm`}`;
    return <g key={measurement.id} opacity={measurement.estimateStatus === "REJECTED" ? .25 : .9}>
      <line {...lineProps(measurement.start, measurement.end, width, height)} stroke={color} strokeWidth="2.5" strokeDasharray={estimated ? "9 7" : undefined} markerStart="url(#dimension-arrow)" markerEnd="url(#dimension-arrow)" />
      {layout.leader && <line x1={layout.anchor.x * width} y1={layout.anchor.y * height} x2={layout.position.x * width} y2={layout.position.y * height} stroke={color} strokeWidth="1" />}
      <rect x={layout.position.x * width - (layout.compact ? 40 : 62)} y={layout.position.y * height - 19} width={layout.compact ? 80 : 124} height="22" rx="6" fill="rgba(15,23,42,.92)" />
      <text x={layout.position.x * width} y={layout.position.y * height - 4} textAnchor="middle" fill="white" fontSize={layout.compact ? "10" : "12"}>{layout.compact && label.length > 13 ? `${label.slice(0, 12)}…` : label}</text>
    </g>;
  })}</>;
}

function visibleReferences(state: SceneState) {
  if (!state.view.layers.CALIBRATION) return [];
  const filtered = state.calibration.references.filter((reference) => reference.visible && (state.measurementFilter === "ALL" || state.measurementFilter === "ACTIVE" && reference.active || state.measurementFilter === "SELECTED_OBJECT" && reference.objectId === state.selectedObjectId || state.measurementFilter === "CALIBRATION" && reference.affectsScale));
  if (state.view.preset !== "CLEAN") return filtered;
  const selected = filtered.find((reference) => reference.id === state.selectedReferenceId);
  const contextual = filtered.filter((reference) => reference.id !== selected?.id && reference.active && reference.residualStatus !== "OUTLIER").slice(0, 2);
  return selected ? [selected, ...contextual] : contextual;
}

function placeHumanAt(state: SceneState, id: string, point: NormalizedPoint, width: number, height: number) {
  const humans = state.humans.map((human) => human.id === id ? placeSingleHuman(human, snapPointToFloor(point, state.calibration.floorBaseline), state.calibration, width, height, human.placement.orientationDeg, "FREE", null) : human);
  return { ...state, humans };
}

function placeSingleHuman(human: SceneHuman, point: NormalizedPoint, calibration: SceneState["calibration"], width: number, height: number, orientationDeg: number, positionMode: SceneHuman["placement"]["positionMode"], attachedObjectId: string | null): SceneHuman {
  const scale = estimateLocalScale(calibration, point, width, height);
  const pixelsPerCm = scale?.pixelsPerCm ?? human.placement.lastScalePxPerCm ?? Math.max(.35, height * .003);
  const pose = buildAnthropometricPose(human.profile, point, pixelsPerCm, width, height, human.pose.preset === "CUSTOM" ? "STANDING" : human.pose.preset, orientationDeg, human.pose);
  return { ...human, visible: true, constraints: createConstraintGraph(human.profile), pose, placement: { ...human.placement, root: pose.joints.pelvisRoot, leftFootContact: pose.joints.leftFoot, rightFootContact: pose.joints.rightFoot, contactPoint: point, floorPinned: calibration.floorBaseline !== null, attachedObjectId, positionMode, orientationDeg, facingPreset: attachedObjectId ? "TOWARD_OBJECT" : human.placement.facingPreset, lastScalePxPerCm: pixelsPerCm, scaleStatus: scale?.status ?? "LOCAL_ONLY" } };
}

function moveHumanInPerspective(state: SceneState, id: string, dx: number, dy: number, width: number, height: number) {
  const humans = state.humans.map((human) => {
    if (human.id !== id || human.locked) return human;
    const requested = { x: clamp(human.placement.contactPoint.x + dx), y: clamp(human.placement.contactPoint.y + dy) };
    const point = human.placement.floorPinned ? snapPointToFloor(requested, state.calibration.floorBaseline) : requested;
    const scale = estimateLocalScale(state.calibration, point, width, height);
    const moved = moveHumanRootUniform(human, point, human.pose.scaleLocked ? scale?.pixelsPerCm ?? human.placement.lastScalePxPerCm : human.placement.lastScalePxPerCm, width, height);
    return { ...moved, placement: { ...moved.placement, contactPoint: point, lastScalePxPerCm: scale?.pixelsPerCm ?? moved.placement.lastScalePxPerCm, scaleStatus: scale?.status ?? "LOCAL_ONLY" } };
  });
  return { ...state, humans };
}

function rotateHuman(human: SceneHuman, point: NormalizedPoint, width: number, height: number): SceneHuman {
  const orientation = Math.atan2((point.y - human.placement.contactPoint.y) * height, (point.x - human.placement.contactPoint.x) * width) * 180 / Math.PI;
  const pixelsPerCm = human.placement.lastScalePxPerCm ?? Math.max(.35, height * .003);
  const pose = buildAnthropometricPose(human.profile, human.placement.contactPoint, pixelsPerCm, width, height, human.pose.preset === "CUSTOM" ? "STANDING" : human.pose.preset, orientation, human.pose);
  return { ...human, pose, placement: { ...human.placement, root: pose.joints.pelvisRoot, leftFootContact: pose.joints.leftFoot, rightFootContact: pose.joints.rightFoot, orientationDeg: orientation, facingPreset: "CUSTOM" } };
}

function rescaleLockedHumans(state: SceneState, width: number, height: number) {
  const calibration = rebuildPerspectiveField(state.calibration);
  return { ...state, calibration, humans: state.humans.map((human) => human.pose.scaleLocked ? placeSingleHuman(human, human.placement.contactPoint, calibration, width, height, human.placement.orientationDeg, human.placement.positionMode, human.placement.attachedObjectId) : human) };
}

function floorPointNearObject(object: SceneObject, floor: SceneState["calibration"]["floorBaseline"]): NormalizedPoint {
  const point = { x: clamp(object.bbox.x + object.bbox.width / 2), y: clamp(object.bbox.y + object.bbox.height + .08) };
  return snapPointToFloor(point, floor);
}

function snapPointToFloor(point: NormalizedPoint, floor: SceneState["calibration"]["floorBaseline"]): NormalizedPoint {
  if (!floor) return point;
  const dx = floor.end.x - floor.start.x, ratio = Math.abs(dx) < .0001 ? .5 : (point.x - floor.start.x) / dx;
  return { x: point.x, y: clamp(floor.start.y + (floor.end.y - floor.start.y) * ratio) };
}

function angleToObject(point: NormalizedPoint, object: SceneObject) { return Math.atan2(object.bbox.y + object.bbox.height / 2 - point.y, object.bbox.x + object.bbox.width / 2 - point.x) * 180 / Math.PI; }

function applyViewPreset(state: SceneState, preset: SceneViewPreset): SceneState {
  const layers = preset === "CLEAN" ? { CALIBRATION: true, OBJECT_DIMENSIONS: false, USER_MEASUREMENTS: true, HUMAN_REACH: false, SUGGESTIONS: false, DEBUG: false }
    : preset === "DIMENSIONS" ? { CALIBRATION: false, OBJECT_DIMENSIONS: true, USER_MEASUREMENTS: true, HUMAN_REACH: false, SUGGESTIONS: true, DEBUG: false }
      : preset === "CALIBRATION" ? { CALIBRATION: true, OBJECT_DIMENSIONS: false, USER_MEASUREMENTS: false, HUMAN_REACH: false, SUGGESTIONS: false, DEBUG: false }
        : { CALIBRATION: false, OBJECT_DIMENSIONS: false, USER_MEASUREMENTS: false, HUMAN_REACH: true, SUGGESTIONS: false, DEBUG: false };
  return { ...state, view: { ...state.view, preset, layers } };
}

function addInteractionPoint(update: (fn: (state: SceneState) => SceneState) => void, object: SceneObject, type: ObjectInteractionPointType, name: string) {
  const position = type === "PLACEMENT_POINT" ? { x: object.bbox.x + object.bbox.width * .72, y: object.bbox.y + object.bbox.height * .35 } : type === "GRIP_POINT" ? { x: object.bbox.x + object.bbox.width * .25, y: object.bbox.y + object.bbox.height * .45 } : { x: object.bbox.x + object.bbox.width / 2, y: object.bbox.y + object.bbox.height * .3 };
  updateObject(update, object.id, { interactionPoints: [...object.interactionPoints, { id: crypto.randomUUID(), name, type, position: { x: clamp(position.x), y: clamp(position.y) }, visible: true }] });
}
function newObject(bbox: NormalizedBox): SceneObject { return { id: crypto.randomUUID(), sourceClass: null, type: "OTHER", name: "Nowy element", bbox, detectorConfidence: null, source: "USER", status: "USER_ADDED", visible: true, locked: false, measurements: emptyMeasurements(), geometryMeasurements: [], interactionPoints: [], referencePoint: null }; }
function mergeDetections(state: SceneState, detection: SceneDetection | null): SceneState {
  if (!detection) return state;
  const objects = state.objects.length ? state.objects : detection.candidates.map((candidate) => ({ ...newObject(candidate.bounding_box), id: candidate.id, sourceClass: candidate.source_class, type: candidate.suggested_scene_type, name: objectLabels[candidate.suggested_scene_type], detectorConfidence: candidate.confidence, source: candidate.source, status: "DETECTED" as const }));
  const known = new Set(state.workerSuggestions.map((suggestion) => suggestion.id));
  const workerSuggestions = [...state.workerSuggestions, ...(detection.dimension_suggestions ?? []).filter((suggestion) => !known.has(suggestion.id))];
  return { ...state, objects, workerSuggestions };
}
function updateObject(update: (fn: (state: SceneState) => SceneState) => void, id: string, patch: Partial<SceneObject>) { update((state) => ({ ...state, objects: state.objects.map((object) => object.id === id ? { ...object, ...patch } : object) })); }
function updateMeasurement(update: (fn: (state: SceneState) => SceneState) => void, id: string, key: ObjectDimensionKey, value: number | null) { update((state) => ({ ...state, objects: state.objects.map((object) => object.id === id ? { ...object, measurements: { ...object.measurements, [key]: value }, status: object.status === "DETECTED" ? "USER_MODIFIED" : object.status } : object) })); }

function acceptWorkerSuggestion(update: (fn: (state: SceneState) => SceneState) => void, snapshot: SceneState, suggestionId: string) {
  const suggestion = snapshot.workerSuggestions.find((item) => item.id === suggestionId); if (!suggestion) return;
  const measurement = workerSuggestionToMeasurement(suggestion, dimensionKeyLabel(suggestion.dimension_type));
  update((state) => ({
    ...state,
    workerSuggestions: state.workerSuggestions.map((item) => item.id === suggestionId ? { ...item, status: "ACCEPTED" } : item),
    objects: state.objects.map((object) => object.id !== suggestion.object_id ? object : {
      ...object,
      geometryMeasurements: object.geometryMeasurements.some((item) => item.id === measurement.id || item.reason === measurement.reason && item.dimensionKey === measurement.dimensionKey) ? object.geometryMeasurements : [...object.geometryMeasurements, measurement],
      measurements: suggestion.estimated_value_cm !== null && object.measurements[suggestion.dimension_type] === null ? { ...object.measurements, [suggestion.dimension_type]: suggestion.estimated_value_cm } : object.measurements,
    }),
    view: { ...state.view, layers: { ...state.view.layers, SUGGESTIONS: true, OBJECT_DIMENSIONS: true } },
  }));
}

function rejectWorkerSuggestion(update: (fn: (state: SceneState) => SceneState) => void, suggestionId: string) { update((state) => ({ ...state, workerSuggestions: state.workerSuggestions.map((item) => item.id === suggestionId ? { ...item, status: "REJECTED" } : item) })); }
function confirmEstimatedMeasurement(update: (fn: (state: SceneState) => SceneState) => void, objectId: string, measurementId: string) { update((state) => ({ ...state, objects: state.objects.map((object) => object.id !== objectId ? object : { ...object, geometryMeasurements: object.geometryMeasurements.map((measurement) => measurement.id === measurementId ? { ...measurement, source: "USER_CONFIRMED_ESTIMATE", estimateStatus: "CONFIRMED" } : measurement) }) })); }
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
function dimensionKeyLabel(key: ObjectDimensionKey) { return ({ heightCm: "Wysokość", widthCm: "Szerokość", depthCm: "Głębokość", workSurfaceHeightCm: "Wysokość powierzchni", lowerEdgeHeightCm: "Wysokość dolnej krawędzi", upperEdgeHeightCm: "Wysokość górnej krawędzi", seatHeightCm: "Wysokość siedziska", seatWidthCm: "Szerokość siedziska", backrestHeightCm: "Wysokość oparcia", seatDepthCm: "Głębokość siedziska", screenCenterHeightCm: "Wysokość środka ekranu", screenHeightCm: "Wysokość ekranu", userDistanceCm: "Odległość od operatora", keyShelfHeightCm: "Wysokość półki", workingWidthCm: "Szerokość robocza", controlHeightCm: "Wysokość sterowania" })[key]; }
function provenanceLabel(source: GeometryMeasurement["source"]) { return ({ USER_MEASURED: "Pomiar użytkownika", WORKER_SUGGESTED: "Sugestia Workera", SCENE_ESTIMATED: "Estymacja ze sceny", USER_CONFIRMED_ESTIMATE: "Estymacja potwierdzona przez użytkownika", UNKNOWN: "Nieznane źródło" })[source]; }
function residualStatusLabel(status: CalibrationReference["residualStatus"]) { return ({ UNASSESSED: "nieoceniona", GOOD: "spójna", WEAK: "słaba", OUTLIER: "odstająca" })[status]; }
function scaleStatusLabel(status: SceneState["calibration"]["scaleField"]["status"]) { return ({ NO_SCALE: "brak skali", LOCAL_ONLY: "tylko lokalna", PERSPECTIVE_PARTIAL: "perspektywa częściowa", PERSPECTIVE_GOOD: "perspektywa dobra", INCONSISTENT: "referencje niespójne" })[status]; }
const postureOptions: [HumanPosture, string][] = [["STANDING", "Stojąca"], ["SEATED", "Siedząca"], ["REACHING", "Sięganie"], ["FORWARD_LEAN", "Pochylenie do przodu"], ["WORK_SURFACE", "Praca przy blacie"], ["ONE_HANDED", "Praca jednorącz"], ["TWO_HANDED", "Praca oburącz"]];
