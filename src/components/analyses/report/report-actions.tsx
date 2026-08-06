"use client";

import { Download, Printer } from "lucide-react";

type ReportActionsProps = {
  downloadUrl: string | null;
};

export function ReportActions({ downloadUrl }: ReportActionsProps) {
  return (
    <div className="report-actions flex flex-wrap gap-3" data-print-hidden>
      <button
        type="button"
        onClick={() => window.print()}
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-200"
      >
        <Printer className="size-4" aria-hidden="true" />
        Drukuj raport
      </button>

      {downloadUrl ? (
        <a
          href={downloadUrl}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-4 py-2.5 text-sm font-semibold text-slate-100 transition hover:bg-white/[0.1] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-200"
        >
          <Download className="size-4" aria-hidden="true" />
          Pobierz dane raportu
        </a>
      ) : (
        <span className="inline-flex min-h-11 items-center rounded-xl border border-white/10 px-4 text-sm text-slate-500">
          Pobieranie chwilowo niedostępne
        </span>
      )}
    </div>
  );
}
