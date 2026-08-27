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
        className="ui-button-primary text-sm"
      >
        <Printer className="size-4" aria-hidden="true" />
        Drukuj raport
      </button>

      {downloadUrl ? (
        <a
          href={downloadUrl}
          className="ui-button-secondary text-sm"
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
