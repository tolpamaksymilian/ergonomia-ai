import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Database,
} from "lucide-react";

import type { AnalysisReport, RiskLevel } from "@/types/analysis";

type ReportOverviewProps = {
  report: AnalysisReport;
};

const levels: Record<
  RiskLevel,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  low: {
    label: "Niskie",
    icon: CheckCircle2,
    className: "border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-100",
  },
  moderate: {
    label: "Umiarkowane",
    icon: AlertTriangle,
    className: "border-amber-300/25 bg-amber-300/[0.08] text-amber-100",
  },
  high: {
    label: "Wysokie",
    icon: AlertTriangle,
    className: "border-orange-300/25 bg-orange-300/[0.08] text-orange-100",
  },
  critical: {
    label: "Bardzo wysokie",
    icon: AlertOctagon,
    className: "border-red-300/25 bg-red-300/[0.08] text-red-100",
  },
  insufficient_data: {
    label: "Niewystarczające dane",
    icon: CircleHelp,
    className: "border-slate-300/20 bg-slate-300/[0.06] text-slate-200",
  },
};

export function ReportOverview({ report }: ReportOverviewProps) {
  const presentation = levels[report.risk_summary.overall_level];
  const Icon = presentation.icon;
  return (
    <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      <section className={`report-card rounded-[26px] border p-6 sm:p-7 print:border-slate-300 print:bg-white print:text-black ${presentation.className}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
          Ogólny wynik techniczny
        </p>
        <div className="mt-5 flex items-center gap-3">
          <Icon className="size-7" aria-hidden="true" />
          <h2 className="text-3xl font-bold">{presentation.label}</h2>
        </div>
        <p className="mt-5 text-sm leading-6 opacity-80">
          {report.risk_summary.insufficient_data
            ? "Za mało poprawnych danych do wiarygodnej oceny."
            : report.observations[0] ?? "Klasyfikacja powstała na podstawie dostępnych metryk."}
        </p>
      </section>

      <section className="report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-white print:text-black">
          <Database className="size-5 text-cyan-300 print:text-black" aria-hidden="true" />
          Jakość i kompletność danych
        </h2>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2">
          <Datum label="Pokrycie poprawnymi danymi" value={formatPercent(report.data_quality.valid_metric_ratio)} />
          <Datum label="Liczba klatek" value={String(report.data_quality.frame_count)} />
          {report.data_quality.pose_presence_ratio !== undefined && (
            <Datum label="Obecność pozy" value={formatPercent(report.data_quality.pose_presence_ratio)} />
          )}
          {report.data_quality.invalid_metric_values !== undefined && (
            <Datum label="Odrzucone wartości metryk" value={String(report.data_quality.invalid_metric_values)} />
          )}
        </dl>
      </section>
    </div>
  );
}

function Datum({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-slate-950/45 p-4 print:border-slate-300 print:bg-white">
      <dt className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</dt>
      <dd className="mt-2 font-semibold text-slate-100 print:text-black">{value}</dd>
    </div>
  );
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("pl-PL", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}
