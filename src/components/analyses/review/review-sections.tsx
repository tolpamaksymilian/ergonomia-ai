"use client";

import { AlertTriangle, Hand, Info, Move3d, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";

import { METRIC_DEFINITIONS, QUALITY_WARNING_LABELS } from "@/lib/analysis-review/config";
import { formatAngle, formatDuration, formatPercentage, formatRatio, formatTimestamp, UNKNOWN_VALUE } from "@/lib/analysis-review/formatters";
import { QUALITY_GRADE_LABELS, qualityGrade } from "@/lib/analysis-review/quality";
import type { AnalysisReviewModel, HandReview, KeyMomentCategory, ReviewMetric } from "@/lib/analysis-review/schemas";

export function QuickSummary({ model }: { model: AnalysisReviewModel }) {
  const strongest = [...model.keyMoments].filter((moment) => moment.category === "posture" && moment.value !== null).sort((a, b) => b.rank - a.rank)[0];
  const longestHold = Math.max(model.hands.left.longestHoldingSeconds ?? -1, model.hands.right.longestHoldingSeconds ?? -1);
  const riskLabel = riskLevelLabel(model.risk.level);
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1" aria-label="Szybkie podsumowanie">
      <SummaryCard label="Ogólny poziom ryzyka" value={riskLabel} hint={model.risk.profileName ?? "Risk Engine"} />
      <SummaryCard label="Największe odchylenie" value={strongest ? `${strongest.title.replace(/^Największe /, "")}: ${strongest.unit === "deg" ? formatAngle(strongest.value) : formatRatio(strongest.value)}` : UNKNOWN_VALUE} hint="geometryczne, nie ocena ryzyka" />
      <SummaryCard label="Najdłuższy chwyt" value={longestHold >= 0 ? formatDuration(longestHold) : UNKNOWN_VALUE} hint="na podstawie Holding V2" />
      <SummaryCard label="Jakość sylwetki" value={QUALITY_GRADE_LABELS[qualityGrade(model.quality.bodyValidRatio)]} hint={formatPercentage(model.quality.bodyValidRatio)} />
      <SummaryCard label="Ważne momenty" value={String(model.keyMoments.length)} hint="deterministyczny wybór" />
    </section>
  );
}

