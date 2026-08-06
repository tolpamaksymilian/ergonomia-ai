import { Clock3, FileWarning, ScanLine } from "lucide-react";

import type {
  AnalysisReport,
  ReportMetricSummary,
  RiskLevel,
} from "@/types/analysis";

const levelLabels: Record<RiskLevel, string> = {
  low: "Niskie",
  moderate: "Umiarkowane",
  high: "Wysokie",
  critical: "Bardzo wysokie",
  insufficient_data: "Brak danych",
};

const limitationLabels: Record<string, string> = {
  analysis_based_on_2d_video: "Analiza bazuje głównie na obrazie 2D.",
  occluded_body_parts_may_be_missing: "Zasłonięte części ciała mogą nie dostarczać danych.",
  result_is_technical_screening: "Wynik jest technicznym screeningiem, a nie diagnozą.",
  specialist_review_required: "Wynik wymaga interpretacji przez kompetentnego specjalistę.",
  development_profile_used: "Użyty profil ma status rozwojowy.",
  production_profile_not_used: "Nie użyto zatwierdzonego profilu produkcyjnego.",
  result_depends_on_recording_quality: "Wynik zależy od jakości nagrania, kadru i oświetlenia.",
  external_load_not_measured: "Nagranie nie dostarcza pełnej informacji o obciążeniu zewnętrznym.",
  rula_not_calculated: "Raport nie zawiera oceny RULA.",
  reba_not_calculated: "Raport nie zawiera oceny REBA.",
  frame_timestamps_replaced_with_fps_fallback: "Czas ekspozycji wykorzystał jawny fallback FPS.",
  exposure_timing_unavailable: "Dla części ekspozycji nie było wiarygodnej osi czasu.",
};

