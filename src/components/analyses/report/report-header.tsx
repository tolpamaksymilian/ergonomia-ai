import Link from "next/link";
import { Activity, ArrowLeft, CheckCircle2 } from "lucide-react";

import { ReportActions } from "@/components/analyses/report/report-actions";
import { formatDuration } from "@/lib/analysis-review/formatters";
import type { AnalysisReport } from "@/types/analysis";

type ReportHeaderProps = {
  report: AnalysisReport;
  completedAt: string | null;
  downloadUrl: string | null;
};

export function ReportHeader({
  report,
  completedAt,
  downloadUrl,
}: ReportHeaderProps) {
  return (
    <header className="report-card rounded-[28px] border border-white/10 bg-slate-950/75 p-6 sm:p-8">
      <div className="report-screen-only flex flex-wrap items-center justify-between gap-4" data-print-hidden>
        <Link
          href={`/panel/analizy/${report.analysis.analysis_id}`}
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-300 transition hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-200"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Workspace analizy
        </Link>
        <ReportActions downloadUrl={downloadUrl} />
      </div>

      <div className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between print:mt-0">
        <div>
          <div className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 print:border-slate-300 print:bg-transparent">
              <Activity className="size-6 text-cyan-200 print:text-black" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300 print:text-slate-600">
                Ergonomia AI
              </p>
              <p className="text-sm text-slate-500 print:text-slate-600">
                Analiza ergonomiczna
              </p>
            </div>
          </div>
          <h1 className="mt-6 max-w-3xl text-3xl font-bold tracking-[-0.035em] text-white sm:text-5xl print:text-black">
            {report.analysis.title}
          </h1>
        </div>

        <div className="report-card min-w-56 rounded-2xl border border-emerald-300/20 bg-emerald-300/[0.07] p-4 print:border-slate-300 print:bg-transparent">
          <p className="flex items-center gap-2 font-semibold text-emerald-200 print:text-black">
            <CheckCircle2 className="size-5" aria-hidden="true" />
            Analiza gotowa
          </p>
          <dl className="mt-3 space-y-1 text-xs text-slate-400 print:text-slate-700">
            <div className="flex justify-between gap-4">
              <dt>Wersja</dt>
              <dd>{report.report_version}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Data</dt>
              <dd>{formatDate(completedAt ?? report.generated_at)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Nagranie</dt>
              <dd>{formatDuration(report.analysis.source_duration_seconds)}</dd>
            </div>
            {report.analysis.source_file_name && (
              <div className="flex justify-between gap-4">
                <dt>Plik</dt>
                <dd className="max-w-40 truncate" title={report.analysis.source_file_name}>{report.analysis.source_file_name}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>
      <dl className="mt-6 grid gap-2 border-t border-white/[0.08] pt-4 text-[10px] text-slate-500 sm:grid-cols-2 lg:grid-cols-4 print:border-slate-300 print:text-slate-700">
        <div><dt>Pose Pipeline</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.pose_pipeline_version ?? "Brak danych"}</dd></div>
        <div><dt>Metrics Engine</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.ergonomics_metrics_version}</dd></div>
        <div><dt>Risk Engine</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.risk_engine_version}</dd></div>
        <div><dt>Report Engine</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.report_engine_version}</dd></div>
      </dl>
    </header>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(value));
}
