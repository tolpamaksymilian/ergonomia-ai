"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Check, HelpCircle, X } from "lucide-react";

import { MEASUREMENT_KIND_LABELS, measurementDirectionWarning, semanticsForReferenceType } from "@/lib/photo-scene/measurement-semantics";
import type {
  MeasurementAxis, MeasurementKind, MeasurementPlane, MeasurementPurpose,
  NormalizedPoint, ReferenceDimensionType,
} from "@/types/photo-scene";

export type GuidedReferenceInput = {
  name: string;
  type: ReferenceDimensionType;
  valueCm: number;
  measurementKind: MeasurementKind;
  axis: MeasurementAxis;
  plane: MeasurementPlane;
  purpose: MeasurementPurpose;
  useForCalibration: boolean;
  confirmedDirectionWarning: boolean;
};

export function GuidedCalibrationForm({
  start, end, objectName, verticalDirection, initialType = "HEIGHT", onSave, onCancel,
}: {
  start: NormalizedPoint;
  end: NormalizedPoint;
  objectName: string | null;
  verticalDirection: NormalizedPoint | null;
  initialType?: ReferenceDimensionType;
  onSave: (input: GuidedReferenceInput) => void;
  onCancel: () => void;
}) {
  const [type, setType] = useState<ReferenceDimensionType>(initialType);
  const [name, setName] = useState(objectName ? `Wymiar: ${objectName}` : defaultReferenceName(initialType));
  const [value, setValue] = useState("");
  const [useForCalibration, setUseForCalibration] = useState(() => semanticsForReferenceType(initialType).axis === "VERTICAL");
  const [warningConfirmed, setWarningConfirmed] = useState(false);
  const semantics = useMemo(() => semanticsForReferenceType(type), [type]);
  const warning = measurementDirectionWarning(start, end, semantics, verticalDirection);

  const canSave = Number(value) > 0 && (!warning || warningConfirmed);
  return <section className="space-y-3 rounded-xl border-2 border-cyan-500/40 bg-cyan-500/5 p-3" aria-label="Kalibracja krok po kroku">
    <div className="flex items-start justify-between gap-3">
      <div><span className="text-[10px] font-bold uppercase tracking-wider text-cyan-600">Krok 3 z 4</span><h3 className="mt-1 font-semibold">Opisz rzeczywisty wymiar</h3></div>
      <button onClick={onCancel} aria-label="Anuluj pomiar" className="rounded-md p-1 hover:bg-muted"><X className="size-4" /></button>
    </div>
    <label className="block text-xs font-semibold">Co mierzysz?<select value={type} onChange={(event) => { const nextType = event.target.value as ReferenceDimensionType, next = semanticsForReferenceType(nextType); setType(nextType); setUseForCalibration(next.axis === "VERTICAL" && next.purpose !== "INFORMATION_ONLY"); setWarningConfirmed(false); }} className={controlClass}>
      <option value="HEIGHT">Wysokość od podłogi</option><option value="WORK_SURFACE_HEIGHT">Wysokość blatu</option>
      <option value="SHELF_HEIGHT">Wysokość półki</option><option value="WIDTH">Szerokość</option>
      <option value="DEPTH">Głębokość</option><option value="DISTANCE">Odległość po podłodze</option><option value="CUSTOM">Informacyjny / inny</option>
    </select></label>
    <label className="block text-xs font-semibold">Nazwa<input value={name} onChange={(event) => setName(event.target.value)} className={controlClass} /></label>
    <label className="block text-xs font-semibold">Rzeczywista wartość [cm]<input type="number" min="0.1" step="0.1" value={value} onChange={(event) => setValue(event.target.value)} className={controlClass} /></label>
    <div className="rounded-lg border border-border bg-card p-3 text-xs">
      <strong>{MEASUREMENT_KIND_LABELS[semantics.measurementKind]}</strong>
      <p className="mt-1 text-muted-foreground">Oś: {semantics.axis} · płaszczyzna: {semantics.plane}</p>
    </div>
    {type === "DEPTH" && <div className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs"><AlertTriangle className="size-4 shrink-0" /><span>Głębokość na pojedynczym zdjęciu może być silnie zniekształcona przez perspektywę. Nie będzie używana do pionowej skali człowieka.</span></div>}
    {warning && <label className="flex gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs"><input type="checkbox" checked={warningConfirmed} onChange={(event) => setWarningConfirmed(event.target.checked)} /><span><strong>Sprawdź kierunek.</strong><br />{warning}</span></label>}
    <label className="flex items-start gap-2 rounded-lg border border-border p-3 text-xs">
      <input type="checkbox" checked={useForCalibration} disabled={semantics.axis !== "VERTICAL"} onChange={(event) => setUseForCalibration(event.target.checked)} />
      <span><strong>Użyj do kalibracji</strong><small className="mt-1 block text-muted-foreground">Dostępne wyłącznie dla potwierdzonych wysokości pionowych. Zwykłe wymiary obiektu są domyślnie wyłączone.</small></span>
    </label>
    <div className="grid grid-cols-2 gap-2"><button onClick={onCancel} className="ui-button-secondary justify-center">Anuluj</button><button disabled={!canSave} onClick={() => onSave({ name, type, valueCm: Number(value), ...semantics, useForCalibration, confirmedDirectionWarning: warningConfirmed })} className="ui-button-primary justify-center"><Check className="size-4" />Zapisz referencję</button></div>
  </section>;
}

export function CalibrationHelp() {
  return <details className="rounded-xl border border-border p-3 text-xs">
    <summary className="flex cursor-pointer items-center gap-2 font-semibold"><HelpCircle className="size-4" />Jak prawidłowo oznaczyć wymiar?</summary>
    <div className="mt-3 grid gap-3 sm:grid-cols-3">
      <Diagram title="Wysokość" lines={["● Górny punkt", "│", "│ 80 cm", "│", "● Punkt na podłodze", "──────── PODŁOGA"]} text="Od podłogi bezpośrednio pod elementem do znanego górnego punktu." />
      <Diagram title="Szerokość" lines={["●────────●", "← 120 cm →", "ta sama krawędź"]} text="Oba końce tej samej widocznej krawędzi i płaszczyzny." />
      <Diagram title="Głębokość" lines={["przód ●────● tył", "70 cm"]} text="Tylko opis obiektu, dopóki nie ma kalibracji jego płaszczyzny." />
    </div>
    <div className="mt-3 rounded-lg border border-red-500/25 bg-red-500/5 p-2 text-muted-foreground"><strong className="text-red-600">Niepoprawnie:</strong> przekątna łącząca niepowiązane punkty sceny nie jest wysokością.</div>
  </details>;
}

export function GuidedCanvasInstruction({ step, targetRegion }: { step: 1 | 2; targetRegion?: "LEFT" | "RIGHT" | "CENTER" | null }) {
  return <div className="pointer-events-none absolute left-1/2 top-4 z-20 w-[min(92%,520px)] -translate-x-1/2 rounded-xl border border-cyan-300/40 bg-slate-950/90 p-4 text-center text-sm text-white shadow-xl">
    <span className="text-[10px] font-bold uppercase tracking-widest text-cyan-300">Kalibracja krok po kroku · krok {step}</span>
    <p className="mt-1 font-semibold">{step === 1 ? "Kliknij punkt na podłodze bezpośrednio pod wybranym elementem." : "Kliknij górny punkt tej samej pionowej wysokości."}</p>
    {targetRegion && <small className="mt-1 block text-slate-300">Zalecany obszar: {targetRegion === "LEFT" ? "lewa część sceny" : targetRegion === "RIGHT" ? "prawa część sceny" : "środek sceny"}.</small>}
  </div>;
}

function Diagram({ title, lines, text }: { title: string; lines: string[]; text: string }) {
  return <div className="rounded-lg bg-muted/60 p-3"><strong>{title}</strong><pre className="my-2 overflow-hidden whitespace-pre-wrap font-mono text-[10px] leading-4 text-cyan-700 dark:text-cyan-300">{lines.join("\n")}</pre><p className="leading-5 text-muted-foreground">{text}</p></div>;
}

const controlClass = "mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20";

function defaultReferenceName(type: ReferenceDimensionType) {
  return ({
    HEIGHT: "Wysokość referencyjna",
    WORK_SURFACE_HEIGHT: "Wysokość blatu",
    SHELF_HEIGHT: "Wysokość półki",
    REACH_HEIGHT: "Wysokość punktu nad podłogą",
    WIDTH: "Szerokość referencyjna",
    DEPTH: "Głębokość referencyjna",
    DISTANCE: "Odległość po podłodze",
    CUSTOM: "Inny wymiar",
  })[type];
}
