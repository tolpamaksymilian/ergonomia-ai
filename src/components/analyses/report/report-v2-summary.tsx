import { CheckSquare, Lightbulb, ListChecks } from "lucide-react";

import { formatDuration, formatTimestamp } from "@/lib/analysis-review/formatters";
import type { AnalysisReport } from "@/types/analysis";

export function ReportV2Summary({ report }: { report: AnalysisReport }) {
  if (report.report_version !== "analysis-report-v2.0-beta.1") return null;
  return (
    <div className="space-y-6">
      <section className="report-card rounded-[26px] border border-cyan-300/15 bg-cyan-300/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white">
        <h2 className="flex items-center gap-2 text-xl font-semibold text-white print:text-black"><ListChecks className="size-5 text-cyan-300 print:text-black" aria-hidden="true" />Podsumowanie</h2>
        <ul className="mt-5 space-y-2 text-sm leading-6 text-slate-300 print:text-slate-700">{report.executive_summary?.map((line) => <li key={line}>— {line}</li>)}</ul>
      </section>
      {!!report.priority_findings?.length && <section className="report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white"><h2 className="text-xl font-semibold text-white print:text-black">Najważniejsze wnioski</h2><div className="mt-5 grid gap-3 md:grid-cols-2">{report.priority_findings.map((finding) => <article key={finding.finding_id} className="rounded-2xl border border-white/[0.08] bg-slate-950/35 p-5 print:border-slate-300 print:bg-white"><p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300 print:text-black">{finding.level}</p><h3 className="mt-2 font-semibold text-slate-100 print:text-black">{finding.title}</h3><p className="mt-2 text-sm leading-6 text-slate-400 print:text-slate-700">{finding.summary}</p><p className="mt-3 text-xs text-slate-500">{finding.duration_seconds != null ? `Czas: ${formatDuration(finding.duration_seconds)}` : "Czas: brak wiarygodnej wartości"}{finding.timestamp_seconds != null ? ` · Moment: ${formatTimestamp(finding.timestamp_seconds)}` : ""}</p></article>)}</div></section>}
      {!!report.recommendations?.length && <section className="report-card rounded-[26px] border border-white/10 bg-white/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white"><h2 className="flex items-center gap-2 text-xl font-semibold text-white print:text-black"><Lightbulb className="size-5 text-cyan-300 print:text-black" aria-hidden="true" />Kierunki do weryfikacji</h2><ol className="mt-5 space-y-3">{report.recommendations.map((item, index) => <li key={item.recommendation_id} className="flex gap-3 text-sm leading-6 text-slate-300 print:text-slate-700"><span className="font-semibold text-cyan-300 print:text-black">{index + 1}.</span>{item.text}</li>)}</ol></section>}
      {!!report.manual_confirmation?.length && <section className="report-card rounded-[26px] border border-amber-300/15 bg-amber-300/[0.035] p-6 sm:p-7 print:border-slate-300 print:bg-white"><h2 className="flex items-center gap-2 text-xl font-semibold text-white print:text-black"><CheckSquare className="size-5 text-amber-300 print:text-black" aria-hidden="true" />Do ręcznego potwierdzenia</h2><ul className="mt-5 space-y-2 text-sm leading-6 text-slate-300 print:text-slate-700">{report.manual_confirmation.map((item) => <li key={item.code}>— {item.label}</li>)}</ul></section>}
    </div>
  );
}
