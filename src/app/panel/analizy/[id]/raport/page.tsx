import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, FileWarning } from "lucide-react";

import { ReportHeader } from "@/components/analyses/report/report-header";
import { ReportOverview } from "@/components/analyses/report/report-overview";
import { ReportManualConfirmation, ReportPriorityFindings, ReportRecommendations, ReportV2Summary } from "@/components/analyses/report/report-v2-summary";
import {
  ReportBodyAreas,
  ReportHands,
  ReportKeyMoments,
  ReportLimitations,
  ReportMetrics,
  ReportMovement,
  ReportAssessment,
  ReportCompanyMethods,
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
      user_id,
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
  const [fileAccess, downloadAccess, companyMethodsAccess] = await Promise.all([
    bucket.download(analysis.report_path),
    bucket.createSignedUrl(analysis.report_path, 5 * 60, {
      download: "analysis-report.json",
    }),
    bucket.download(`${analysis.user_id}/${analysis.id}/results/company-method-assessment.json`),
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
  if (companyMethodsAccess.data) {
    try {
      const companyMethods: unknown = JSON.parse(await companyMethodsAccess.data.text());
      if (isRecord(companyMethods) && companyMethods.schema_version === "1.0") {
        report.company_methods = {
          status: "available",
          company_methods_version: text(companyMethods.company_methods_version),
          missing_inputs: strings(companyMethods.missing_inputs),
          limitations: strings(companyMethods.limitations),
          owas: isRecord(companyMethods.owas) ? companyMethods.owas : null,
          ejms: isRecord(companyMethods.ejms) ? companyMethods.ejms : null,
          risk_score: isRecord(companyMethods.risk_score) ? companyMethods.risk_score : null,
          measurable_factors: Array.isArray(companyMethods.measurable_factors) ? companyMethods.measurable_factors.filter(isRecord) : [],
          chemical: isRecord(companyMethods.chemical) ? companyMethods.chemical : null,
        };
      }
    } catch {
      // The immutable report remains usable when the optional live method file is invalid.
    }
  }
  if (report.ergonomic_assessment?.keyframes) {
    report.ergonomic_assessment.keyframes = await Promise.all(
      report.ergonomic_assessment.keyframes.map(async (keyframe) => {
        if (!keyframe.storage_path) return keyframe;
        const access = await bucket.createSignedUrl(keyframe.storage_path, 5 * 60);
        return access.data?.signedUrl
          ? { ...keyframe, signed_url: access.data.signedUrl }
          : keyframe;
      }),
    );
  }

  return (
    <main className="report-page min-h-screen overflow-x-hidden bg-[#050b14] px-4 py-6 text-white sm:px-8 sm:py-8 print:bg-white print:px-0 print:py-0 print:text-black">
      <div className="mx-auto max-w-6xl space-y-6 print:max-w-none print:space-y-4">
        <ReportHeader
          report={report}
          completedAt={analysis.report_completed_at}
          downloadUrl={downloadAccess.data?.signedUrl ?? null}
        />
        <ReportV2Summary report={report} />
        <ReportQuality report={report} />
        <ReportPriorityFindings report={report} />
        <ReportOverview report={report} />
        <ReportAssessment report={report} />
        <ReportCompanyMethods report={report} />
        <ReportHands report={report} />
        <ReportMovement report={report} />
        <ReportManualConfirmation report={report} />
        <ReportRecommendations report={report} />
        <ReportLimitations report={report} />
        <details className="report-card rounded-[26px] border border-white/10 bg-white/[0.025] p-6 print:border-slate-300 print:bg-white">
          <summary className="cursor-pointer font-semibold text-slate-200 focus-visible:outline-2 focus-visible:outline-cyan-200 print:text-black">Załącznik techniczny</summary>
          <div className="mt-6 space-y-6">
            <dl className="grid gap-2 text-[10px] text-slate-500 sm:grid-cols-2 lg:grid-cols-4 print:text-slate-700">
              <div><dt>Pose Pipeline</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.pose_pipeline_version ?? "Brak danych"}</dd></div>
              <div><dt>Metrics Engine</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.ergonomics_metrics_version}</dd></div>
              <div><dt>Risk Engine</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.risk_engine_version}</dd></div>
              <div><dt>Report Engine</dt><dd className="mt-1 font-medium text-slate-300 print:text-black">{report.processing.report_engine_version}</dd></div>
            </dl>
            <ReportBodyAreas report={report} />
            <ReportMetrics report={report} />
            <ReportKeyMoments report={report} />
          </div>
        </details>
      </div>
    </main>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function text(value: unknown) { return typeof value === "string" ? value : undefined; }
function strings(value: unknown) { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []; }

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
