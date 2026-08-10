import { Activity, Clock3, Factory, FileWarning, Hand, ScanLine, ShieldCheck } from "lucide-react";
import Image from "next/image";

import { manualInputLabel } from "@/config/manual-input-labels";
import { METRIC_DEFINITIONS } from "@/lib/analysis-review/config";
import { formatAngle, formatDuration, formatPercentage, formatRatio, formatTimestamp, UNKNOWN_VALUE } from "@/lib/analysis-review/formatters";
import type { AnalysisReport, ReportMetricSummary, RiskLevel } from "@/types/analysis";

const levelLabels: Record<RiskLevel, string> = {
  low: "Niskie",
  moderate: "Umiarkowane",
  high: "Wysokie",
  critical: "Krytyczne",
  insufficient_data: "Niewystarczające dane",
};

const limitationLabels: Record<string, string> = {
  analysis_based_on_2d_video: "Analiza bazuje głównie na obrazie 2D.",
  occluded_body_parts_may_be_missing: "Zasłonięte części ciała mogą nie dostarczać danych.",
  result_is_technical_screening: "Wynik jest technicznym screeningiem, a nie diagnozą.",
  specialist_review_required: "Wynik wymaga interpretacji przez kompetentnego specjalistę.",
  development_profile_used: "Użyty profil klasyfikacji ma status rozwojowy.",
  production_profile_not_used: "Nie użyto zatwierdzonego profilu produkcyjnego.",
  result_depends_on_recording_quality: "Wynik zależy od jakości nagrania, kadru i oświetlenia.",
  external_load_not_measured: "Nagranie nie dostarcza pełnej informacji o obciążeniu zewnętrznym.",
  rula_not_calculated: "Raport nie zawiera oceny RULA.",
  reba_not_calculated: "Raport nie zawiera oceny REBA.",
  frame_timestamps_replaced_with_fps_fallback: "Czas ekspozycji wykorzystał jawny fallback FPS.",
  exposure_timing_unavailable: "Dla części ekspozycji nie było wiarygodnej osi czasu.",
  low_hand_visibility: "Widoczność dłoni była ograniczona.",
  body_occlusion: "Części sylwetki były okresowo zasłonięte.",
  high_motion_blur: "Nagranie zawiera fragmenty rozmazane ruchem.",
  holding_uncertain: "Klasyfikacja chwytu zawiera okresy ograniczonej jakości.",
  partial_source_video_processing: "Przetworzono tylko część źródłowego nagrania.",
  limited_left_hand_visibility: "Widoczność lewej dłoni była ograniczona.",
  limited_right_hand_visibility: "Widoczność prawej dłoni była ograniczona.",
  person_partially_out_of_frame: "Pracownik okresowo znajdował się częściowo poza kadrem.",
  left_holding_object_unclassified: "Nie udało się wiarygodnie sklasyfikować obiektu trzymanego lewą dłonią.",
  right_holding_object_unclassified: "Nie udało się wiarygodnie sklasyfikować obiektu trzymanego prawą dłonią.",
};

