import {
  CalendarCheck2,
  CircleGauge,
  Layers3,
  ListChecks,
} from "lucide-react";

import type { ErgonomicsAnalysisMetadata } from "@/types/analysis";

type ErgonomicsMetricsCardProps = {
  version: ErgonomicsAnalysisMetadata["ergonomics_metrics_version"];
  processedFrames: ErgonomicsAnalysisMetadata["ergonomics_processed_frames"];
  validMetricRatio: ErgonomicsAnalysisMetadata["ergonomics_valid_metric_ratio"];
  completedAt: ErgonomicsAnalysisMetadata["ergonomics_completed_at"];
};

export function ErgonomicsMetricsCard({
  version,
  processedFrames,
  validMetricRatio,
  completedAt,
}: ErgonomicsMetricsCardProps) {
  return (
    <section
      className="rounded-[28px] border border-cyan-400/20 bg-cyan-400/[0.055] p-6"
      aria-labelledby="ergonomics-metrics-title"
    >
      <div className="flex items-start gap-4">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10">
          <CircleGauge className="size-5 text-cyan-200" aria-hidden="true" />
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.17em] text-cyan-300/75">
            Dane techniczne etapu
          </p>
          <h2 id="ergonomics-metrics-title" className="mt-1 text-xl font-semibold text-cyan-100">
            Metryki są gotowe
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Kolejny etap to ocena ryzyka.
          </p>
        </div>
      </div>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TechnicalValue
          icon={Layers3}
          label="Metrics Engine"
          value={version || "Brak danych"}
        />
        <TechnicalValue
          icon={ListChecks}
          label="Przetworzone klatki"
          value={formatInteger(processedFrames)}
        />
        <TechnicalValue
          icon={CircleGauge}
          label="Pokrycie poprawnymi danymi"
          value={formatCoverage(validMetricRatio)}
        />
        <TechnicalValue
          icon={CalendarCheck2}
          label="Zakończenie etapu"
          value={formatDate(completedAt)}
        />
      </dl>

      <p className="mt-4 text-xs leading-5 text-slate-500">
        Liczba metryk: <span className="font-semibold text-slate-300">14</span>.
        Pokrycie oznacza udział poprawnych pomiarów, a nie dokładność AI.
      </p>
    </section>
  );
}

function TechnicalValue({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof CircleGauge;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-white/[0.07] bg-slate-950/40 p-4">
      <dt className="flex items-center gap-2 text-[9px] uppercase tracking-[0.13em] text-slate-500">
        <Icon className="size-3.5 shrink-0 text-cyan-300" aria-hidden="true" />
        {label}
      </dt>
      <dd className="mt-2 break-words text-sm font-semibold text-slate-100">
        {value}
      </dd>
    </div>
  );
}

function formatInteger(value: number | null) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? new Intl.NumberFormat("pl-PL").format(value)
    : "Brak danych";
}

function formatCoverage(value: number | string | null) {
  if (value === null || value === "") {
    return "Brak danych";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "Brak danych";
  }
  return new Intl.NumberFormat("pl-PL", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.min(1, Math.max(0, numeric)));
}

function formatDate(value: string | null) {
  if (!value) {
    return "Brak danych";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Brak danych";
  }
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(date);
}
