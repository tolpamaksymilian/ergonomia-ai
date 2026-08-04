"use client";

import { useState } from "react";
import {
  Download,
  FileJson,
  ImageIcon,
  RefreshCw,
  Scissors,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

type PoseResultsPreviewProps = {
  videoUrl: string | null;
  thumbnailUrl: string | null;
  jsonUrl: string | null;

  poseModel: string | null;
  processedFrames: number | null;
  detectedFrames: number | null;
  averageConfidence: number | string | null;
  presenceRatio: number | string | null;

  activeStartSeconds: number | string | null;
  activeEndSeconds: number | string | null;
  activeDurationSeconds: number | string | null;

  trackingMethod: string | null;
  smoothingMethod: string | null;

  errorMessage?: string | null;
  expiresInMinutes?: number;
};

export function PoseResultsPreview({
  videoUrl,
  thumbnailUrl,
  jsonUrl,
  poseModel,
  processedFrames,
  detectedFrames,
  averageConfidence,
  presenceRatio,
  activeStartSeconds,
  activeEndSeconds,
  activeDurationSeconds,
  trackingMethod,
  smoothingMethod,
  errorMessage,
  expiresInMinutes = 10,
}: PoseResultsPreviewProps) {
  const [activeVideoUrl] = useState<string | null>(() => videoUrl);
  const [activeThumbnailUrl] = useState<string | null>(
    () => thumbnailUrl,
  );
  const [activeJsonUrl] = useState<string | null>(() => jsonUrl);

  const [playbackError, setPlaybackError] = useState(false);

  const confidencePercent = formatPercent(averageConfidence);
  const presencePercent = formatPercent(presenceRatio);

  const detectionPercent =
    processedFrames && detectedFrames !== null
      ? `${((detectedFrames / processedFrames) * 100).toFixed(1)}%`
      : "Brak danych";

  const activeRange = formatActiveRange(
    activeStartSeconds,
    activeEndSeconds,
  );

  const activeDuration = formatDuration(activeDurationSeconds);

  function refreshAccess() {
    window.location.reload();
  }

  return (
    <section className="overflow-hidden rounded-[30px] border border-emerald-400/15 bg-white/[0.035]">
      <header className="flex flex-wrap items-center justify-between gap-5 border-b border-white/10 px-6 py-6 sm:px-8">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.19em] text-emerald-300">
            <ShieldCheck className="size-4" />
            Wynik Pose Pipeline V3.0
          </div>

          <h2 className="mt-3 text-2xl font-semibold text-white">
            Wykryty szkielet pracownika
          </h2>

          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            Film wynikowy zawiera aktywny fragment z głównym pracownikiem.
            Punkty ciała są stabilizowane, a dłonie przechodzą osobną walidację.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-2 text-xs font-semibold text-emerald-200">
          <Scissors className="size-4" />
          Automatycznie przycięty
        </div>
      </header>

      <div className="grid gap-3 border-b border-white/10 p-6 sm:grid-cols-2 sm:p-8 lg:grid-cols-4 xl:grid-cols-8">
        <Metric label="Model" value={poseModel || "RTMW Wholebody"} />
        <Metric label="Aktywny zakres" value={activeRange} />
        <Metric label="Długość wyniku" value={activeDuration} />
        <Metric
          label="Klatki modelu"
          value={processedFrames?.toLocaleString("pl-PL") ?? "Brak danych"}
        />
        <Metric label="Wykrycie osoby" value={detectionPercent} />
        <Metric label="Pokrycie obecności" value={presencePercent} />
        <Metric label="Średnia pewność" value={confidencePercent} />
        <Metric
          label="Stabilizacja"
          value={smoothingMethod ? "One Euro" : "Brak danych"}
          title={smoothingMethod ?? undefined}
        />
      </div>

      {errorMessage ? (
        <ResultError message={errorMessage} onRefresh={refreshAccess} />
      ) : (
        <div className="p-6 sm:p-8">
          {activeVideoUrl && !playbackError ? (
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-black">
              <video
                controls
                playsInline
                preload="metadata"
                poster={activeThumbnailUrl ?? undefined}
                onError={() => setPlaybackError(true)}
                className="aspect-video max-h-[720px] w-full bg-black object-contain"
              >
                <source src={activeVideoUrl} type="video/mp4" />
                Twoja przeglądarka nie obsługuje odtwarzania tego filmu.
              </video>
            </div>
          ) : activeThumbnailUrl ? (
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-black">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={activeThumbnailUrl}
                alt="Klatka z wykrytym szkieletem pracownika"
                className="max-h-[720px] w-full object-contain"
              />
            </div>
          ) : (
            <ResultError
              message="Nie udało się pobrać podglądu wyników."
              onRefresh={refreshAccess}
            />
          )}

          {playbackError && (
            <div className="mt-4 rounded-2xl border border-amber-300/20 bg-amber-400/[0.06] px-4 py-3 text-sm leading-6 text-amber-100/80">
              Przeglądarka nie mogła odtworzyć filmu wynikowego. Miniatura i dane
              JSON pozostają dostępne.
            </div>
          )}

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            <TechnicalInfo
              label="Tracking głównej osoby"
              value={trackingMethod || "Brak danych"}
            />
            <TechnicalInfo
              label="Wygładzanie punktów"
              value={smoothingMethod || "Brak danych"}
            />
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
            <p className="max-w-xl text-xs leading-5 text-slate-500">
              Adresy dostępu wygasają po około {expiresInMinutes} minutach.
              Odśwież stronę, aby wygenerować nowe.
            </p>

            <div className="flex flex-wrap gap-3">
              {activeThumbnailUrl && (
                <a
                  href={activeThumbnailUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-white transition hover:border-cyan-400/30 hover:bg-cyan-400/10"
                >
                  <ImageIcon className="size-4 text-cyan-300" />
                  Otwórz miniaturę
                </a>
              )}

              {activeJsonUrl && (
                <a
                  href={activeJsonUrl}
                  target="_blank"
                  rel="noreferrer"
                  download
                  className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-white transition hover:border-cyan-400/30 hover:bg-cyan-400/10"
                >
                  <FileJson className="size-4 text-cyan-300" />
                  Pobierz punkty JSON
                </a>
              )}

              {activeVideoUrl && (
                <a
                  href={activeVideoUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                >
                  <Download className="size-4" />
                  Otwórz film wynikowy
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4">
      <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
        {label}
      </p>
      <p className="mt-2 truncate text-sm font-semibold text-white" title={title}>
        {value}
      </p>
    </div>
  );
}

function TechnicalInfo({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-slate-950/30 px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.15em] text-slate-600">
        {label}
      </p>
      <p className="mt-2 break-all text-xs leading-5 text-slate-300">{value}</p>
    </div>
  );
}

function ResultError({
  message,
  onRefresh,
}: {
  message: string;
  onRefresh: () => void;
}) {
  return (
    <div className="p-6 sm:p-8">
      <div className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl border border-dashed border-amber-300/20 bg-amber-400/[0.045] px-6 text-center">
        <TriangleAlert className="size-8 text-amber-300" />
        <p className="mt-5 max-w-xl text-sm leading-6 text-slate-400">
          {message}
        </p>
        <button
          type="button"
          onClick={onRefresh}
          className="mt-6 inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-5 py-3 font-semibold text-white transition hover:bg-white/[0.09]"
        >
          <RefreshCw className="size-5" />
          Odśwież dostęp
        </button>
      </div>
    </div>
  );
}

function formatPercent(value: number | string | null) {
  if (value === null) {
    return "Brak danych";
  }

  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    return "Brak danych";
  }

  return `${(numericValue * 100).toFixed(1)}%`;
}

function formatDuration(value: number | string | null) {
  if (value === null) {
    return "Brak danych";
  }

  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    return "Brak danych";
  }

  return `${numericValue.toFixed(2)} s`;
}

function formatActiveRange(
  startValue: number | string | null,
  endValue: number | string | null,
) {
  const start = Number(startValue);
  const end = Number(endValue);

  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return "Brak danych";
  }

  return `${start.toFixed(2)}–${end.toFixed(2)} s`;
}
