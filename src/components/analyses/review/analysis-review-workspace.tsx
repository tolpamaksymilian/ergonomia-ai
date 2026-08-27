"use client";

import { Activity, ArrowLeft, CheckCircle2, Download, FileText, Video } from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useRef, useState } from "react";

import { formatDuration } from "@/lib/analysis-review/formatters";
import type { AnalysisReviewModel, ReviewMetricName } from "@/lib/analysis-review/schemas";
import type { CompanyMethodsView } from "@/lib/company-methods/normalize";
import type { AnalysisCategory, AnalysisMetadata, Workstation } from "@/types/analysis-context";
import { AnalysisContextEditor } from "@/components/analyses/analysis-context-editor";

import { AnalysisTimeline } from "./analysis-timeline";
import { AssessmentSection } from "./assessment-section";
import { BodyMap } from "./body-map";
import { CompanyMethodsSection } from "./company-methods-section";
import { MetricExplorer } from "./metric-explorer";
import { ReviewVideoPlayer } from "./review-video-player";
import {
  HandsSection,
  KeyMomentsSection,
  MetricCards,
  MovementSection,
  QualitySection,
  QuickSummary,
  RiskSection,
  TechnicalDetails,
} from "./review-sections";

type AnalysisReviewWorkspaceProps = {
  model: AnalysisReviewModel;
  companyMethods: CompanyMethodsView | null;
  metadata: AnalysisMetadata;
  workstations: Workstation[];
  categories: AnalysisCategory[];
  analysis: {
    id: string;
    title: string;
    description: string | null;
    createdAt: string;
    sourceFileName: string;
    sourceDurationSeconds: number | null;
    sourceWidth: number | null;
    sourceHeight: number | null;
  };
  urls: {
    overlay: string | null;
    original: string | null;
    thumbnail: string | null;
    poseJson: string | null;
    ergonomicsJson: string | null;
    riskJson: string | null;
    reportJson: string | null;
    assessmentJson: string | null;
    companyMethodsJson: string | null;
  };
};