export function ReportBodyAreas({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Obszary ciała" icon={ScanLine}>
    {report.body_areas.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{report.body_areas.map((area) => <article key={area.area_id} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white"><div className="flex items-start justify-between gap-3"><h3 className="font-semibold text-slate-100 print:text-black">{area.label}</h3><span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-semibold uppercase text-slate-300 print:border-slate-400 print:text-black">{levelLabels[area.level]}</span></div>{area.coverage !== undefined && <p className="mt-3 text-xs text-slate-500 print:text-slate-700">Pokrycie danych: {formatPercentage(area.coverage)}</p>}</article>)}</div> : <Empty text="Brak obszarów możliwych do podsumowania." />}
  </ReportSection>;
}

export function ReportMetrics({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Postawa ciała i metryki" icon={Activity}>
    <p className="mb-5 text-sm leading-6 text-slate-500 print:text-slate-700">Wartości techniczne są prezentowane oddzielnie od klasyfikacji Risk Engine.</p>
    {report.metric_summary.length ? <div className="overflow-x-auto"><table className="w-full min-w-[660px] text-left text-sm"><thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="pb-3 pr-4">Metryka</th><th className="pb-3 pr-4">Poziom Risk Engine</th><th className="pb-3 pr-4">Mediana</th><th className="pb-3 pr-4">Maksimum</th><th className="pb-3">Pokrycie</th></tr></thead><tbody className="divide-y divide-white/[0.07] print:divide-slate-200">{report.metric_summary.map((metric) => { const unavailable = metric.display_status === "insufficient_data" || metric.level === "insufficient_data"; return <tr key={metric.metric_name} className={unavailable ? "opacity-65" : ""}><td className="py-3 pr-4 font-medium text-slate-200 print:text-black">{metric.label}{unavailable && <span className="mt-1 block text-[10px] font-normal text-amber-200">Za mało wiarygodnych danych</span>}</td><td className="py-3 pr-4 text-slate-400 print:text-slate-700">{levelLabels[metric.level]}</td><td className="py-3 pr-4 text-slate-400 print:text-slate-700">{unavailable ? UNKNOWN_VALUE : formatMetric(metric, metric.statistics?.median)}</td><td className="py-3 pr-4 text-slate-400 print:text-slate-700">{unavailable ? UNKNOWN_VALUE : formatMetric(metric, metric.statistics?.maximum)}</td><td className="py-3 text-slate-400 print:text-slate-700">{formatPercentage(metric.valid_ratio)}</td></tr>; })}</tbody></table></div> : <Empty text="Brak metryk możliwych do przedstawienia." />}
  </ReportSection>;
}

export function ReportHands({ report }: { report: AnalysisReport }) {
  const activity = report.holding_activity ?? report.hand_activity;
  if (!activity) return <ReportSection title="Dłonie i chwyt" icon={Hand}><Empty text="Brak danych Holding V2 dla tej wersji analizy." /></ReportSection>;
  return <ReportSection title="Dłonie i chwyt" icon={Hand}>
    <div className="grid gap-4 md:grid-cols-3">
      {(["left", "right"] as const).map((side) => { const hand = activity[side]; return <article key={side} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-5 print:border-slate-300 print:bg-white"><h3 className="font-semibold text-slate-100 print:text-black">{side === "left" ? "Lewa dłoń" : "Prawa dłoń"}</h3>{hand ? <dl className="mt-4 grid grid-cols-2 gap-3"><Datum label="Obserwacja" value={formatDuration(hand.valid_observation_seconds)} /><Datum label="Czas chwytu" value={formatDuration(hand.likely_holding_seconds)} /><Datum label="Udział chwytu" value={formatPercentage(hand.holding_ratio)} /><Datum label="Najdłuższy chwyt" value={formatDuration(hand.longest_holding_seconds)} /><Datum label="Chwyt statyczny" value={formatDuration(hand.static_holding_seconds)} /><Datum label="Epizody" value={hand.holding_episode_count?.toString() ?? UNKNOWN_VALUE} /></dl> : <Empty text="Brak danych." />}</article>; })}
      <article className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-5 print:border-slate-300 print:bg-white"><h3 className="font-semibold text-slate-100 print:text-black">Oburącz</h3><dl className="mt-4 grid grid-cols-2 gap-3"><Datum label="Czas chwytu" value={formatDuration(activity.bimanual?.likely_holding_seconds)} /><Datum label="Epizody" value={activity.bimanual?.episode_count?.toString() ?? UNKNOWN_VALUE} /></dl></article>
    </div>
    <p className="mt-4 text-xs text-slate-500 print:text-slate-700">System nie estymuje siły ani masy przedmiotu.</p>
  </ReportSection>;
}

export function ReportMovement({ report }: { report: AnalysisReport }) {
  const findingMetrics = new Set(report.priority_findings?.flatMap((finding) => finding.metric_names) ?? []);
  const movement = report.movement_features ? Object.entries(report.movement_features).filter(([name, item]) =>
    findingMetrics.has(name) || (item.repetition_count ?? item.cycle_count ?? 0) > 0 || (item.longest_stable_posture_seconds ?? 0) >= 1,
  ).slice(0, 6) : [];
  const posture = report.posture_duration ? Object.entries(report.posture_duration).filter(([, value]) => typeof value === "number" && value >= 0.1).slice(0, 6) : [];
  return <ReportSection title="Czas ekspozycji, ruch i powtarzalność" icon={Clock3}>
    {!movement.length && !posture.length ? <Empty text="Brak danych movement V2 dla tej wersji analizy." /> : <>
      {posture.length > 0 && <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{posture.map(([name, value]) => <Datum key={name} label={postureLabel(name)} value={formatDuration(value as number)} card />)}</div>}
      {movement.length > 0 && <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{movement.map(([name, item]) => <article key={name} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white"><h3 className="text-sm font-semibold text-slate-100 print:text-black">{METRIC_DEFINITIONS[name as keyof typeof METRIC_DEFINITIONS]?.label ?? "Metryka techniczna"}</h3><dl className="mt-4 grid grid-cols-2 gap-3"><Datum label="Zakres ruchu" value={name.endsWith("_deg") ? formatAngle(item.range_of_motion ?? item.movement_range) : formatRatio(item.range_of_motion ?? item.movement_range)} /><Datum label="Cykle" value={item.cycle_count?.toString() ?? UNKNOWN_VALUE} /><Datum label="Prędkość medianowa" value={item.median_absolute_velocity !== undefined ? `${item.median_absolute_velocity.toFixed(1)} ${name.endsWith("_deg") ? "°/s" : "jedn./s"}` : UNKNOWN_VALUE} /><Datum label="Stabilna postawa" value={formatDuration(item.longest_stable_posture_seconds)} /></dl></article>)}</div>}
    </>}
  </ReportSection>;
}

export function ReportKeyMoments({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Kluczowe momenty" icon={Clock3}>
    {report.key_moments.length ? <div className="grid gap-3 sm:grid-cols-2">{report.key_moments.map((moment, index) => <article key={`${moment.metric_name}-${moment.timestamp_seconds ?? index}`} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white"><div className="flex items-start justify-between gap-3"><time className="font-mono text-sm font-semibold text-cyan-300 print:text-black">{formatTimestamp(moment.timestamp_seconds)}</time><span className="text-[10px] font-semibold uppercase text-slate-500">{levelLabels[moment.level]}</span></div><h3 className="mt-3 font-semibold text-slate-100 print:text-black">{moment.metric_label}</h3><p className="mt-2 text-sm leading-6 text-slate-400 print:text-slate-700">{moment.reason}</p>{moment.value !== undefined && <p className="mt-2 text-sm font-semibold text-slate-300 print:text-black">{moment.metric_name.endsWith("_deg") ? formatAngle(moment.value) : formatRatio(moment.value)}</p>}</article>)}</div> : <Empty text="Raport nie zawiera kluczowych momentów." />}
  </ReportSection>;
}

export function ReportQuality({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Jakość analizy" icon={ShieldCheck}>
    <p className="mb-5 text-sm leading-6 text-slate-500 print:text-slate-700">Jakość oznacza pokrycie nagrania wiarygodnymi danymi, nie dokładność systemu.</p>
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Datum label="Przetworzona część filmu" value={formatPercentage(report.data_quality.processing_coverage_ratio)} card /><Datum label="Obecność sylwetki" value={formatPercentage(report.data_quality.pose_presence_ratio)} card /><Datum label="Pokrycie poprawnymi metrykami" value={formatPercentage(report.data_quality.valid_metric_ratio)} card /><Datum label="Odrzucone wartości" value={report.data_quality.invalid_metric_values?.toString() ?? UNKNOWN_VALUE} card /></dl>
    {report.data_quality.region_coverage && <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(report.data_quality.region_coverage).map(([region, coverage]) => <Datum key={region} label={regionLabel(region)} value={formatPercentage(coverage)} card />)}</div>}
  </ReportSection>;
}

export function ReportAssessment({ report }: { report: AnalysisReport }) {
  const assessment = report.ergonomic_assessment;
  return <ReportSection title="Metody RULA / REBA" icon={ScanLine} className="report-break-before">
    <p className="mb-5 text-sm leading-6 text-slate-500 print:text-slate-700">Metody przesiewowe są prezentowane oddzielnie od własnego Risk Engine. Brakujące parametry nie są zamieniane na zero.</p>
    {!assessment || assessment.status !== "available" ? <Empty text="Assessment Engine nie był dostępny dla tej analizy." /> : <div className="grid gap-4 md:grid-cols-2">{([assessment.rula, assessment.reba] as const).map((method, index) => {
      const name = index === 0 ? "RULA" : "REBA";
      const representative = method?.representative;
      const score = representative?.final_score ?? null;
      const range = representative?.score_range;
      const keyframe = assessment.keyframes?.find((item) => item.method === name && item.signed_url);
      return <article key={name} className="report-card rounded-2xl border border-sky-300/15 bg-sky-300/[0.035] p-5 print:border-slate-300 print:bg-white">{keyframe?.signed_url && <Image src={keyframe.signed_url} alt={`Pozycja reprezentatywna ${name}`} width={960} height={540} unoptimized className="mb-4 aspect-video w-full rounded-xl border border-white/10 object-cover print:border-slate-300" />}<h3 className="text-lg font-semibold text-slate-100 print:text-black">{name}</h3><p className="mt-2 text-sm text-slate-400 print:text-slate-700">{methodStatus(method?.status)}</p><dl className="mt-4 grid grid-cols-2 gap-3"><Datum label={score !== null ? "Wynik" : "Możliwy zakres"} value={score !== null ? String(score) : range ? `${range.min}–${range.max}` : UNKNOWN_VALUE} /><Datum label="Pozycja" value={formatTimestamp(representative?.timestamp_seconds)} /><Datum label="Strona" value={representative?.side === "left" ? "Lewa" : representative?.side === "right" ? "Prawa" : UNKNOWN_VALUE} /><Datum label="Pokrycie dowodami" value={formatPercentage(representative?.evidence_coverage_ratio)} /></dl>{representative?.missing_inputs?.length ? <div className="mt-4"><p className="text-[9px] uppercase tracking-wider text-slate-500">Brakujące informacje</p><ul className="mt-2 space-y-1 text-xs text-slate-500 print:text-slate-700">{representative.missing_inputs.slice(0, 6).map((item) => <li key={item}>— {manualInputLabel(item)}</li>)}</ul></div> : null}</article>;
    })}</div>}
  </ReportSection>;
}

export function ReportCompanyMethods({ report }: { report: AnalysisReport }) {
  const methods = report.company_methods;
  if (!methods || methods.status !== "available") return <ReportSection title="Metody zakładowe" icon={Factory}><Empty text="Metody zakładowe nie były dostępne dla tej analizy." /></ReportSection>;
  const items = [["OWAS", methods.owas], ["EJMS", methods.ejms]] as const;
  const hasAdditionalMethods = Boolean(
    (asRecord(methods.risk_score)?.status && asRecord(methods.risk_score)?.status !== "REQUIRES_DATA")
    || (Array.isArray(methods.measurable_factors) && methods.measurable_factors.length)
    || (asRecord(methods.chemical)?.status && asRecord(methods.chemical)?.status !== "REQUIRES_DATA"),
  );
  return <ReportSection title="OWAS i EJMS" icon={Factory} className="report-break-before">
    <p className="mb-5 text-sm leading-6 text-slate-500 print:text-slate-700">OWAS i EJMS uzupełniają Risk Engine, RULA oraz REBA; nie są łączone w jeden wynik 0–100.</p>
    <div className="grid gap-3 sm:grid-cols-2">{items.map(([name, raw]) => { const item = asRecord(raw); const status = typeof item?.status === "string" ? item.status : "REQUIRES_DATA"; return <article key={name} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white"><h3 className="font-semibold text-slate-100 print:text-black">{name}</h3><p className="mt-2 text-xs font-semibold uppercase text-cyan-200 print:text-black">{companyStatus(status)}</p>{name === "OWAS" && <OwasReportSummary value={item} />}{name === "EJMS" && <EjmsReportSummary value={item} />}</article>; })}</div>
    {!hasAdditionalMethods && <p className="mt-4 rounded-xl border border-white/[0.07] bg-white/[0.025] p-4 text-sm text-slate-500">Dodatkowe metody kontekstowe wymagają danych wejściowych i nie są rozwijane w głównej części raportu.</p>}
  </ReportSection>;
}

function OwasReportSummary({ value }: { value: Record<string, unknown> | null }) {
  const summary = asRecord(value?.summary);
  const postures = asRecord(summary?.posture_duration_seconds);
  const dominantPosture = postures ? Object.entries(postures).filter((entry): entry is [string, number] => typeof entry[1] === "number").sort((a, b) => b[1] - a[1])[0]?.[0] : undefined;
  const postureDuration = typeof summary?.posture_classified_duration_seconds === "number" ? summary.posture_classified_duration_seconds : undefined;
  const postureCoverage = typeof summary?.posture_coverage_ratio === "number" ? summary.posture_coverage_ratio : undefined;
  const category = typeof summary?.dominant_category === "number" ? String(summary.dominant_category) : "Wymaga masy";
  return <dl className="mt-3 space-y-1 text-xs text-slate-500 print:text-slate-700"><div>Postura: <strong>{dominantPosture ? `${dominantPosture}?` : UNKNOWN_VALUE}</strong></div><div>Pełna kategoria: <strong>{category}</strong></div><div>Rozpoznana postura: <strong>{formatDuration(postureDuration)}{postureCoverage !== undefined ? ` / ${formatPercentage(postureCoverage)}` : ""}</strong></div></dl>;
}
function EjmsReportSummary({ value }: { value: Record<string, unknown> | null }) { const section = asRecord(value?.section_i); const known = typeof section?.known_score === "number" ? section.known_score : null; const minimum = typeof section?.possible_score_min === "number" ? section.possible_score_min : null; const maximum = typeof section?.possible_score_max === "number" ? section.possible_score_max : null; return <p className="mt-3 text-xs text-slate-500 print:text-slate-700">Wynik z rozpoznanych danych: <strong>{known !== null ? `${known} pkt` : UNKNOWN_VALUE}</strong>. Możliwy zakres: <strong>{minimum !== null && maximum !== null ? `${minimum}–${maximum}` : UNKNOWN_VALUE}</strong>. Ranking globalny pozostaje wyłączony z powodu konfliktu źródła.</p>; }
function asRecord(value: unknown): Record<string, unknown> | null { return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null; }
function companyStatus(value: string) { return ({ AUTOMATIC: "Automatyczna", PARTIAL: "Częściowa", REQUIRES_DATA: "Wymaga danych", MANUAL: "Manualna", UNAVAILABLE: "Niedostępna", SOURCE_ERROR: "Błąd źródła" } as Record<string, string>)[value] ?? "Niepełne dane"; }

export function ReportLimitations({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Ograniczenia" icon={FileWarning} className="report-break-before"><ul className="space-y-2">{report.limitations.map((item) => <li key={item} className="flex gap-3 text-sm leading-6 text-slate-400 print:text-slate-700"><span aria-hidden="true">—</span>{limitationLabels[item] ?? "Dodatkowe ograniczenie jakości danych."}</li>)}</ul><p className="mt-6 border-t border-white/10 pt-5 text-sm font-medium text-slate-300 print:border-slate-300 print:text-black">Wynik ma charakter wspierający i nie zastępuje oceny specjalisty.</p></ReportSection>;
}

function ReportSection({ title, icon: Icon, className = "", children }: { title: string; icon: typeof Activity; className?: string; children: React.ReactNode }) { return <section className={`report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white ${className}`}><h2 className="mb-5 flex items-center gap-2 text-xl font-semibold text-white print:text-black"><Icon className="size-5 text-cyan-300 print:text-black" aria-hidden="true" />{title}</h2>{children}</section>; }
function Datum({ label, value, card = false }: { label: string; value: string; card?: boolean }) { return <div className={card ? "report-card rounded-xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white" : ""}><dt className="text-[9px] uppercase tracking-wider text-slate-500">{label}</dt><dd className="mt-1 text-sm font-semibold text-slate-200 print:text-black">{value}</dd></div>; }
function Empty({ text }: { text: string }) { return <p className="rounded-xl border border-dashed border-white/10 px-5 py-7 text-center text-sm text-slate-500 print:border-slate-300">{text}</p>; }
function formatMetric(metric: ReportMetricSummary, value: number | undefined) { return metric.unit === "deg" ? formatAngle(value) : formatRatio(value); }
function postureLabel(value: string) { return ({ trunk_posture_hold: "Tułów", neck_posture_hold: "Szyja", left_arm_elevation_hold: "Lewe ramię", right_arm_elevation_hold: "Prawe ramię", left_wrist_posture_hold: "Lewy nadgarstek", right_wrist_posture_hold: "Prawy nadgarstek" } as Record<string, string>)[value] ?? "Inny obszar postawy"; }
function regionLabel(value: string) { return ({ body: "Tułów", neck: "Szyja", left_arm: "Lewa kończyna górna", right_arm: "Prawa kończyna górna", legs: "Nogi", left_hand: "Lewa dłoń", right_hand: "Prawa dłoń" } as Record<string, string>)[value] ?? "Inny obszar"; }
function methodStatus(value: string | undefined) { return value === "COMPLETE" ? "Wynik kompletny" : value === "PARTIAL" ? "Ocena częściowa — zakres wynika z brakujących danych" : "Niewystarczające dane"; }
