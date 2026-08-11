"use client";

import { AlertCircle, Calculator, CheckCircle2, ChevronDown, Factory, FlaskConical, Scale, Weight } from "lucide-react";
import { useFormStatus } from "react-dom";

import { saveCompanyMethodInputs } from "@/app/panel/analizy/[id]/company-method-actions";
import { companyMethodSpecs, hazardSuggestions } from "@/lib/company-methods/specs";
import type { CompanyMethodsView } from "@/lib/company-methods/normalize";

export function CompanyMethodsSection({ analysisId, value, onSeek }: { analysisId: string; value: CompanyMethodsView | null; onSeek: (time: number) => void }) {
  const owas = value?.owas ?? null;
  const missing = value?.missingInputs ?? [];
  const dominantFrame = findDominantOwasFrame(owas);
  return <section className="review-panel" aria-labelledby="company-methods-title">
    <p className="review-eyebrow"><Factory className="size-4" /> Metody zakładowe</p>
    <div className="mt-2 flex flex-wrap items-end justify-between gap-3"><div><h2 id="company-methods-title" className="text-2xl font-semibold">OWAS i ocena kontekstowa</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Metody pozostają oddzielne od Risk Engine, RULA i REBA. Wartości manualne wymagają pomiaru lub potwierdzenia użytkownika.</p></div><span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.07] px-3 py-1.5 text-xs font-semibold text-cyan-100">{value?.version ?? "company-methods-v1.2-beta.1"}</span></div>
    <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MethodCard title="OWAS" icon={Weight} status={status(owas)} detail={owasSummary(owas)} />
      {value?.riskScore && status(value.riskScore) !== "REQUIRES_DATA" && <MethodCard title="Risk Score" icon={Calculator} status={status(value.riskScore)} detail={riskSummary(value.riskScore)} />}
      {!!value?.measurableFactors.length && <MethodCard title="Czynniki mierzalne" icon={Scale} status="MANUAL" detail="Pomiar zapisany" />}
      {value?.chemical && status(value.chemical) !== "REQUIRES_DATA" && <MethodCard title="Chemia" icon={FlaskConical} status={status(value.chemical)} detail="Dane uzupełnione ręcznie" />}
    </div>
    <OwasDetails value={owas} />
    {dominantFrame && <button type="button" onClick={() => onSeek(dominantFrame.time)} className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] px-4 py-3 text-left text-sm text-cyan-100 transition hover:bg-cyan-300/[0.1] focus-visible:outline-2 focus-visible:outline-cyan-200">Dominująca rozpoznana pozycja OWAS: kod {dominantFrame.code}, kategoria {dominantFrame.category}. Przejdź do {dominantFrame.time.toFixed(1)} s.</button>}
    <details className="mt-6 rounded-2xl border border-amber-300/15 bg-amber-300/[0.035] open:bg-amber-300/[0.05]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 focus-visible:outline-2 focus-visible:outline-amber-200"><span><span className="flex items-center gap-2 font-semibold"><AlertCircle className="size-4 text-amber-300" />Dane wymagające uzupełnienia</span><span className="mt-1 block text-sm text-slate-400">{missing.length ? `${missing.length} informacji może poprawić kompletność oceny.` : "Brak obowiązkowych uzupełnień dla aktywnych metod."}</span></span><ChevronDown className="size-5 text-slate-500" /></summary>
      <form action={saveCompanyMethodInputs} className="grid gap-5 border-t border-white/[0.08] p-5 xl:grid-cols-2">
        <input type="hidden" name="analysis_id" value={analysisId} />
        <Fieldset title="Informacje potrzebne do OWAS"><NumberField name="handled_load_kg" label="Masa przenoszonego przedmiotu [kg]" /><SelectField name="owas_forced_posture" label="Charakter pozycji" options={[["", "Nie określono"], ["forced", "Wymuszona"], ["unforced", "Niewymuszona"]]} /><p className="text-xs text-slate-500">System nie zgaduje masy na podstawie obrazu.</p></Fieldset>
        <Fieldset title="Risk Score — dane manualne"><TextField name="risk_activity" label="Wykonywana czynność" /><TextField name="risk_hazard_source" label="Źródło zagrożenia" /><TextField name="risk_hazard" label="Zagrożenie" list="company-hazards" /><datalist id="company-hazards">{hazardSuggestions.map((item) => <option key={item.id} value={item.label} />)}</datalist><div className="grid gap-3 sm:grid-cols-3"><SelectField name="risk_exposure" label="Ekspozycja" options={options(companyMethodSpecs.riskScore.thresholds.exposure)} /><SelectField name="risk_severity" label="Skutki" options={options(companyMethodSpecs.riskScore.thresholds.severity)} /><SelectField name="risk_probability" label="Prawdopodobieństwo" options={options(companyMethodSpecs.riskScore.thresholds.probability)} /></div></Fieldset>
        <Fieldset title="Czynnik mierzalny"><TextField name="measurement_label" label="Nazwa czynnika" /><div className="grid grid-cols-2 gap-3"><NumberField name="measurement" label="Pomiar P" /><NumberField name="measurement_limit" label="Limit Pmax" /></div></Fieldset>
        <Fieldset title="Chemia — dane manualne"><TextField name="chemical_name" label="Substancja" /><TextField name="chemical_h_statements" label="Zwroty H" /><TextField name="chemical_risk_level" label="Poziom ryzyka" /><label className="flex items-center gap-3 text-sm text-slate-300"><input type="checkbox" name="chemical_safe" className="size-4 accent-emerald-400" /> Produkt sklasyfikowany jako bezpieczny</label></Fieldset>
        <div className="xl:col-span-2 flex justify-end"><SubmitButton /></div>
      </form>
    </details>
  </section>;
}