export function AnalysisReviewWorkspace({ model, companyMethods, metadata, workstations, categories, analysis, urls }: AnalysisReviewWorkspaceProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const lastUpdateRef = useRef(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(model.durationSeconds ?? analysis.sourceDurationSeconds ?? 0);
  const [selectedMetric, setSelectedMetric] = useState<ReviewMetricName>("trunk_inclination_deg");
  const metrics = useMemo(() => Object.values(model.metrics), [model.metrics]);
  const effectiveDuration = videoDuration > 0 ? videoDuration : model.durationSeconds ?? 1;

  const seekTo = useCallback((time: number) => {
    const selected = Math.max(0, Math.min(effectiveDuration, time));
    if (videoRef.current) videoRef.current.currentTime = selected;
    setCurrentTime(selected);
    document.getElementById("analysis-video")?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
  }, [effectiveDuration]);

  const handleTimeUpdate = useCallback((time: number, duration: number) => {
    const now = performance.now();
    if (now - lastUpdateRef.current >= 150 || time === 0) {
      setCurrentTime(time);
      lastUpdateRef.current = now;
    }
    if (Number.isFinite(duration) && duration > 0) setVideoDuration(duration);
  }, []);

  return (
    <main className="ui-page relative px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_12%_10%,rgba(249,115,22,.06),transparent_30%)]" />
      <div className="relative mx-auto max-w-[1540px] space-y-5 sm:space-y-6">
        <header className="ui-surface p-5 backdrop-blur-xl sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div className="min-w-0">
              <Link href="/panel/analizy" className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground transition hover:text-foreground"><ArrowLeft className="size-4" />Historia analiz</Link>
              <div className="mt-5 flex items-center gap-3"><span className="flex size-11 items-center justify-center rounded-2xl border border-emerald-300/20 bg-emerald-300/10"><Activity className="size-6 text-emerald-300" /></span><div><p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.17em] text-emerald-300"><CheckCircle2 className="size-4" />Analiza gotowa</p><p className="mt-1 text-xs text-slate-500">{formatDate(analysis.createdAt)}</p></div></div>
              <h1 className="mt-5 max-w-4xl text-3xl font-bold tracking-[-0.035em] sm:text-4xl lg:text-5xl">{analysis.title}</h1>
              {analysis.description && <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{analysis.description}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href={`/panel/analizy/${analysis.id}/raport`} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-200"><FileText className="size-4" />Raport</Link>
              {urls.reportJson && <a href={urls.reportJson} download className="ui-button-secondary text-sm"><Download className="size-4" />Pobierz dane</a>}
            </div>
          </div>
          <dl className="mt-6 flex flex-wrap gap-x-6 gap-y-3 border-t border-white/[0.08] pt-5 text-xs text-slate-500">
            <div className="flex gap-2"><dt>Film:</dt><dd className="font-medium text-slate-300">{analysis.sourceFileName}</dd></div>
            <div className="flex gap-2"><dt>Czas:</dt><dd className="font-medium text-slate-300">{formatDuration(analysis.sourceDurationSeconds)}</dd></div>
            {analysis.sourceWidth && analysis.sourceHeight && <div className="flex gap-2"><dt>Rozdzielczość:</dt><dd className="font-medium text-slate-300">{analysis.sourceWidth} × {analysis.sourceHeight}</dd></div>}
            <div className="flex gap-2"><dt>Ryzyko:</dt><dd className="font-medium text-slate-300">{riskLabel(model.risk.level)}</dd></div>
          </dl>
        </header>
        <AnalysisContextEditor analysisId={analysis.id} metadata={metadata} workstations={workstations} categories={categories} />

        <section className="review-panel" aria-labelledby="top-findings-title">
          <p className="review-eyebrow">Priorytety analizy</p>
          <h2 id="top-findings-title" className="mt-2 text-xl font-semibold">Najważniejsze wnioski</h2>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {model.keyMoments.slice(0, 3).map((moment) => (
              <button key={moment.id} type="button" onClick={() => seekTo(moment.time)} className="rounded-xl border border-border bg-surface-muted p-4 text-left transition hover:border-orange-200 hover:bg-brand-soft">
                <span className="text-xs font-semibold text-accent-foreground">{formatDuration(moment.time)}</span>
                <span className="mt-2 block font-semibold text-slate-100">{moment.title}</span>
                <span className="mt-2 block text-sm leading-6 text-slate-400">{moment.description}</span>
              </button>
            ))}
            {model.keyMoments.length === 0 && <p className="text-sm text-slate-500">Brak wiarygodnych momentów wymagających wyróżnienia.</p>}
          </div>
        </section>

        <div id="analysis-video" className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
          <ReviewVideoPlayer videoRef={videoRef} overlayUrl={urls.overlay} originalUrl={urls.original} posterUrl={urls.thumbnail} fileName={analysis.sourceFileName} currentTime={currentTime} duration={effectiveDuration} keyMoments={model.keyMoments} onTimeUpdate={handleTimeUpdate} onSeek={seekTo} />
          <div className="xl:sticky xl:top-5 xl:self-start"><QuickSummary model={model} /></div>
        </div>

        <AnalysisTimeline segments={model.timeline} duration={effectiveDuration} currentTime={currentTime} onSeek={seekTo} />
        <div className="grid min-w-0 gap-5 lg:grid-cols-[20rem_minmax(0,1fr)]">
          <BodyMap selected={selectedMetric} onSelect={setSelectedMetric} />
          <MetricExplorer metrics={model.metrics} selected={selectedMetric} currentTime={currentTime} duration={effectiveDuration} onSelect={setSelectedMetric} onSeek={seekTo} />
        </div>
        <MetricCards metrics={metrics} onSelect={(metric) => { setSelectedMetric(metric); document.getElementById("metric-explorer-title")?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" }); }} />
        <HandsSection model={model} onSeek={seekTo} />
        <MovementSection model={model} />
        <KeyMomentsSection model={model} onSeek={seekTo} />
        <QualitySection model={model} />
        <RiskSection model={model} />
        <AssessmentSection assessment={model.assessment} onSeek={seekTo} />
        <CompanyMethodsSection analysisId={analysis.id} value={companyMethods} onSeek={seekTo} />
        <TechnicalDetails model={model} />

        <section className="review-panel flex flex-wrap items-center justify-between gap-4">
          <div><p className="review-eyebrow"><Video className="size-4" /> Pełny raport</p><h2 className="mt-2 text-xl font-semibold">Uporządkowane podsumowanie do druku</h2></div>
          <Link href={`/panel/analizy/${analysis.id}/raport`} className="ui-button-secondary text-sm hover:border-orange-200 hover:bg-brand-soft"><FileText className="size-4" />Otwórz raport</Link>
        </section>
      </div>
    </main>
  );
}

function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? "Data niedostępna" : new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium", timeStyle: "short" }).format(date); }
function riskLabel(level: AnalysisReviewModel["risk"]["level"]) { return ({ low: "niskie", moderate: "umiarkowane", high: "wysokie", critical: "krytyczne", insufficient_data: "niewystarczające dane" } as const)[level ?? "insufficient_data"]; }
function reducedMotion() { return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
