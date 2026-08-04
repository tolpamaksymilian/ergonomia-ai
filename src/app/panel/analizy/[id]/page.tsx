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
  XCircle,
} from "lucide-react";

import { AnalysisAutoRefresh } from "@/components/analyses/analysis-auto-refresh";
import { DeleteAnalysisButton } from "@/components/analyses/delete-analysis-button";
import { ErgonomicsMetricsCard } from "@/components/analyses/ergonomics-metrics-card";
import { PrivateVideoPreview } from "@/components/analyses/private-video-preview";
import { PoseResultsPreview } from "@/components/analyses/pose-results-preview";
import { AnalysisAvailability } from "@/components/analyses/analysis-availability";
import { requireUser } from "@/lib/auth/access";

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
  const { supabase } = await requireUser();

  const { data: analysis, error } = await supabase
    .from("analyses")
    .select(`
      id,
      title,
      description,
      status,
      progress,
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
      ergonomics_error_message
    `)
    .eq("id", id)
    .maybeSingle();

  if (error || !analysis) {
    notFound();
  }

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

  const shouldRefresh =
    analysis.status === "uploading" ||
    analysis.status === "processing" ||
    (
      analysis.status === "queued" &&
      [
        null,
        "queued",
        "ready-for-ai",
        "ready-for-ergonomics",
      ].includes(
        analysis.processing_stage,
      )
    );

  const status = getStatusDetails(
    analysis.status,
    analysis.processing_stage,
  );

  const StatusIcon = status.icon;

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] px-5 py-8 text-white sm:px-8">
      <AnalysisAutoRefresh
        enabled={shouldRefresh}
      />

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

          <aside
            className={`rounded-[30px] border p-7 ${status.containerClass}`}
          >
            <div
              className={`flex size-12 items-center justify-center rounded-2xl ${status.iconClass}`}
            >
              <StatusIcon
                className={`size-6 ${
                  status.animated
                    ? "animate-spin"
                    : ""
                }`}
              />
            </div>

            <p className="mt-6 text-xs uppercase tracking-[0.18em] text-slate-500">
              Aktualny status
            </p>

            <p className={`mt-2 text-2xl font-bold ${status.textClass}`}>
              {status.label}
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-400">
              {status.description}
            </p>

            {shouldRefresh && (
              <p className="mt-5 text-xs text-slate-600">
                Widok odświeża się automatycznie.
              </p>
            )}
          </aside>
        </section>

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
          ].includes(analysis.processing_stage ?? "") && (
              <div className="mt-6">
                {analysis.processing_stage === "ready-for-ergonomics" && (
                  <div className="mb-6">
                    <AnalysisAvailability />
                  </div>
                )}

                {analysis.processing_stage === "ready-for-risk-assessment" && (
                  <div className="mb-6">
                    <ErgonomicsMetricsCard
                      version={analysis.ergonomics_metrics_version}
                      processedFrames={analysis.ergonomics_processed_frames}
                      validMetricRatio={analysis.ergonomics_valid_metric_ratio}
                      completedAt={analysis.ergonomics_completed_at}
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
              </div>
          )}
        </div>

        <section className="mt-6 rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Postęp przetwarzania
              </p>

              <h2 className="mt-2 text-2xl font-semibold">
                Pipeline analizy
              </h2>
            </div>

            <p className="text-3xl font-bold text-cyan-300">
              {analysis.progress}%
            </p>
          </div>

          <div className="mt-6 h-2 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400 transition-[width]"
              style={{
                width: `${analysis.progress}%`,
              }}
            />
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
                analysis.processing_stage === "ready-for-risk-assessment"
              }
              active={[
                "ready-for-ergonomics",
                "ergonomics-processing",
              ].includes(analysis.processing_stage ?? "")}
            />

            <PipelineStep
              label="Ocena ryzyka — w przygotowaniu"
            />
          </div>
        </section>

        {analysis.error_message && (
          <section className="mt-6 rounded-[28px] border border-red-400/20 bg-red-400/[0.07] p-6">
            <div className="flex items-start gap-4">
              <TriangleAlert className="mt-1 size-6 shrink-0 text-red-300" />

              <div>
                <p className="font-semibold text-red-200">
                  Wystąpił problem
                </p>

                <p className="mt-2 text-sm leading-6 text-red-200/75">
                  {analysis.error_message}
                </p>

                {analysis.error_code && (
                  <p className="mt-3 text-xs text-red-300/50">
                    Kod: {analysis.error_code}
                  </p>
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

function getStatusDetails(
  status: string,
  processingStage: string | null,
) {
  if (
    status === "processing" &&
    processingStage === "ergonomics-processing"
  ) {
    return {
      label: "Obliczanie metryk",
      description: "Obliczamy metryki ergonomiczne.",
      icon: LoaderCircle,
      animated: true,
      containerClass:
        "border-cyan-400/20 bg-cyan-400/[0.06]",
      iconClass:
        "bg-cyan-400/10 text-cyan-300",
      textClass: "text-cyan-300",
    };
  }

  if (
    status === "queued" &&
    processingStage === "ready-for-risk-assessment"
  ) {
    return {
      label: "Metryki gotowe",
      description: "Metryki są gotowe. Kolejny etap to ocena ryzyka.",
      icon: CheckCircle2,
      animated: false,
      containerClass:
        "border-emerald-400/20 bg-emerald-400/[0.06]",
      iconClass:
        "bg-emerald-400/10 text-emerald-300",
      textClass: "text-emerald-300",
    };
  }

  if (
    status === "queued" &&
    processingStage === "ready-for-ergonomics"
  ) {
    return {
      label: "Poza gotowa do metryk",
      description: "Pozycja została wykryta. Czekamy na obliczenie metryk.",
      icon: CheckCircle2,
      animated: false,
      containerClass:
        "border-emerald-400/20 bg-emerald-400/[0.06]",
      iconClass:
        "bg-emerald-400/10 text-emerald-300",
      textClass: "text-emerald-300",
    };
  }

  switch (status) {
    case "uploading":
      return {
        label: "Przesyłanie filmu",
        description:
          "Film jest aktualnie przesyłany do prywatnego magazynu.",
        icon: LoaderCircle,
        animated: true,
        containerClass:
          "border-cyan-400/20 bg-cyan-400/[0.06]",
        iconClass:
          "bg-cyan-400/10 text-cyan-300",
        textClass: "text-cyan-300",
      };

    case "queued":
      return {
        label: "Oczekuje w kolejce",
        description:
          "Film został zapisany i czeka na uruchomienie workera AI.",
        icon: Clock3,
        animated: false,
        containerClass:
          "border-amber-300/20 bg-amber-400/[0.06]",
        iconClass:
          "bg-amber-400/10 text-amber-300",
        textClass: "text-amber-300",
      };

    case "processing":
      return {
        label: "Analiza w toku",
        description:
          "Worker AI analizuje nagranie i zapisuje wyniki.",
        icon: LoaderCircle,
        animated: true,
        containerClass:
          "border-cyan-400/20 bg-cyan-400/[0.06]",
        iconClass:
          "bg-cyan-400/10 text-cyan-300",
        textClass: "text-cyan-300",
      };

    case "completed":
      return {
        label: "Analiza ukończona",
        description:
          "Przetwarzanie zostało zakończone. Zakres dostępnych wyników zależy od wdrożonych etapów systemu.",
        icon: CheckCircle2,
        animated: false,
        containerClass:
          "border-emerald-400/20 bg-emerald-400/[0.06]",
        iconClass:
          "bg-emerald-400/10 text-emerald-300",
        textClass: "text-emerald-300",
      };

    case "failed":
      return {
        label: "Analiza nieudana",
        description:
          "Podczas przesyłania albo przetwarzania wystąpił błąd.",
        icon: XCircle,
        animated: false,
        containerClass:
          "border-red-400/20 bg-red-400/[0.06]",
        iconClass:
          "bg-red-400/10 text-red-300",
        textClass: "text-red-300",
      };

    case "cancelled":
      return {
        label: "Anulowano",
        description:
          "Operacja została anulowana przez użytkownika.",
        icon: XCircle,
        animated: false,
        containerClass:
          "border-slate-400/20 bg-white/[0.035]",
        iconClass:
          "bg-white/[0.06] text-slate-400",
        textClass: "text-slate-300",
      };

    default:
      return {
        label: "Wersja robocza",
        description:
          "Analiza nie została jeszcze uruchomiona.",
        icon: Clock3,
        animated: false,
        containerClass:
          "border-white/10 bg-white/[0.035]",
        iconClass:
          "bg-white/[0.06] text-slate-400",
        textClass: "text-slate-300",
      };
  }
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
