"use client";

import { useState } from "react";
import { AlertTriangle, Calculator, ChevronRight, CircleDot, Info, LoaderCircle, Plus } from "lucide-react";

import type {
  GeometryReadinessGoal, MeasurementKind, SceneGeometryConstraint, SceneObject,
  SceneRegionType, SceneShapeAssumption, SceneState,
} from "@/types/photo-scene";

const inputClass = "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20";
const goalLabels: Record<GeometryReadinessGoal, string> = {
  HUMAN_PLACEMENT: "Osadzenie operatora", WORK_HEIGHT: "Wysokość robocza", REACH: "Zasięg",
  COLLISION: "Kolizje", FULL_3D: "Pełny model 3D",
};

export function GeometryPanel({ state, starting, error, onCalculate, onPrepareMeasurement, advanced, setAdvanced }: {
  state: SceneState;
  starting: boolean;
  error: string | null;
  onCalculate: () => Promise<void>;
  onPrepareMeasurement: (kind: MeasurementKind, objectId: string | null) => void;
  advanced: boolean;
  setAdvanced: (value: boolean) => void;
}) {
  const reconstruction = state.reconstructionState;
  const hasInput = state.regions.length > 0 || state.constraintGraph.constraints.length > 0 || state.calibration.references.length > 0;
  const next = reconstruction.nextBestMeasurements[0] ?? null;
  return <div className="space-y-4">
    <section className="rounded-xl border-2 border-primary/30 bg-primary/5 p-4">
      <p className="text-[10px] font-bold uppercase tracking-wider text-primary">Rekonstrukcja sceny</p>
      <h3 className="mt-1 text-base font-bold">{reconstruction.status === "SOLVED" ? "Geometria gotowa" : reconstruction.status === "PARTIAL" ? "Geometria częściowa" : reconstruction.status === "INCONSISTENT" ? "Wymiary wymagają sprawdzenia" : "Oblicz spójny model sceny"}</h3>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">Regiony, znane wymiary i płaszczyzny są dopasowywane razem. Wpisane wartości nie są automatycznie zmieniane.</p>
      <button disabled={!hasInput || starting} onClick={() => void onCalculate()} className="ui-button-primary mt-4 w-full justify-center disabled:cursor-not-allowed disabled:opacity-50">
        {starting ? <LoaderCircle className="size-4 animate-spin" /> : <Calculator className="size-4" />}
        {reconstruction.status === "SOLVED" || reconstruction.status === "PARTIAL" ? "Przelicz ponownie" : "Oblicz geometrię sceny"}
      </button>
      {!hasInput && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">Najpierw zaznacz co najmniej jeden obszar albo dodaj wymiar.</p>}
      {error && <p role="alert" className="mt-2 text-xs text-red-600">{error}</p>}
    </section>

    <section className="space-y-2">
      <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-bold">Gotowość według celu</h3><span className="text-[10px] font-semibold text-muted-foreground">bez ogólnego procentu</span></div>
      {(Object.keys(goalLabels) as GeometryReadinessGoal[]).map((goal) => {
        const item = reconstruction.readiness[goal];
        const ready = item.status === "READY";
        return <div key={goal} className="rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold">{goalLabels[goal]}</span><span className={`rounded-full px-2 py-1 text-[9px] font-bold ${ready ? "bg-emerald-500/10 text-emerald-600" : item.status === "INVALID" ? "bg-red-500/10 text-red-600" : "bg-amber-500/10 text-amber-700 dark:text-amber-300"}`}>{readinessLabel(item.status)}</span></div>
          {item.reasons[0] && <p className="mt-1 text-[11px] text-muted-foreground">{item.reasons[0]}</p>}
        </div>;
      })}
    </section>

    {next && <section className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4">
      <p className="text-[10px] font-bold uppercase tracking-wider text-cyan-700 dark:text-cyan-300">Najbardziej informacyjny kolejny pomiar</p>
      <p className="mt-2 text-sm font-semibold">{next.reason}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{next.expectedBenefit}</p>
      <button onClick={() => onPrepareMeasurement(next.measurementKind, next.objectId)} className="ui-button-secondary mt-3 w-full justify-center">Dodaj ten wymiar <ChevronRight className="size-4" /></button>
    </section>}

    {reconstruction.conflicts.length > 0 && <section className="rounded-xl border border-red-500/30 bg-red-500/5 p-3">
      <div className="flex items-center gap-2 text-sm font-bold text-red-600"><AlertTriangle className="size-4" />{reconstruction.conflicts.length} wymiar wymaga sprawdzenia</div>
      {reconstruction.conflicts.map((conflict) => <p key={conflict.id} className="mt-2 text-xs">{conflict.message}</p>)}
      <p className="mt-2 text-[11px] text-muted-foreground">Popraw wymiar, wyłącz pomiar albo zmień założenie kształtu. Dane źródłowe pozostały bez zmian.</p>
    </section>}

    {reconstruction.autoRepairs.length > 0 && <details className="rounded-xl border border-amber-500/30 p-3">
      <summary className="cursor-pointer text-sm font-bold">{reconstruction.autoRepairs.length} automatyczne korekty geometrii</summary>
      <div className="mt-2 space-y-2">{reconstruction.autoRepairs.map((repair) => <p key={repair.id} className="text-xs"><strong>{repair.type}</strong> · {repair.reason} · Δ {repair.delta.toFixed(2)} {repair.unit}</p>)}</div>
    </details>}

    <label className="flex items-center justify-between rounded-lg border border-border p-3 text-xs"><span><strong>Tryb zaawansowany</strong><small className="mt-1 block text-muted-foreground">Płaszczyzny, residuals, outliery i model kamery.</small></span><input type="checkbox" checked={advanced} onChange={(event) => setAdvanced(event.target.checked)} /></label>
    {advanced && <section className="space-y-2 rounded-xl border border-border bg-muted/20 p-3 text-xs">
      <div className="flex justify-between"><span>Stan solvera</span><strong>{reconstruction.status}</strong></div>
      <div className="flex justify-between"><span>Camera Model V2</span><strong>{reconstruction.cameraModel.status}</strong></div>
      <div className="flex justify-between"><span>Outliery</span><strong>{reconstruction.outlierConstraintIds.length}</strong></div>
      <div className="flex justify-between"><span>Ograniczenia</span><strong>{state.constraintGraph.constraints.length}</strong></div>
      {Object.entries(reconstruction.constraintResiduals).map(([id, residual]) => <div key={id} className="flex justify-between gap-2"><span className="truncate">{id}</span><strong>{residual.toFixed(2)} cm</strong></div>)}
    </section>}
  </div>;
}

export function ObjectGeometryV3Panel({ state, object, update, onDrawRegion, onDrawMeasurement }: {
  state: SceneState;
  object: SceneObject;
  update: (producer: (state: SceneState) => SceneState) => void;
  onDrawRegion: (type: SceneRegionType) => void;
  onDrawMeasurement: () => void;
}) {
  const [kind, setKind] = useState<"HEIGHT" | "WIDTH" | "DEPTH">("HEIGHT");
  const [value, setValue] = useState("");
  const [cornerIndex, setCornerIndex] = useState(0);
  const constraints = state.constraintGraph.constraints.filter((item) => item.objectId === object.id && ["HEIGHT", "WIDTH", "DEPTH"].includes(item.type));
  const primaryRegion = state.regions.find((region) => object.regionIds.includes(region.id));
  const targetPoint = primaryRegion?.polygonImageNormalized[cornerIndex]?.effective ?? null;
  function addConstraint() {
    const numeric = Number(value.replace(",", "."));
    if (!Number.isFinite(numeric) || numeric <= 0) return;
    const constraint: SceneGeometryConstraint = {
      id: crypto.randomUUID(), type: kind, nodeIds: [`object:${object.id}`], objectId: object.id,
      regionId: primaryRegion?.id ?? null,
      target: targetPoint ? { kind: "POINT", id: `${primaryRegion?.id}:corner:${cornerIndex + 1}`, point: targetPoint } : { kind: "OBJECT", id: object.id, point: null },
      rawValue: numeric, effectiveValue: numeric, unit: "cm", source: "USER_PROVIDED", weight: 1,
      useForSolver: true, status: "ACTIVE", residual: null, imageSegment: null,
    };
    update((current) => ({ ...current, constraintGraph: { ...current.constraintGraph, constraints: [...current.constraintGraph.constraints, constraint] }, reconstructionState: { ...current.reconstructionState, status: "UNSOLVED", readiness: Object.fromEntries(Object.entries(current.reconstructionState.readiness).map(([goal, item]) => [goal, { ...item, status: "STALE", reasons: ["Geometria zmieniła się — przelicz model."] }])) as SceneState["reconstructionState"]["readiness"] } }));
    setValue("");
  }
  function toggleAssumption(assumption: SceneShapeAssumption) {
    const selected = object.shapeAssumptions.includes(assumption);
    update((current) => ({ ...current, objects: current.objects.map((item) => item.id === object.id ? { ...item, shapeAssumptions: selected ? item.shapeAssumptions.filter((value) => value !== assumption) : [...item.shapeAssumptions.filter((value) => value !== "FREEFORM"), assumption] } : item) }));
  }
  return <div className="space-y-3">
    {(["TABLE", "WORK_SURFACE"].includes(object.type)) && <section className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-3">
      <p className="text-[10px] font-bold uppercase text-cyan-700 dark:text-cyan-300">Kreator stołu / blatu</p>
      <ol className="mt-2 space-y-2 text-xs">
        <li className="flex gap-2"><CircleDot className="mt-0.5 size-3 text-primary" />Zaznacz cztery widoczne narożniki powierzchni.</li>
        <li className="flex gap-2"><CircleDot className="mt-0.5 size-3 text-primary" />Dodaj tylko te wysokości, szerokości i głębokości, które znasz.</li>
        <li className="flex gap-2"><CircleDot className="mt-0.5 size-3 text-primary" />Uruchom wspólne dopasowanie geometrii.</li>
      </ol>
      <button onClick={() => onDrawRegion("WORK_SURFACE")} className="ui-button-primary mt-3 w-full justify-center">Zaznacz powierzchnię blatu</button>
    </section>}

    <section className="rounded-xl border border-border p-3">
      <h4 className="text-sm font-bold">Znane wymiary obiektu</h4>
      <p className="mt-1 text-[11px] text-muted-foreground">Możesz dodać 2, 3, 4 lub więcej pomiarów każdego rodzaju. Są ograniczeniami obiektu, nie osobnymi skalami.</p>
      <div className="mt-3 grid grid-cols-[1fr_1fr_auto] gap-2">
        <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)} className={inputClass}><option value="HEIGHT">Wysokość</option><option value="WIDTH">Szerokość</option><option value="DEPTH">Głębokość</option></select>
        <input value={value} onChange={(event) => setValue(event.target.value)} inputMode="decimal" placeholder="cm" className={inputClass} />
        <button onClick={addConstraint} aria-label="Dodaj wymiar" className="ui-button-secondary px-3"><Plus className="size-4" /></button>
      </div>
      {primaryRegion && primaryRegion.polygonImageNormalized.length > 0 && <label className="mt-2 block text-[11px] font-semibold">Dotyczy punktu / narożnika<select value={cornerIndex} onChange={(event) => setCornerIndex(Number(event.target.value))} className={`${inputClass} mt-1`}><option value={0}>Narożnik A</option>{primaryRegion.polygonImageNormalized.slice(1).map((_point, index) => <option key={index + 1} value={index + 1}>Narożnik {String.fromCharCode(66 + index)}</option>)}</select></label>}
      <button onClick={onDrawMeasurement} className="mt-2 text-xs font-semibold text-primary">Narysuj dokładne punkty wymiaru →</button>
      <div className="mt-3 space-y-2">{constraints.map((constraint) => <div key={constraint.id} className="flex items-center justify-between gap-2 rounded-lg bg-muted/40 p-2 text-xs"><span>{constraintLabel(constraint.type)} · {constraint.source === "USER_PROVIDED" ? "pomiar użytkownika" : constraint.source}</span><span className="flex items-center gap-2"><strong>{constraint.rawValue} cm</strong>{constraint.status === "OUTLIER" && <span className="text-amber-600">odstający</span>}<button aria-label="Usuń wymiar" onClick={() => update((current) => ({ ...current, constraintGraph: { ...current.constraintGraph, constraints: current.constraintGraph.constraints.filter((item) => item.id !== constraint.id) } }))} className="text-muted-foreground">×</button></span></div>)}</div>
    </section>

    <section className="rounded-xl border border-border p-3">
      <h4 className="text-sm font-bold">Założenia kształtu</h4>
      <p className="mt-1 text-[11px] text-muted-foreground">Założenia można wyłączyć dla obiektu nieregularnego.</p>
      <div className="mt-2 grid grid-cols-2 gap-2">{(["RECTANGULAR", "PLANAR", "PARALLEL_EDGES"] as SceneShapeAssumption[]).map((assumption) => <label key={assumption} className="flex items-center gap-2 rounded-lg border border-border p-2 text-[10px]"><input type="checkbox" checked={object.shapeAssumptions.includes(assumption)} onChange={() => toggleAssumption(assumption)} />{assumption}</label>)}</div>
    </section>
    <p className="flex gap-2 rounded-lg bg-muted/40 p-3 text-[11px] text-muted-foreground"><Info className="size-4 shrink-0" />Brak wymiaru pozostaje stanem UNKNOWN. System nie podstawia typowych rozmiarów stołu.</p>
  </div>;
}

