"use client";

import { Activity, ChevronDown } from "lucide-react";
import { useMemo } from "react";

import { DEVIATION_LABELS, METRIC_DEFINITIONS, METRIC_NAMES } from "@/lib/analysis-review/config";
import { formatAngle, formatDuration, formatRatio, formatTimestamp, formatPercentage } from "@/lib/analysis-review/formatters";
import type { ReviewMetric, ReviewMetricName } from "@/lib/analysis-review/schemas";

type MetricExplorerProps = {
  metrics: Record<ReviewMetricName, ReviewMetric>;
  selected: ReviewMetricName;
  currentTime: number;
  duration: number;
  onSelect: (metric: ReviewMetricName) => void;
  onSeek: (time: number) => void;
};

export function MetricExplorer({ metrics, selected, currentTime, duration, onSelect, onSeek }: MetricExplorerProps) {
  const metric = metrics[selected];
  const chart = useMemo(() => buildChart(metric, duration), [metric, duration]);
  const groups = useMemo(() => [...new Set(METRIC_NAMES.map((name) => METRIC_DEFINITIONS[name].group))], []);
  const valueFormatter = metric.unit === "deg" ? formatAngle : formatRatio;

  function seekFromChart(event: React.MouseEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(1, bounds.width)));
    onSeek(ratio * chart.duration);
  }

  return (
    <section className="review-panel min-w-0" aria-labelledby="metric-explorer-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="review-eyebrow"><Activity className="size-4" /> Metric Explorer</p>
          <h2 id="metric-explorer-title" className="mt-2 text-xl font-semibold">{metric.label}</h2>
          <p className="mt-2 text-sm text-slate-400">{metric.unit === "deg" ? "Kąt [°]" : "Znormalizowany wskaźnik"} w czasie. Przerwy oznaczają nieważne lub brakujące dane.</p>
        </div>
        <label className="relative">
          <span className="sr-only">Wybierz metrykę</span>
          <select value={selected} onChange={(event) => onSelect(event.target.value as ReviewMetricName)} className="appearance-none rounded-xl border border-white/10 bg-slate-900 py-2.5 pl-3 pr-9 text-sm text-white focus-visible:outline-2 focus-visible:outline-cyan-200">
            {groups.map((group) => (
              <optgroup key={group} label={group}>
                {METRIC_NAMES.filter((name) => METRIC_DEFINITIONS[name].group === group).map((name) => <option key={name} value={name}>{METRIC_DEFINITIONS[name].label}</option>)}
              </optgroup>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-3 size-4 text-slate-500" />
        </label>
      </div>

      {chart.paths.length ? (
        <div className="mt-6 min-w-0 overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-950/50 p-3 sm:p-4">
          <svg
            viewBox="0 0 900 300"
            preserveAspectRatio="none"
            className="h-64 w-full touch-manipulation focus-visible:outline-2 focus-visible:outline-cyan-200"
            role="slider"
            tabIndex={0}
            aria-label={`Wykres metryki ${metric.label}; strzałki przesuwają film o sekundę`}
            aria-valuemin={0}
            aria-valuemax={chart.duration}
            aria-valuenow={Math.min(chart.duration, currentTime)}
            onClick={seekFromChart}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight") onSeek(Math.min(chart.duration, currentTime + 1));
              if (event.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 1));
            }}
          >
            <defs>
              <linearGradient id="chart-grid" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#22d3ee" stopOpacity="0.08"/><stop offset="1" stopColor="#22d3ee" stopOpacity="0"/></linearGradient>
            </defs>
            <rect x="0" y="0" width="900" height="300" fill="url(#chart-grid)" />
            {[0, 75, 150, 225, 300].map((y) => <line key={y} x1="0" y1={y} x2="900" y2={y} stroke="rgba(148,163,184,.12)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
            {chart.paths.map((path, index) => <path key={index} d={path} fill="none" stroke="#67e8f9" strokeWidth="2.25" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />)}
            <line x1={Math.min(900, currentTime / chart.duration * 900)} x2={Math.min(900, currentTime / chart.duration * 900)} y1="0" y2="300" stroke="#f8fafc" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="mt-2 flex justify-between text-[10px] tabular-nums text-slate-600"><span>00:00</span><span>{formatTimestamp(chart.duration / 2)}</span><span>{formatTimestamp(chart.duration)}</span></div>
          <p className="sr-only">Zakres wykresu: {valueFormatter(chart.minimum)} do {valueFormatter(chart.maximum)}. Poprawne dane: {formatPercentage(metric.statistics.validRatio)}.</p>
        </div>
      ) : <div className="mt-6 rounded-2xl border border-dashed border-white/10 px-5 py-12 text-center text-sm text-slate-500">Brak wiarygodnej serii czasowej dla tej metryki.</div>}

      <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Statistic label="Mediana" value={valueFormatter(metric.statistics.median)} />
        <Statistic label="Minimum / maksimum" value={metric.statistics.minimum !== null || metric.statistics.maximum !== null ? `${valueFormatter(metric.statistics.minimum)} / ${valueFormatter(metric.statistics.maximum)}` : "Brak danych"} />
        <Statistic label="Czas obserwacji" value={formatDuration(metric.statistics.validExposureSeconds)} />
        <Statistic label="Zakres ruchu" value={valueFormatter(metric.statistics.rangeOfMotion)} />
        <Statistic label="Najdłuższa stabilna postawa" value={formatDuration(metric.statistics.longestStablePostureSeconds)} />
      </dl>
      <div className="mt-4 flex flex-wrap gap-3 text-[11px] text-slate-500">
        {(["neutral", "mild", "elevated", "strong", "unknown"] as const).map((band) => <span key={band}>{DEVIATION_LABELS[band]}</span>)}
      </div>
    </section>
  );
}

function buildChart(metric: ReviewMetric, duration: number) {
  const validValues = metric.points.flatMap((point) => point.valid && point.value !== null ? [point.value] : []);
  const minimum = validValues.length ? Math.min(...validValues) : null;
  const maximum = validValues.length ? Math.max(...validValues) : null;
  const lower = minimum === null ? 0 : minimum;
  const upper = maximum === null ? 1 : maximum;
  const span = Math.max(1e-6, upper - lower);
  const chartDuration = Math.max(1, duration, ...metric.points.map((point) => point.time));
  const paths: string[] = [];
  let path = "";
  for (const point of metric.points) {
    if (!point.valid || point.value === null) {
      if (path) paths.push(path);
      path = "";
      continue;
    }
    const x = point.time / chartDuration * 900;
    const y = 285 - (point.value - lower) / span * 270;
    path += `${path ? " L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }
  if (path) paths.push(path);
  return { paths, minimum, maximum, duration: chartDuration };
}

function Statistic({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/[0.07] bg-slate-950/35 p-3"><dt className="text-[9px] uppercase tracking-wider text-slate-600">{label}</dt><dd className="mt-2 text-sm font-semibold text-slate-200">{value}</dd></div>;
}
