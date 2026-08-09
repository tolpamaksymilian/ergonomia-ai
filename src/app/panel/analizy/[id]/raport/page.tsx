import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, FileWarning } from "lucide-react";

import { ReportHeader } from "@/components/analyses/report/report-header";
import { ReportOverview } from "@/components/analyses/report/report-overview";
import {
  ReportBodyAreas,
  ReportHands,
  ReportKeyMoments,
  ReportLimitations,
  ReportMetrics,
  ReportMovement,
  ReportQuality,
} from "@/components/analyses/report/report-sections";
import { parseAnalysisReport } from "@/lib/analysis-report";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Raport analizy",
  description: "Techniczny raport analizy ergonomicznej.",
};

type ReportPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ReportPage({ params }: ReportPageProps) {
  const { id } = await params;
  const { supabase } = await requireUser();
  const { data: analysis, error } = await supabase
    .from("analyses")
    .select(`
      id,
      title,
      status,
      processing_stage,
      report_path,
      report_version,
      report_completed_at
    `)
    .eq("id", id)
    .maybeSingle();

  if (error) {
    throw new Error("Nie udało się pobrać danych raportu.");
  }
  if (!analysis) notFound();

  if (!analysis.report_path || analysis.status !== "completed") {
    return <ReportUnavailable analysisId={analysis.id} stage={analysis.processing_stage} />;
  }

  const bucket = supabase.storage.from("analysis-results");
  const [fileAccess, downloadAccess] = await Promise.all([
    bucket.download(analysis.report_path),
    bucket.createSignedUrl(analysis.report_path, 5 * 60, {
      download: "analysis-report.json",
    }),
  ]);

  if (fileAccess.error || !fileAccess.data) {
    return <ReportUnavailable analysisId={analysis.id} stage="storage-error" />;
  }

  let rawReport: unknown;
  try {
    rawReport = JSON.parse(await fileAccess.data.text()) as unknown;
  } catch {
    return <ReportUnavailable analysisId={analysis.id} stage="invalid-report" />;
  }
  const report = parseAnalysisReport(rawReport);
  if (!report || report.analysis.analysis_id !== analysis.id) {
    return <ReportUnavailable analysisId={analysis.id} stage="invalid-report" />;
  }

  return (
    <main className="report-page min-h-screen overflow-x-hidden bg-[#050b14] px-4 py-6 text-white sm:px-8 sm:py-8 print:bg-white print:px-0 print:py-0 print:text-black">
      <div className="mx-auto max-w-6xl space-y-6 print:max-w-none print:space-y-4">
        <ReportHeader
          report={report}
          completedAt={analysis.report_completed_at}
          downloadUrl={downloadAccess.data?.signedUrl ?? null}
        />
        <ReportOverview report={report} />
        <ReportBodyAreas report={report} />
        <ReportMetrics report={report} />
        <ReportHands report={report} />
        <ReportMovement report={report} />
        <ReportKeyMoments report={report} />
        <ReportQuality report={report} />
        <ReportLimitations report={report} />
      </div>
    </main>
  );
}

function ReportUnavailable({
  analysisId,
  stage,
}: {
  analysisId: string;
  stage: string | null;
}) {
  const message =
    stage === "report-processing"
      ? "Raport jest obecnie przygotowywany."
      : stage === "report-failed"
        ? "Nie udało się przygotować raportu. Wcześniejsze wyniki analizy zostały zachowane."
        : stage === "invalid-report"
          ? "Zapisany raport ma nieobsługiwany lub uszkodzony format."
          : stage === "storage-error"
            ? "Nie udało się bezpiecznie pobrać prywatnego pliku raportu."
            : "Raport nie jest jeszcze dostępny.";

  return (
    <main className="min-h-screen bg-[#050b14] px-5 py-10 text-white">
      <section className="mx-auto max-w-2xl rounded-[28px] border border-amber-300/20 bg-amber-300/[0.06] p-7 sm:p-9">
        <FileWarning className="size-8 text-amber-300" aria-hidden="true" />
        <h1 className="mt-5 text-2xl font-semibold">Raport analizy</h1>
        <p className="mt-3 leading-7 text-slate-300">{message}</p>
        <Link
          href={`/panel/analizy/${analysisId}`}
          className="mt-7 inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-4 py-3 font-semibold transition hover:bg-white/[0.1] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-cyan-200"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Wróć do analizy
        </Link>
      </section>
    </main>
  );
}