export function ReportBodyAreas({ report }: { report: AnalysisReport }) {
  return (
    <section className="report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white">
      <h2 className="text-xl font-semibold text-white print:text-black">Obszary ciała</h2>
      {report.body_areas.length ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {report.body_areas.map((area) => (
            <article key={area.area_id} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold text-slate-100 print:text-black">{area.label}</h3>
                <span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-300 print:border-slate-400 print:text-black">
                  {levelLabels[area.level]}
                </span>
              </div>
              {area.coverage !== undefined && (
                <p className="mt-3 text-xs text-slate-500 print:text-slate-700">
                  Pokrycie danych: {formatPercent(area.coverage)}
                </p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Brak obszarów możliwych do podsumowania.</p>
      )}
    </section>
  );
}

export function ReportMetrics({ report }: { report: AnalysisReport }) {
  return (
    <section className="report-card overflow-hidden rounded-[26px] border border-white/10 bg-white/[0.035] print:border-slate-300 print:bg-white">
      <div className="p-6 sm:p-7">
        <h2 className="text-xl font-semibold text-white print:text-black">Najważniejsze metryki</h2>
        <p className="mt-2 text-sm text-slate-500 print:text-slate-700">
          Podsumowania istniejących wyników. Pełna seria klatkowa pozostaje w pliku metryk.
        </p>
      </div>
      {report.metric_summary.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm print:min-w-0">
            <thead className="border-y border-white/[0.08] bg-slate-950/55 text-xs uppercase tracking-wide text-slate-500 print:border-slate-300 print:bg-white print:text-slate-700">
              <tr>
                <th className="px-6 py-3 font-medium">Metryka</th>
                <th className="px-4 py-3 font-medium">Poziom</th>
                <th className="px-4 py-3 font-medium">Mediana</th>
                <th className="px-4 py-3 font-medium">Maksimum</th>
                <th className="px-4 py-3 font-medium">Pokrycie</th>
                <th className="px-6 py-3 font-medium">Ekspozycja wysoka</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.07] print:divide-slate-300">
              {report.metric_summary.map((metric) => (
                <MetricRow key={metric.metric_name} metric={metric} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-6 pb-6 text-sm text-slate-500">Brak metryk możliwych do zestawienia.</p>
      )}
    </section>
  );
}

function MetricRow({ metric }: { metric: ReportMetricSummary }) {
  return (
    <tr className="report-card print:text-black">
      <td className="px-6 py-4 font-medium text-slate-200 print:text-black">{metric.label}</td>
      <td className="px-4 py-4 text-slate-400 print:text-black">{levelLabels[metric.level]}</td>
      <td className="px-4 py-4 text-slate-400 print:text-black">{formatMeasurement(metric.statistics?.median, metric.unit)}</td>
      <td className="px-4 py-4 text-slate-400 print:text-black">{formatMeasurement(metric.statistics?.maximum, metric.unit)}</td>
      <td className="px-4 py-4 text-slate-400 print:text-black">{metric.valid_ratio === undefined ? "—" : formatPercent(metric.valid_ratio)}</td>
      <td className="px-6 py-4 text-slate-400 print:text-black">{formatExposure(metric)}</td>
    </tr>
  );
}

export function ReportKeyMoments({ report }: { report: AnalysisReport }) {
  return (
    <section className="report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white">
      <h2 className="flex items-center gap-2 text-xl font-semibold text-white print:text-black">
        <ScanLine className="size-5 text-cyan-300 print:text-black" aria-hidden="true" />
        Kluczowe momenty
      </h2>
      {report.key_moments.length ? (
        <ol className="mt-5 grid gap-3 sm:grid-cols-2">
          {report.key_moments.map((moment, index) => (
            <li key={`${moment.source_frame_index ?? "frame"}-${moment.metric_name}-${index}`} className="report-card rounded-2xl border border-white/[0.08] bg-slate-950/35 p-4 print:border-slate-300 print:bg-white">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-100 print:text-black">{moment.metric_label}</span>
                <span className="text-xs text-slate-500 print:text-slate-700">{levelLabels[moment.level]}</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-400 print:text-slate-700">{moment.reason}</p>
              <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500 print:text-slate-700">
                {moment.source_frame_index !== undefined && <span>Klatka {moment.source_frame_index}</span>}
                {moment.timestamp_seconds !== undefined && (
                  <span className="inline-flex items-center gap-1"><Clock3 className="size-3" aria-hidden="true" />{formatSeconds(moment.timestamp_seconds)}</span>
                )}
                {moment.area_label && <span>{moment.area_label}</span>}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Risk Engine nie wskazał kandydatów kluczowych momentów.</p>
      )}
    </section>
  );
}

export function ReportLimitations({ report }: { report: AnalysisReport }) {
  return (
    <section className="report-card rounded-[26px] border border-amber-300/15 bg-amber-300/[0.045] p-6 sm:p-7 print:border-slate-300 print:bg-white">
      <h2 className="flex items-center gap-2 text-xl font-semibold text-amber-100 print:text-black">
        <FileWarning className="size-5" aria-hidden="true" />
        Ograniczenia
      </h2>
      <ul className="mt-5 grid gap-2 text-sm leading-6 text-amber-50/70 sm:grid-cols-2 print:text-slate-700">
        {report.limitations.map((limitation) => (
          <li key={limitation} className="flex items-start gap-2">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-300 print:bg-black" />
            {limitationLabels[limitation] ?? limitation}
          </li>
        ))}
      </ul>
      <p className="mt-6 border-t border-amber-200/10 pt-5 font-semibold text-amber-100 print:border-slate-300 print:text-black">
        {report.disclaimer}
      </p>
    </section>
  );
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("pl-PL", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

function formatMeasurement(value: number | undefined, unit: "deg" | "ratio") {
  if (value === undefined) return "—";
  const formatted = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 }).format(value);
  return unit === "deg" ? `${formatted}°` : formatted;
}

function formatExposure(metric: ReportMetricSummary) {
  const ratio = Math.max(
    metric.exposure?.high_exposure_ratio ?? 0,
    metric.exposure?.critical_exposure_ratio ?? 0,
  );
  return metric.exposure ? formatPercent(ratio) : "—";
}

function formatSeconds(value: number) {
  return `${new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 }).format(value)} s`;
}