function MethodCard({ title, icon: Icon, status: value, detail }: { title: string; icon: typeof Weight; status: string; detail: string }) { const ready = ["AUTOMATIC", "MANUAL"].includes(value); return <article className="rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4"><div className="flex items-start justify-between gap-2"><Icon className="size-5 text-cyan-300" /><span className={`rounded-full px-2 py-1 text-[9px] font-semibold uppercase ${ready ? "bg-emerald-300/10 text-emerald-200" : "bg-amber-300/10 text-amber-200"}`}>{statusLabel(value)}</span></div><h3 className="mt-4 font-semibold">{title}</h3><p className="mt-2 text-xs text-slate-500">{detail}</p></article>; }
function Fieldset({ title, children }: { title: string; children: React.ReactNode }) { return <fieldset className="space-y-3 rounded-2xl border border-white/[0.08] bg-slate-950/30 p-4"><legend className="px-2 font-semibold text-slate-200">{title}</legend>{children}</fieldset>; }
function TextField({ name, label, list }: { name: string; label: string; list?: string }) { return <label className="block text-xs font-medium text-slate-400">{label}<input name={name} list={list} className="mt-1.5 min-h-11 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 text-sm text-white" /></label>; }
function NumberField({ name, label }: { name: string; label: string }) { return <label className="block text-xs font-medium text-slate-400">{label}<input name={name} inputMode="decimal" className="mt-1.5 min-h-11 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 text-sm text-white" /></label>; }
function SelectField({ name, label, options: items }: { name: string; label: string; options: ReadonlyArray<readonly [string, string]> }) { return <label className="block text-xs font-medium text-slate-400">{label}<select name={name} className="mt-1.5 min-h-11 w-full rounded-xl border border-white/10 bg-slate-950 px-3 text-sm text-white">{items.map(([v, label]) => <option key={`${name}-${v}`} value={v}>{label}</option>)}</select></label>; }
function SubmitButton() { const { pending } = useFormStatus(); return <button disabled={pending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-300 px-5 text-sm font-semibold text-slate-950 disabled:opacity-60"><CheckCircle2 className="size-4" />{pending ? "Przeliczanie…" : "Zapisz i przelicz"}</button>; }
function options(items: ReadonlyArray<{ id: string; label: string }>): Array<readonly [string, string]> { return [["", "Wybierz"], ...items.map((item) => [item.id, item.label] as const)]; }
function status(value: Record<string, unknown> | null | undefined) { return typeof value?.status === "string" ? value.status : "REQUIRES_DATA"; }
function statusLabel(value: string) { return ({ AUTOMATIC: "Automatyczna", PARTIAL: "Częściowa", REQUIRES_DATA: "Wymaga danych", MANUAL: "Manualna", UNAVAILABLE: "Niedostępna", SOURCE_ERROR: "Błąd źródła" } as Record<string, string>)[value] ?? "Niepełne dane"; }
function owasSummary(value: Record<string, unknown> | null) { const summary = rec(value?.summary); return typeof summary?.dominant_category === "number" ? `Dominująca kategoria ${summary.dominant_category}` : "Masa może wymagać uzupełnienia"; }
function riskSummary(value: Record<string, unknown>) { return typeof value.category === "string" ? value.category : "Wymaga danych kontekstowych"; }
function rec(value: unknown): Record<string, unknown> | null { return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null; }
function findDominantOwasFrame(value: Record<string, unknown> | null) { if (!Array.isArray(value?.frames)) return null; for (const raw of value.frames) { const item = rec(raw); if (typeof item?.code === "string" && typeof item.category === "number" && typeof item.timestamp_seconds === "number") return { code: item.code, category: item.category, time: item.timestamp_seconds }; } return null; }
function OwasDetails({ value }: { value: Record<string, unknown> | null }) { const summary = rec(value?.summary); const ratios = rec(summary?.category_ratios); if (!summary) return null; return <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">{[1,2,3,4].map((category) => <div key={category} className="rounded-xl bg-white/[0.035] p-3 text-xs"><span className="text-slate-500">Kategoria {category}</span><strong className="mt-1 block">{typeof ratios?.[String(category)] === "number" ? `${((ratios[String(category)] as number) * 100).toFixed(1)}%` : "—"}</strong></div>)}</div>; }