export function ReconstructionProgress({ status }: { status: SceneState["reconstructionState"]["status"] }) {
  if (!(["QUEUED", "SOLVING"] as string[]).includes(status)) return null;
  const steps = ["Sprawdzam dane", "Dopasowuję perspektywę", "Wyznaczam płaszczyzny", "Dopasowuję obiekty", "Sprawdzam spójność", "Gotowe"];
  return <div role="status" className="rounded-xl border border-cyan-500/30 bg-slate-950 p-4 text-cyan-100"><div className="flex items-center gap-2 text-sm font-bold"><LoaderCircle className="size-4 animate-spin" />Obliczanie geometrii sceny</div><ol className="mt-3 grid gap-1 text-xs text-cyan-100/70">{steps.map((step, index) => <li key={step} className="flex items-center gap-2"><span className="w-4 text-right">{index + 1}.</span>{step}</li>)}</ol></div>;
}

function constraintLabel(type: SceneGeometryConstraint["type"]) { return type === "HEIGHT" ? "Wysokość" : type === "WIDTH" ? "Szerokość" : type === "DEPTH" ? "Głębokość" : type; }
function readinessLabel(status: SceneState["reconstructionState"]["readiness"][GeometryReadinessGoal]["status"]) { return ({ READY: "Gotowe", PARTIAL: "Częściowo", NEEDS_HEIGHT: "Potrzebna wysokość", NEEDS_WIDTH: "Potrzebna szerokość", NEEDS_DEPTH: "Potrzebna głębokość", INSUFFICIENT: "Brak danych", INVALID: "Wymaga uwagi", STALE: "Nieaktualne" })[status]; }
