import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  FileVideo,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";

import { AnalysisLiveStatus } from "@/components/analyses/analysis-live-status";
import { PipelineSystemStatus } from "@/components/analyses/pipeline-system-status";
import { DeleteAnalysisButton } from "@/components/analyses/delete-analysis-button";
import { ErgonomicsMetricsCard } from "@/components/analyses/ergonomics-metrics-card";
import { PrivateVideoPreview } from "@/components/analyses/private-video-preview";
import { PoseResultsPreview } from "@/components/analyses/pose-results-preview";
import { RiskAssessmentCard } from "@/components/analyses/risk-assessment-card";
import { AnalysisAvailability } from "@/components/analyses/analysis-availability";
import { AnalysisReviewWorkspace } from "@/components/analyses/review/analysis-review-workspace";
import { AnalysisContextEditor } from "@/components/analyses/analysis-context-editor";
import { getSafeAnalysisErrorMessage } from "@/config/analysis-status";
import { normalizeAnalysisReview } from "@/lib/analysis-review/normalize";
import { normalizeCompanyMethods } from "@/lib/company-methods/normalize";
import { requireUser } from "@/lib/auth/access";
import type { RiskAssessmentSummary } from "@/types/analysis";
import { normalizeAnalysisContext, type AnalysisCategory, type Workstation } from "@/types/analysis-context";

import { retryFailedAnalysisStage } from "./actions";

export const dynamic = "force-dynamic";

type AnalysisDetailsPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function AnalysisDetailsPage({
  params,
}: AnalysisDetailsPageProps) {
  const { id } = await params;
  const { supabase, profile } = await requireUser();

  const { data: analysis, error } = await supabase
    .from("analyses")
    .select(`
      id,
      user_id,
      title,
      description,
      workstation_id,
      analysis_context,
      analysis_date,
      status,
      progress,
      attempts,
      worker_id,
      source_video_path,
      source_file_name,
      source_mime_type,
      source_size_bytes,
      source_duration_seconds,
      source_width,
      source_height,
      final_score,
      risk_level,
      critical_events_count,
      error_code,
      error_message,
      queued_at,
      created_at,
      updated_at,
      heartbeat_at,
      processing_stage,
      result_video_path,
      result_json_path,
      active_segment_start_frame,
      active_segment_end_frame,
      active_segment_start_seconds,
      active_segment_end_seconds,
      active_segment_duration_seconds,
      pose_presence_ratio,
      pose_tracking_method,
      pose_smoothing_method,
      pose_quality_version,
      thumbnail_path,
      pose_model,
      pose_sample_stride,
      pose_processed_frames,
      pose_detected_frames,
      pose_average_confidence,
      pose_completed_at,
      ergonomics_metrics_path,
      ergonomics_metrics_version,
      ergonomics_processed_frames,
      ergonomics_valid_metric_ratio,
      ergonomics_metrics_summary,
      ergonomics_completed_at,
      ergonomics_error_code,
      ergonomics_error_message,
      risk_assessment_path,
      risk_assessment_version,
      risk_profile_id,
      risk_profile_version,
      risk_profile_status,
      risk_processed_frames,
      risk_valid_metric_ratio,
      risk_overall_level,
      risk_assessment_summary,
      risk_completed_at,
      risk_error_code,
      risk_error_message,
      risk_worker_id,
      risk_started_at,
      risk_attempts,
      report_path,
      report_version,
      report_summary,
      report_completed_at,
      report_error_code,
      report_error_message,
      report_worker_id,
      report_started_at,
      report_attempts
    `)
    .eq("id", id)
    .maybeSingle();

  if (error || !analysis) {
    notFound();
  }

  const [{ data: workstationsData }, { data: categoriesData }, { data: categoryLinks }] = await Promise.all([
    supabase.from("workstations").select("id,name,code,description,department,area,is_active").eq("is_active", true).order("name"),
    supabase.from("analysis_categories").select("id,name,group_name,description,is_active").eq("is_active", true).order("group_name").order("name"),
    supabase.from("analysis_category_links").select("category:analysis_categories(id,name,group_name,description,is_active)").eq("analysis_id", analysis.id),
  ]);
  const workstations = (workstationsData ?? []) as unknown as Workstation[];
  const categories = (categoriesData ?? []) as unknown as AnalysisCategory[];
  const assignedCategories = (categoryLinks ?? []).flatMap((link) => link.category ? [link.category as unknown as AnalysisCategory] : []);
  const workstation = workstations.find((item) => item.id === analysis.workstation_id) ?? null;
  const metadata = { title: analysis.title, description: analysis.description, analysis_date: analysis.analysis_date, workstation, categories: assignedCategories, context: normalizeAnalysisContext(analysis.analysis_context) };

  const signedUrlLifetimeSeconds = 10 * 60;


  const resultUrlLifetimeSeconds =
    10 * 60;

  const resultVideoAccess =
    analysis.result_video_path
      ? await supabase.storage
          .from("analysis-results")
          .createSignedUrl(
            analysis.result_video_path,
            resultUrlLifetimeSeconds,
          )
      : {
          data: null,
          error: null,
        };

  const resultJsonAccess =
    analysis.result_json_path
      ? await supabase.storage
          .from("analysis-results")
          .createSignedUrl(
            analysis.result_json_path,
            resultUrlLifetimeSeconds,
          )
      : {
          data: null,
          error: null,
        };

  const thumbnailAccess =
    analysis.thumbnail_path
      ? await supabase.storage
          .from("analysis-results")
          .createSignedUrl(
            analysis.thumbnail_path,
            resultUrlLifetimeSeconds,
          )
      : {
          data: null,
          error: null,
        };

  const resultVideoUrl =
    resultVideoAccess.data?.signedUrl ??
    null;

  const resultJsonUrl =
    resultJsonAccess.data?.signedUrl ??
    null;

  const thumbnailUrl =
    thumbnailAccess.data?.signedUrl ??
    null;

  const resultAccessError =
    [
      resultVideoAccess.error?.message,
      resultJsonAccess.error?.message,
      thumbnailAccess.error?.message,
    ]
      .filter(Boolean)
      .join(" ") || null;


  const {
    data: signedVideoData,
    error: signedVideoError,
  } = await supabase.storage
    .from("analysis-videos")
    .createSignedUrl(
      analysis.source_video_path,
      signedUrlLifetimeSeconds,
    );

  const signedVideoUrl =
    signedVideoData?.signedUrl ?? null;

  const signedVideoErrorMessage =
    signedVideoError?.message ?? null;

  if (analysis.status === "completed") {
    const resultsBucket = supabase.storage.from("analysis-results");
    const emptyAccess = { data: null, error: null };
    const [
      poseFile,
      ergonomicsFile,
      riskFile,
      reportFile,
      ergonomicsDownload,
      riskDownload,
      reportDownload,
      assessmentFile,
      assessmentDownload,
      companyMethodsFile,
      companyMethodsDownload,
    ] = await Promise.all([
      analysis.result_json_path ? resultsBucket.download(analysis.result_json_path) : emptyAccess,
      analysis.ergonomics_metrics_path ? resultsBucket.download(analysis.ergonomics_metrics_path) : emptyAccess,
      analysis.risk_assessment_path ? resultsBucket.download(analysis.risk_assessment_path) : emptyAccess,
      analysis.report_path ? resultsBucket.download(analysis.report_path) : emptyAccess,
      analysis.ergonomics_metrics_path
        ? resultsBucket.createSignedUrl(analysis.ergonomics_metrics_path, resultUrlLifetimeSeconds, { download: "ergonomics-metrics.json" })
        : emptyAccess,
      analysis.risk_assessment_path
        ? resultsBucket.createSignedUrl(analysis.risk_assessment_path, resultUrlLifetimeSeconds, { download: "risk-assessment.json" })
        : emptyAccess,
      analysis.report_path
        ? resultsBucket.createSignedUrl(analysis.report_path, resultUrlLifetimeSeconds, { download: "analysis-report.json" })
        : emptyAccess,
      resultsBucket.download(`${analysis.user_id}/${analysis.id}/results/ergonomic-assessment.json`),
      resultsBucket.createSignedUrl(
        `${analysis.user_id}/${analysis.id}/results/ergonomic-assessment.json`,
        resultUrlLifetimeSeconds,
        { download: "ergonomic-assessment.json" },
      ),
      resultsBucket.download(`${analysis.user_id}/${analysis.id}/results/company-method-assessment.json`),
      resultsBucket.createSignedUrl(
        `${analysis.user_id}/${analysis.id}/results/company-method-assessment.json`,
        resultUrlLifetimeSeconds,
        { download: "company-method-assessment.json" },
      ),
    ]);
    const [poseDocument, ergonomicsDocument, riskDocument, reportDocument, rawAssessmentDocument, companyMethodsDocument] = await Promise.all([
      parseStorageJson(poseFile.data),
      parseStorageJson(ergonomicsFile.data),
      parseStorageJson(riskFile.data),
      parseStorageJson(reportFile.data),
      parseStorageJson(assessmentFile.data),
      parseStorageJson(companyMethodsFile.data),
    ]);
    const assessmentDocument = await attachAssessmentSignedUrls(
      rawAssessmentDocument,
      async (storagePath) => {
        const access = await resultsBucket.createSignedUrl(storagePath, resultUrlLifetimeSeconds);
        return access.data?.signedUrl ?? null;
      },
    );
    const sourceDurationSeconds = finiteNumber(analysis.source_duration_seconds);
    const model = normalizeAnalysisReview({
      analysisId: analysis.id,
      pose: poseDocument,
      ergonomics: ergonomicsDocument,
      risk: riskDocument,
      report: reportDocument,
      assessment: assessmentDocument,
      fallbackDurationSeconds: sourceDurationSeconds,
      fallbackProcessedFrames: analysis.pose_processed_frames,
    });
    const companyMethods = normalizeCompanyMethods(companyMethodsDocument);

    return (
      <AnalysisReviewWorkspace
        model={model}
        companyMethods={companyMethods}
        metadata={metadata}
        workstations={workstations}
        categories={categories}
        analysis={{
          id: analysis.id,
          title: analysis.title,
          description: analysis.description,
          createdAt: analysis.created_at,
          sourceFileName: analysis.source_file_name,
          sourceDurationSeconds,
          sourceWidth: analysis.source_width,
          sourceHeight: analysis.source_height,
        }}
        urls={{
          overlay: resultVideoUrl,
          original: signedVideoUrl,
          thumbnail: thumbnailUrl,
          poseJson: resultJsonUrl,
          ergonomicsJson: ergonomicsDownload.data?.signedUrl ?? null,
          riskJson: riskDownload.data?.signedUrl ?? null,
          reportJson: reportDownload.data?.signedUrl ?? null,
          assessmentJson: assessmentDownload.data?.signedUrl ?? null,
          companyMethodsJson: companyMethodsDownload.data?.signedUrl ?? null,
        }}
      />
    );
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] px-5 py-8 text-white sm:px-8">
      <Background />

      <div className="relative mx-auto max-w-6xl">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-[26px] border border-white/10 bg-slate-950/65 px-6 py-5 backdrop-blur-xl">
          <Link
            href="/panel"
            className="flex items-center gap-3"
          >
            <span className="flex size-11 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
              <Activity className="size-6 text-emerald-300" />
            </span>

            <span>
              <span className="block font-bold">
                Ergonomia AI
              </span>

              <span className="block text-xs text-slate-500">
                Szczegóły analizy
              </span>
            </span>
          </Link>

          <div className="flex flex-wrap items-center gap-3">
            <DeleteAnalysisButton
              analysisId={analysis.id}
              title={analysis.title}
              status={analysis.status}
            />

            <Link
              href="/panel/analizy"
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]"
            >
              <ArrowLeft className="size-4" />
              Historia analiz
            </Link>
          </div>
        </header>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1fr_0.38fr]">
          <div className="rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/65 to-cyan-400/[0.08] p-8 sm:p-10">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
              Analiza ergonomiczna
            </p>

            <h1 className="mt-5 text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
              {analysis.title}
            </h1>

            <p className="mt-5 max-w-3xl leading-7 text-slate-400">
              {analysis.description ||
                "Nie dodano dodatkowego opisu."}
            </p>
          </div>

          <AnalysisLiveStatus
            analysisId={analysis.id}
            initialState={{
              status: analysis.status,
              progress: analysis.progress,
              processing_stage: analysis.processing_stage,
              report_path: analysis.report_path,
              updated_at: analysis.updated_at,
            }}
          />
          <div className="lg:col-span-2">
            <PipelineSystemStatus
              initialAnalysis={{
                id: analysis.id,
                status: analysis.status,
                progress: analysis.progress,
                processing_stage: analysis.processing_stage,
                updated_at: analysis.updated_at,
                heartbeat_at: analysis.heartbeat_at,
                error_code: analysis.error_code,
              }}
            />
          </div>
        </section>

        <div className="mt-6"><AnalysisContextEditor analysisId={analysis.id} metadata={metadata} workstations={workstations} categories={categories} /></div>

        <section className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Nazwa pliku"
            value={analysis.source_file_name}
          />

          <Metric
            label="Rozmiar"
            value={formatBytes(
              Number(analysis.source_size_bytes),
            )}
          />

          <Metric
            label="Długość"
            value={formatDuration(
              analysis.source_duration_seconds,
            )}
          />

          <Metric
            label="Rozdzielczość"
            value={
              analysis.source_width &&
              analysis.source_height
                ? `${analysis.source_width} × ${analysis.source_height}`
                : "Odczyta worker"
            }
          />
        </section>

        <div className="mt-6">
          <PrivateVideoPreview
            signedUrl={signedVideoUrl}
            fileName={analysis.source_file_name}
            mimeType={analysis.source_mime_type}
            errorMessage={signedVideoErrorMessage}
            expiresInMinutes={10}
          />
          {[
            "ready-for-ergonomics",
            "ergonomics-processing",
            "ready-for-risk-assessment",
            "ergonomics-failed",
            "risk-processing",
            "risk-failed",
            "ready-for-report",
            "report-processing",
            "report-failed",
            "completed",
          ].includes(analysis.processing_stage ?? "") && (
              <div className="mt-6">
                {analysis.processing_stage === "ready-for-ergonomics" && (
                  <div className="mb-6">
                    <AnalysisAvailability />
                  </div>
                )}

                {[
                  "ready-for-risk-assessment",
                  "risk-processing",
                  "risk-failed",
                  "ready-for-report",
                  "report-processing",
                  "report-failed",
                  "completed",
                ].includes(analysis.processing_stage ?? "") && (
                  <div className="mb-6">
                    <ErgonomicsMetricsCard
                      version={analysis.ergonomics_metrics_version}
                      processedFrames={analysis.ergonomics_processed_frames}
                      validMetricRatio={analysis.ergonomics_valid_metric_ratio}
                      completedAt={analysis.ergonomics_completed_at}
                    />
                  </div>
                )}

                {[
                  "ready-for-report",
                  "report-processing",
                  "report-failed",
                  "completed",
                ].includes(analysis.processing_stage ?? "") &&
                  analysis.risk_assessment_summary && (
                    <div className="mb-6">
                      <RiskAssessmentCard
                        summary={
                          analysis.risk_assessment_summary as RiskAssessmentSummary
                        }
                        completedAt={analysis.risk_completed_at}
                      />
                    </div>
                  )}

                <PoseResultsPreview
                  videoUrl={resultVideoUrl}
                  thumbnailUrl={thumbnailUrl}
                  jsonUrl={resultJsonUrl}
                  poseModel={analysis.pose_model}
                  processedFrames={analysis.pose_processed_frames}
                  detectedFrames={analysis.pose_detected_frames}
                  averageConfidence={analysis.pose_average_confidence}
                  presenceRatio={analysis.pose_presence_ratio}
                  activeStartSeconds={analysis.active_segment_start_seconds}
                  activeEndSeconds={analysis.active_segment_end_seconds}
                  activeDurationSeconds={analysis.active_segment_duration_seconds}
                  trackingMethod={analysis.pose_tracking_method}
                  smoothingMethod={analysis.pose_smoothing_method}
                  errorMessage={resultAccessError}
                  expiresInMinutes={10}
                />

                {analysis.processing_stage === "completed" &&
                  analysis.report_path && (
                    <div className="mt-6 flex justify-center sm:justify-end">
                      <Link
                        href={`/panel/analizy/${analysis.id}/raport`}
                        className="inline-flex min-h-12 items-center justify-center rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                      >
                        Otwórz raport
                      </Link>
                    </div>
                  )}
              </div>
          )}
        </div>

        <section className="mt-6 rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
            Główne etapy
          </p>
          <h2 className="mt-2 text-2xl font-semibold">Pipeline analizy</h2>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <PipelineStep
              label="Film przesłany"
              completed={[
                "queued",
                "processing",
                "completed",
              ].includes(analysis.status)}
            />

            <PipelineStep
              label="Pose Pipeline V3.0"
              completed={
                [
                  "ready-for-ergonomics",
                  "ergonomics-processing",
                  "ergonomics-failed",
                  "ready-for-risk-assessment",
                  "risk-processing",
                  "risk-failed",
                  "ready-for-report",
                  "report-processing",
                  "report-failed",
                  "completed",
                ].includes(analysis.processing_stage ?? "") ||
                analysis.status === "completed"
              }
              active={
                analysis.status ===
                  "processing" &&
                [
                  "pose-claimed",
                  "downloading-for-pose",
                  "initializing-pose-inference",
                  "pose-inference",
                  "uploading-pose-results",
                  "saving-pose-results",
                  "downloading-for-pose-v3",
                  "pose-inference-active-segment-v3",
                  "pose-v3-rendering-validated-results",
                  "uploading-pose-results-v3",
                  "saving-pose-results-v3",
                ].includes(
                  analysis.processing_stage ??
                    "",
                )
              }
            />

            <PipelineStep
              label="Metryki ergonomiczne"
              completed={
                [
                  "ready-for-risk-assessment",
                  "risk-processing",
                  "risk-failed",
                  "ready-for-report",
                  "report-processing",
                  "report-failed",
                  "completed",
                ].includes(analysis.processing_stage ?? "")
              }
              active={[
                "ready-for-ergonomics",
                "ergonomics-processing",
              ].includes(analysis.processing_stage ?? "")}
            />

            <PipelineStep
              label="Ocena ryzyka"
              completed={[
                "ready-for-report",
                "report-processing",
                "report-failed",
                "completed",
              ].includes(analysis.processing_stage ?? "")}
              active={[
                "ready-for-risk-assessment",
                "risk-processing",
              ].includes(analysis.processing_stage ?? "")}
            />

            <PipelineStep
              label="Raport analizy"
              completed={analysis.processing_stage === "completed"}
              active={[
                "ready-for-report",
                "report-processing",
              ].includes(analysis.processing_stage ?? "")}
            />
          </div>
        </section>

        {analysis.status === "failed" && (
          <section className="mt-6 rounded-[28px] border border-red-400/20 bg-red-400/[0.07] p-6">
            <div className="flex items-start gap-4">
              <TriangleAlert className="mt-1 size-6 shrink-0 text-red-300" />

              <div>
                <p className="font-semibold text-red-200">
                  Wystąpił problem
                </p>

                <p className="mt-2 text-sm leading-6 text-red-200/75">
                  {getSafeAnalysisErrorMessage(analysis.processing_stage)}
                </p>

                {profile?.role === "admin" && (
                  <div className="mt-4 border-t border-red-300/15 pt-4">
                    <dl className="grid gap-2 text-xs text-red-100/70 sm:grid-cols-2">
                      <div><dt className="text-red-300/50">Kod</dt><dd>{analysis.error_code ?? "—"}</dd></div>
                      <div><dt className="text-red-300/50">Etap</dt><dd>{analysis.processing_stage ?? "—"}</dd></div>
                      <div><dt className="text-red-300/50">Liczba prób</dt><dd>{analysis.attempts ?? 0}</dd></div>
                      <div><dt className="text-red-300/50">Worker</dt><dd>{analysis.report_worker_id ?? analysis.risk_worker_id ?? analysis.worker_id ?? "zwolniony"}</dd></div>
                    </dl>
                    <form action={retryFailedAnalysisStage.bind(null, analysis.id)} className="mt-4">
                      <button
                        type="submit"
                        className="rounded-xl border border-red-300/25 bg-red-300/10 px-4 py-2 text-sm font-semibold text-red-100 transition hover:bg-red-300/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300"
                      >
                        {analysis.processing_stage === "report-failed" ? "Odbuduj raport" : "Ponów nieudany etap"}
                      </button>
                    </form>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <article className="min-w-0 rounded-[24px] border border-white/10 bg-white/[0.035] p-5">
      <FileVideo className="size-5 text-cyan-300" />

      <p className="mt-4 text-[10px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </p>

      <p className="mt-2 truncate font-semibold">
        {value}
      </p>
    </article>
  );
}

function PipelineStep({
  label,
  completed = false,
  active = false,
}: {
  label: string;
  completed?: boolean;
  active?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4">
      {completed ? (
        <CheckCircle2 className="size-5 shrink-0 text-emerald-300" />
      ) : active ? (
        <LoaderCircle className="size-5 shrink-0 animate-spin text-cyan-300" />
      ) : (
        <Clock3 className="size-5 shrink-0 text-slate-600" />
      )}

      <span
        className={
          completed
            ? "text-sm font-semibold text-emerald-200"
            : active
              ? "text-sm font-semibold text-cyan-200"
              : "text-sm text-slate-500"
        }
      >
        {label}
      </span>
    </div>
  );
}

function formatBytes(
  bytes: number,
) {
  if (!Number.isFinite(bytes)) {
    return "Brak danych";
  }

  return `${(
    bytes /
    (1024 * 1024)
  ).toFixed(1)} MB`;
}

function formatDuration(
  value: number | string | null,
) {
  const seconds = Number(value);

  if (!Number.isFinite(seconds)) {
    return "Brak danych";
  }

  const totalSeconds =
    Math.max(0, Math.round(seconds));

  const minutes =
    Math.floor(totalSeconds / 60);

  const remainingSeconds =
    totalSeconds % 60;

  return `${minutes}:${String(
    remainingSeconds,
  ).padStart(2, "0")}`;
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-52 -top-40 size-[620px] rounded-full bg-emerald-500/[0.07] blur-[160px]" />

      <div className="absolute -right-52 top-[500px] size-[620px] rounded-full bg-cyan-500/[0.07] blur-[170px]" />
    </div>
  );
}

async function parseStorageJson(file: Blob | null): Promise<unknown> {
  if (!file || file.size === 0) return null;
  try {
    return JSON.parse(await file.text()) as unknown;
  } catch {
    return null;
  }
}

function finiteNumber(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : Number.NaN;
  return Number.isFinite(numeric) ? numeric : null;
}

async function attachAssessmentSignedUrls(
  value: unknown,
  signer: (storagePath: string) => Promise<string | null>,
): Promise<unknown> {
  if (!isUnknownRecord(value) || !Array.isArray(value.keyframes)) return value;
  const keyframes = await Promise.all(value.keyframes.map(async (item) => {
    if (!isUnknownRecord(item) || typeof item.storage_path !== "string") return item;
    const signedUrl = await signer(item.storage_path);
    return signedUrl ? { ...item, signed_url: signedUrl } : item;
  }));
  return { ...value, keyframes };
}

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
