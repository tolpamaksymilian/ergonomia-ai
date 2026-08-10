import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
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
      <section className={`report-card rounded-[26px] border p-6 sm:p-7 print:border-slate-300 print:bg-white print:text-black ${presentation.className}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
          Ocena Risk Engine
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
  );
}
