"use client";

import { Calculator, CircleHelp, Play, ScanSearch } from "lucide-react";
import Image from "next/image";

import { manualInputLabel } from "@/config/manual-input-labels";
import { formatPercentage, formatTimestamp, UNKNOWN_VALUE } from "@/lib/analysis-review/formatters";
import type { AssessmentComponent, AssessmentMethodResult, AssessmentReview } from "@/lib/analysis-review/schemas";

export function AssessmentSection({ assessment, onSeek }: { assessment: AssessmentReview; onSeek: (time: number) => void }) {
  return (
    <section className="review-panel" aria-labelledby="assessment-title">
      <p className="review-eyebrow"><ScanSearch className="size-4" /> Metody ergonomiczne</p>
      <h2 id="assessment-title" className="mt-2 text-xl font-semibold">RULA i REBA</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">RULA i REBA to metody przesiewowej oceny postawy. System oblicza tylko elementy, dla których posiada wystarczające dane.</p>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <MethodCard result={assessment.rula} onSeek={onSeek} />
        <MethodCard result={assessment.reba} onSeek={onSeek} />
      </div>
      {!assessment.engineVersion && <p className="mt-4 flex gap-2 rounded-xl border border-dashed border-white/10 px-4 py-3 text-sm text-slate-500"><CircleHelp className="mt-0.5 size-4 shrink-0" />Ta analiza powstała przed dodaniem Assessment Engine. Pozostałe wyniki są nadal dostępne.</p>}
    </section>
  );
}

function MethodCard({ result, onSeek }: { result: AssessmentMethodResult; onSeek: (time: number) => void }) {
  return (
    <article className="min-w-0 rounded-2xl border border-sky-300/15 bg-sky-300/[0.035] p-5 sm:p-6">
      {result.keyframeUrl && <Image src={result.keyframeUrl} alt={`Pozycja reprezentatywna ${result.method}`} width={960} height={540} unoptimized className="mb-5 aspect-video w-full rounded-xl border border-white/10 object-cover" />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">{result.method}</p><h3 className="mt-2 text-lg font-semibold">{statusLabel(result.status)}</h3></div>
        <span className="rounded-full border border-white/10 bg-slate-950/40 px-3 py-1 text-xs text-slate-300">{qualityLabel(result.applicability)}</span>
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
        <Datum label={result.status === "COMPLETE" ? "Wynik" : "Możliwy zakres"} value={scoreLabel(result)} />
        <Datum label="Strona" value={result.side === "left" ? "Lewa" : result.side === "right" ? "Prawa" : UNKNOWN_VALUE} />
        <Datum label="Pozycja" value={formatTimestamp(result.timestamp)} />
        <Datum label="Pokrycie danych" value={formatPercentage(result.coverage)} />
      </dl>
      {result.status === "PARTIAL" && <p className="mt-4 text-xs leading-5 text-slate-500">Zakres wynika z parametrów, których nie można określić na podstawie nagrania. Nie jest to przedział ufności.</p>}
      {result.status === "INSUFFICIENT_DATA" && <p className="mt-4 text-sm leading-6 text-slate-400">Za mało wiarygodnych danych do obliczenia {result.method}.</p>}
      {result.missingInputs.length > 0 && <div className="mt-5"><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Brakujące informacje</p><ul className="mt-2 space-y-1 text-xs text-slate-400">{result.missingInputs.slice(0, 6).map((item) => <li key={item}>• {missingLabel(item)}</li>)}</ul></div>}
      <div className="mt-5 flex flex-wrap gap-2">
        {result.timestamp !== null && <button type="button" onClick={() => onSeek(result.timestamp!)} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-sky-300/20 bg-sky-300/10 px-3 py-2 text-xs font-semibold text-sky-100 focus-visible:outline-2 focus-visible:outline-sky-200"><Play className="size-4" />Pokaż moment</button>}
        {result.components.length > 0 && <details className="w-full rounded-xl border border-white/[0.08] bg-slate-950/30 p-3"><summary className="cursor-pointer list-none text-xs font-semibold text-slate-300 focus-visible:outline-2 focus-visible:outline-sky-200"><Calculator className="mr-2 inline size-4" />Szczegóły</summary><div className="mt-3 divide-y divide-white/[0.06]">{result.components.map((component) => <ComponentRow key={component.name} component={component} />)}</div></details>}
      </div>
    </article>
  );
}

function ComponentRow({ component }: { component: AssessmentComponent }) { return <div className="flex min-w-0 items-center justify-between gap-3 py-2 text-xs"><span className="min-w-0 break-words text-slate-300">{componentLabel(component.name)}</span><span className="shrink-0 text-right text-slate-500">{sourceLabel(component.source)} · {component.score ?? UNKNOWN_VALUE}</span></div>; }
function Datum({ label, value }: { label: string; value: string }) { return <div><dt className="text-[9px] uppercase tracking-wider text-slate-600">{label}</dt><dd className="mt-1 font-semibold text-slate-200">{value}</dd></div>; }
function scoreLabel(result: AssessmentMethodResult) { if (result.finalScore !== null) return String(result.finalScore); return result.scoreRange ? `${result.scoreRange.min}–${result.scoreRange.max}` : UNKNOWN_VALUE; }
function statusLabel(status: AssessmentMethodResult["status"]) { return status === "COMPLETE" ? "Wynik kompletny" : status === "PARTIAL" ? "Ocena częściowa" : "Niewystarczające dane"; }
function qualityLabel(value: AssessmentMethodResult["applicability"]) { return value === "GOOD" ? "Jakość dobra" : value === "LIMITED" ? "Jakość ograniczona" : "Za mało danych"; }
function sourceLabel(value: AssessmentComponent["source"]) { return ({ observed: "Z filmu", derived: "Obliczone z filmu", user_provided: "Podane przez użytkownika", assumed: "Założenie", unknown: "Brak danych" } as const)[value]; }
function componentLabel(value: string) { return ({ upper_arm: "Ramię", lower_arm: "Przedramię", wrist: "Nadgarstek", wrist_twist: "Skręt nadgarstka", neck: "Szyja", trunk: "Tułów", legs: "Nogi", muscle_use: "Praca mięśni", force_load: "Siła / obciążenie", load_force: "Siła / obciążenie", coupling: "Sprzężenie z przedmiotem", activity: "Aktywność" } as Record<string, string>)[value] ?? "Dodatkowy składnik metody"; }
function missingLabel(value: string) { return manualInputLabel(value); }