export function MetricCards({ metrics, onSelect }: { metrics: ReviewMetric[]; onSelect: (metric: ReviewMetric["name"]) => void }) {
  const groups = [...new Set(metrics.map((metric) => metric.group))];
  return (
    <section className="review-panel" aria-labelledby="all-metrics-title">
      <p className="review-eyebrow">14 metryk technicznych</p>
      <h2 id="all-metrics-title" className="mt-2 text-xl font-semibold">Metryki ciała i dłoni</h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">Wartością reprezentatywną jest mediana. Brak danych pozostaje brakiem danych — nie jest zamieniany na zero.</p>
      <div className="mt-6 space-y-6">
        {groups.map((group) => (
          <div key={group}>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{group}</h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {metrics.filter((metric) => metric.group === group).map((metric) => (
                <button key={metric.name} type="button" onClick={() => onSelect(metric.name)} className="min-w-0 rounded-xl border border-border bg-surface-muted p-4 text-left transition hover:border-orange-200 hover:bg-brand-soft">
                  <span className="block text-sm font-semibold text-slate-200">{metric.label}</span>
                  <span className="mt-4 grid grid-cols-3 gap-2 text-xs">
                    <MetricDatum label="Mediana" value={formatMetric(metric, metric.statistics.median)} />
                    <MetricDatum label="Maksimum" value={formatMetric(metric, metric.statistics.maximum)} />
                    <MetricDatum label="Pokrycie" value={formatPercentage(metric.statistics.validRatio)} />
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function HandsSection({ model, onSeek }: { model: AnalysisReviewModel; onSeek: (time: number) => void }) {
  const hasHolding = [model.hands.left, model.hands.right].some((hand) => hand.validObservationSeconds !== null || hand.episodes.length) || model.hands.bimanual.holdingSeconds !== null;
  return (
    <section className="review-panel" aria-labelledby="hands-title">
      <p className="review-eyebrow"><Hand className="size-4" /> Dłonie i chwyt</p>
      <h2 id="hands-title" className="mt-2 text-xl font-semibold">Obserwacja dłoni oraz trzymania przedmiotów</h2>
      {!hasHolding ? <EmptyState text="Brak danych Holding V2 dla tej wersji analizy." /> : (
        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <HandColumn title="Lewa dłoń" hand={model.hands.left} onSeek={onSeek} />
          <HandColumn title="Prawa dłoń" hand={model.hands.right} onSeek={onSeek} />
          <article className="rounded-2xl border border-fuchsia-300/15 bg-fuchsia-300/[0.04] p-5">
            <h3 className="font-semibold text-fuchsia-100">Oburącz</h3>
            <dl className="mt-4 grid grid-cols-2 gap-3"><MetricDatum label="Czas chwytu" value={formatDuration(model.hands.bimanual.holdingSeconds)} /><MetricDatum label="Epizody" value={model.hands.bimanual.episodeCount?.toString() ?? UNKNOWN_VALUE} /></dl>
            {model.hands.bimanual.episodes.length > 0 && <EpisodeList episodes={model.hands.bimanual.episodes} onSeek={onSeek} />}
          </article>
        </div>
      )}
      <p className="mt-4 flex gap-2 text-xs leading-5 text-slate-500"><Info className="mt-0.5 size-4 shrink-0" />System nie estymuje siły ani masy trzymanego przedmiotu.</p>
    </section>
  );
}

export function MovementSection({ model }: { model: AnalysisReviewModel }) {
  const metrics = Object.values(model.metrics).filter((metric) => metric.statistics.rangeOfMotion !== null || metric.statistics.cycleCount !== null || metric.statistics.longestStablePostureSeconds !== null);
  if (!metrics.length) return <section className="review-panel"><h2 className="text-xl font-semibold">Ruch i czas utrzymania postawy</h2><EmptyState text="Brak danych movement V2 dla tej wersji analizy." /></section>;
  return (
    <section className="review-panel" aria-labelledby="movement-title">
      <p className="review-eyebrow"><Move3d className="size-4" /> Ruch i ekspozycja</p>
      <h2 id="movement-title" className="mt-2 text-xl font-semibold">Ruch, powtarzalność i stabilne okresy</h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">Wartości opisują ruch technicznie. Bez progów Risk Profile nie oznaczają „zbyt szybko” ani „zbyt powtarzalnie”.</p>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {metrics.map((metric) => <article key={metric.name} className="rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4"><h3 className="text-sm font-semibold text-slate-200">{metric.shortLabel}</h3><dl className="mt-4 grid grid-cols-2 gap-3"><MetricDatum label="Zakres ruchu" value={formatMetric(metric, metric.statistics.rangeOfMotion)} /><MetricDatum label="Cykle" value={metric.statistics.cycleCount?.toString() ?? UNKNOWN_VALUE} /><MetricDatum label="Prędkość medianowa" value={metric.statistics.medianVelocity !== null ? `${formatMetric(metric, metric.statistics.medianVelocity)}/s` : UNKNOWN_VALUE} /><MetricDatum label="Stabilna postawa" value={formatDuration(metric.statistics.longestStablePostureSeconds)} /></dl></article>)}
      </div>
    </section>
  );
}

export function KeyMomentsSection({ model, onSeek }: { model: AnalysisReviewModel; onSeek: (time: number) => void }) {
  const [filter, setFilter] = useState<KeyMomentCategory | "all">("all");
  const moments = model.keyMoments.filter((moment) => filter === "all" || moment.category === filter);
  return (
    <section className="review-panel" aria-labelledby="moments-title">
      <p className="review-eyebrow"><Sparkles className="size-4" /> Kluczowe momenty</p>
      <div className="flex flex-wrap items-end justify-between gap-4"><div><h2 id="moments-title" className="mt-2 text-xl font-semibold">Najważniejsze fragmenty nagrania</h2><p className="mt-2 text-sm text-slate-400">Ranking jest deterministyczny: uwzględnia odchylenie, czas trwania, jakość i typ zdarzenia.</p></div><div className="flex flex-wrap gap-2">{(["all", "posture", "hands", "holding", "quality"] as const).map((value) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`review-filter ${filter === value ? "review-filter-active" : ""}`}>{categoryLabel(value)}</button>)}</div></div>
      {moments.length ? <div className="mt-6 grid gap-3 md:grid-cols-2">{moments.map((moment) => <article key={moment.id} className="flex min-w-0 gap-4 rounded-xl border border-border bg-surface-muted p-4"><time className="shrink-0 font-mono text-sm font-semibold text-accent-foreground">{formatTimestamp(moment.time)}</time><div className="min-w-0"><h3 className="font-semibold text-foreground">{moment.title}</h3><p className="mt-1 text-sm leading-6 text-muted-foreground">{moment.description}</p><button type="button" onClick={() => onSeek(moment.time)} className="mt-3 text-xs font-semibold text-accent-foreground underline-offset-4 hover:underline">Przejdź do filmu</button></div></article>)}</div> : <EmptyState text="Brak wiarygodnych momentów dla wybranego filtra." />}
    </section>
  );
}

export function QualitySection({ model }: { model: AnalysisReviewModel }) {
  const items = [
    ["Sylwetka", model.quality.bodyValidRatio], ["Lewa dłoń", model.quality.leftHandValidRatio], ["Prawa dłoń", model.quality.rightHandValidRatio],
  ] as const;
  return (
    <section className="review-panel" aria-labelledby="quality-title">
      <p className="review-eyebrow"><ShieldCheck className="size-4" /> Jakość analizy</p>
      <h2 id="quality-title" className="mt-2 text-xl font-semibold">Widoczność i wiarygodność danych</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Jakość określa, jaka część nagrania zawierała wystarczająco wiarygodne dane do analizy. Nie jest to dokładność AI.</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{items.map(([label, value]) => { const grade = qualityGrade(value); return <article key={label} className="rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-lg font-semibold text-slate-100">{QUALITY_GRADE_LABELS[grade]}</p><p className="mt-1 text-xs text-slate-500">Pokrycie: {formatPercentage(value)}</p></article>; })}</div>
      <dl className="mt-4 grid gap-3 sm:grid-cols-3"><MetricDatum label="Poza kadrem" value={formatPercentage(model.quality.outOfFrameRatio)} /><MetricDatum label="Utraty śledzenia" value={model.quality.trackLosses?.toString() ?? UNKNOWN_VALUE} /><MetricDatum label="Ponowne podjęcia" value={model.quality.reacquisitions?.toString() ?? UNKNOWN_VALUE} /></dl>
      {model.quality.warnings.length > 0 && <div className="mt-5 space-y-2">{model.quality.warnings.map((warning) => <p key={warning} className="flex gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] px-4 py-3 text-sm leading-6 text-amber-100/85"><AlertTriangle className="mt-1 size-4 shrink-0" />{QUALITY_WARNING_LABELS[warning] ?? "Analiza zawiera fragmenty o ograniczonej jakości danych."}</p>)}</div>}
    </section>
  );
}

export function RiskSection({ model }: { model: AnalysisReviewModel }) {
  return <section className="review-panel border-primary/20 bg-primary/[0.035]" aria-labelledby="risk-title"><p className="review-eyebrow text-primary"><AlertTriangle className="size-4" /> Ocena ryzyka</p><h2 id="risk-title" className="mt-2 text-xl font-semibold">{riskLevelLabel(model.risk.level)}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">To wynik Risk Engine według profilu „{model.risk.profileName ?? "brak danych"}”{model.risk.profileVersion ? ` v${model.risk.profileVersion}` : ""}. Jest prezentowany oddzielnie od geometrycznych pasm odchylenia.</p>{model.risk.dominantMetrics.length > 0 && <div className="mt-5"><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Najważniejsze czynniki</h3><ul className="mt-3 grid gap-2 sm:grid-cols-2">{model.risk.dominantMetrics.slice(0, 6).map((name) => <li key={name} className="rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">{METRIC_DEFINITIONS[name as keyof typeof METRIC_DEFINITIONS]?.label ?? name}</li>)}</ul></div>}</section>;
}

export function TechnicalDetails({ model }: { model: AnalysisReviewModel }) {
  return <details className="review-panel group"><summary className="cursor-pointer list-none font-semibold text-foreground focus-visible:outline-2 focus-visible:outline-ring">Szczegóły techniczne</summary><dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><MetricDatum label="Worker" value={model.workerVersion ?? UNKNOWN_VALUE} /><MetricDatum label="Pose" value={model.poseVersion ?? UNKNOWN_VALUE} /><MetricDatum label="Schema pozy" value={model.poseSchemaVersion ?? UNKNOWN_VALUE} /><MetricDatum label="Metryki" value={model.metricsVersion ?? UNKNOWN_VALUE} /><MetricDatum label="Przetworzone klatki" value={model.processedFrames?.toLocaleString("pl-PL") ?? UNKNOWN_VALUE} /><MetricDatum label="Pose JSON" value={model.availableSources.pose ? "Dostępny" : "Niedostępny"} /><MetricDatum label="Risk JSON" value={model.availableSources.risk ? "Dostępny" : "Niedostępny"} /><MetricDatum label="Report JSON" value={model.availableSources.report ? "Dostępny" : "Niedostępny"} /></dl></details>;
}

function HandColumn({ title, hand, onSeek }: { title: string; hand: HandReview; onSeek: (time: number) => void }) {
  return <article className="rounded-2xl border border-border bg-card p-5"><h3 className="font-semibold text-primary">{title}</h3><dl className="mt-4 grid grid-cols-2 gap-3"><MetricDatum label="Obserwacja" value={formatDuration(hand.validObservationSeconds)} /><MetricDatum label="Czas chwytu" value={formatDuration(hand.holdingSeconds)} /><MetricDatum label="Udział chwytu" value={formatPercentage(hand.holdingRatio)} /><MetricDatum label="Najdłuższy chwyt" value={formatDuration(hand.longestHoldingSeconds)} /><MetricDatum label="Statyczny chwyt" value={formatDuration(hand.staticHoldingSeconds)} /><MetricDatum label="Cykle chwytu" value={hand.graspReleaseCycles?.toString() ?? UNKNOWN_VALUE} /><MetricDatum label="Cykle pinch" value={hand.pinchCycles?.toString() ?? UNKNOWN_VALUE} /><MetricDatum label="Jakość dłoni" value={formatPercentage(hand.validRatio)} /></dl>{hand.episodes.length > 0 && <EpisodeList episodes={hand.episodes} onSeek={onSeek} />}</article>;
}

function EpisodeList({ episodes, onSeek }: { episodes: HandReview["episodes"]; onSeek: (time: number) => void }) {
  return <div className="mt-5 border-t border-border pt-4"><p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Epizody</p><div className="mt-2 max-h-44 space-y-1 overflow-y-auto pr-1">{episodes.map((episode) => <button key={episode.id} type="button" onClick={() => onSeek(episode.start)} className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-2 text-left text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"><span>{formatTimestamp(episode.start)}–{formatTimestamp(episode.end)}<small className="block text-muted-foreground">{episode.objectClass ? `Obiekt: ${translateObject(episode.objectClass)}` : "Nieokreślony przedmiot"}</small></span><span className="shrink-0 font-semibold text-foreground">{formatDuration(episode.duration)}</span></button>)}</div></div>;
}

function SummaryCard({ label, value, hint }: { label: string; value: string; hint: string }) { return <article className="rounded-2xl border border-white/[0.08] bg-white/[0.035] p-4"><p className="text-[9px] uppercase tracking-[0.14em] text-slate-600">{label}</p><p className="mt-2 truncate text-base font-semibold text-slate-100" title={value}>{value}</p><p className="mt-1 truncate text-[10px] text-slate-600" title={hint}>{hint}</p></article>; }
function MetricDatum({ label, value }: { label: string; value: string }) { return <div><dt className="text-[9px] uppercase tracking-wider text-slate-600">{label}</dt><dd className="mt-1 text-xs font-semibold text-slate-300">{value}</dd></div>; }
function EmptyState({ text }: { text: string }) { return <p className="mt-5 rounded-xl border border-dashed border-white/10 px-5 py-8 text-center text-sm text-slate-500">{text}</p>; }
function formatMetric(metric: ReviewMetric, value: number | null) { return metric.unit === "deg" ? formatAngle(value) : formatRatio(value); }
function riskLevelLabel(level: AnalysisReviewModel["risk"]["level"]) { return ({ low: "Niskie", moderate: "Umiarkowane", high: "Wysokie", critical: "Krytyczne", insufficient_data: "Niewystarczające dane" } as const)[level ?? "insufficient_data"]; }
function categoryLabel(value: KeyMomentCategory | "all") { return ({ all: "Wszystkie", posture: "Postawa", hands: "Dłonie", holding: "Chwyt", quality: "Jakość" } as const)[value]; }
function translateObject(value: string) { return ({ bottle: "butelka", cup: "kubek", box: "pudełko", chair: "krzesło", laptop: "laptop", cell_phone: "telefon" } as Record<string, string>)[value] ?? value; }
