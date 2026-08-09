import { Activity, Clock3, FileWarning, Hand, ScanLine, ShieldCheck } from "lucide-react";

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
};

export function ReportBodyAreas({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Obszary ciała" icon={ScanLine}>
    {report.body_areas.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{report.body_areas.map((area) => <article key={area.area_id} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white"><div className="flex items-start justify-between gap-3"><h3 className="font-semibold text-slate-100 print:text-black">{area.label}</h3><span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-semibold uppercase text-slate-300 print:border-slate-400 print:text-black">{levelLabels[area.level]}</span></div>{area.coverage !== undefined && <p className="mt-3 text-xs text-slate-500 print:text-slate-700">Pokrycie danych: {formatPercentage(area.coverage)}</p>}</article>)}</div> : <Empty text="Brak obszarów możliwych do podsumowania." />}
  </ReportSection>;
}

export function ReportMetrics({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Postawa ciała i metryki" icon={Activity}>
    <p className="mb-5 text-sm leading-6 text-slate-500 print:text-slate-700">Wartości techniczne są prezentowane oddzielnie od klasyfikacji Risk Engine.</p>
    {report.metric_summary.length ? <div className="overflow-x-auto"><table className="w-full min-w-[660px] text-left text-sm"><thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="pb-3 pr-4">Metryka</th><th className="pb-3 pr-4">Poziom Risk Engine</th><th className="pb-3 pr-4">Mediana</th><th className="pb-3 pr-4">Maksimum</th><th className="pb-3">Pokrycie</th></tr></thead><tbody className="divide-y divide-white/[0.07] print:divide-slate-200">{report.metric_summary.map((metric) => <tr key={metric.metric_name}><td className="py-3 pr-4 font-medium text-slate-200 print:text-black">{metric.label}</td><td className="py-3 pr-4 text-slate-400 print:text-slate-700">{levelLabels[metric.level]}</td><td className="py-3 pr-4 text-slate-400 print:text-slate-700">{formatMetric(metric, metric.statistics?.median)}</td><td className="py-3 pr-4 text-slate-400 print:text-slate-700">{formatMetric(metric, metric.statistics?.maximum)}</td><td className="py-3 text-slate-400 print:text-slate-700">{formatPercentage(metric.valid_ratio)}</td></tr>)}</tbody></table></div> : <Empty text="Brak metryk możliwych do przedstawienia." />}
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
  const movement = report.movement_features ? Object.entries(report.movement_features) : [];
  const posture = report.posture_duration ? Object.entries(report.posture_duration).filter(([, value]) => typeof value === "number") : [];
  return <ReportSection title="Czas ekspozycji, ruch i powtarzalność" icon={Clock3}>
    {!movement.length && !posture.length ? <Empty text="Brak danych movement V2 dla tej wersji analizy." /> : <>
      {posture.length > 0 && <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{posture.map(([name, value]) => <Datum key={name} label={postureLabel(name)} value={formatDuration(value as number)} card />)}</div>}
      {movement.length > 0 && <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{movement.map(([name, item]) => <article key={name} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white"><h3 className="text-sm font-semibold text-slate-100 print:text-black">{METRIC_DEFINITIONS[name as keyof typeof METRIC_DEFINITIONS]?.label ?? name}</h3><dl className="mt-4 grid grid-cols-2 gap-3"><Datum label="Zakres ruchu" value={name.endsWith("_deg") ? formatAngle(item.range_of_motion ?? item.movement_range) : formatRatio(item.range_of_motion ?? item.movement_range)} /><Datum label="Cykle" value={item.cycle_count?.toString() ?? UNKNOWN_VALUE} /><Datum label="Prędkość medianowa" value={item.median_absolute_velocity !== undefined ? `${item.median_absolute_velocity.toFixed(1)}/s` : UNKNOWN_VALUE} /><Datum label="Stabilna postawa" value={formatDuration(item.longest_stable_posture_seconds)} /></dl></article>)}</div>}
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
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Datum label="Poprawne metryki" value={formatPercentage(report.data_quality.valid_metric_ratio)} card /><Datum label="Obecność pozy" value={formatPercentage(report.data_quality.pose_presence_ratio)} card /><Datum label="Przetworzone klatki" value={report.data_quality.pose_processed_frames?.toString() ?? UNKNOWN_VALUE} card /><Datum label="Odrzucone wartości" value={report.data_quality.invalid_metric_values?.toString() ?? UNKNOWN_VALUE} card /></dl>
  </ReportSection>;
}

export function ReportLimitations({ report }: { report: AnalysisReport }) {
  return <ReportSection title="Ograniczenia" icon={FileWarning} className="report-break-before"><ul className="space-y-2">{report.limitations.map((item) => <li key={item} className="flex gap-3 text-sm leading-6 text-slate-400 print:text-slate-700"><span aria-hidden="true">—</span>{limitationLabels[item] ?? humanize(item)}</li>)}</ul><p className="mt-6 border-t border-white/10 pt-5 text-sm font-medium text-slate-300 print:border-slate-300 print:text-black">Wynik ma charakter wspierający i nie zastępuje oceny specjalisty.</p></ReportSection>;
}

function ReportSection({ title, icon: Icon, className = "", children }: { title: string; icon: typeof Activity; className?: string; children: React.ReactNode }) { return <section className={`report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white ${className}`}><h2 className="mb-5 flex items-center gap-2 text-xl font-semibold text-white print:text-black"><Icon className="size-5 text-cyan-300 print:text-black" aria-hidden="true" />{title}</h2>{children}</section>; }
function Datum({ label, value, card = false }: { label: string; value: string; card?: boolean }) { return <div className={card ? "report-card rounded-xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white" : ""}><dt className="text-[9px] uppercase tracking-wider text-slate-500">{label}</dt><dd className="mt-1 text-sm font-semibold text-slate-200 print:text-black">{value}</dd></div>; }
function Empty({ text }: { text: string }) { return <p className="rounded-xl border border-dashed border-white/10 px-5 py-7 text-center text-sm text-slate-500 print:border-slate-300">{text}</p>; }
function formatMetric(metric: ReportMetricSummary, value: number | undefined) { return metric.unit === "deg" ? formatAngle(value) : formatRatio(value); }
function humanize(value: string) { return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()); }
function postureLabel(value: string) { return ({ trunk_posture_hold: "Tułów", neck_posture_hold: "Szyja", left_arm_elevation_hold: "Lewe ramię", right_arm_elevation_hold: "Prawe ramię", left_wrist_posture_hold: "Lewy nadgarstek", right_wrist_posture_hold: "Prawy nadgarstek" } as Record<string, string>)[value] ?? value; }
