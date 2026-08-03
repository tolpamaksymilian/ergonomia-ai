"use client";

import { useRef, useState } from "react";
import {
  Download,
  FileJson,
  ImageIcon,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

type PoseResultsPreviewProps = {
  videoUrl: string | null;
  thumbnailUrl: string | null;
  jsonUrl: string | null;

  poseModel: string | null;
  sampleStride: number | null;
  processedFrames: number | null;
  detectedFrames: number | null;
  averageConfidence: number | string | null;

  errorMessage?: string | null;
  expiresInMinutes?: number;
};

export function PoseResultsPreview({
  videoUrl,
  thumbnailUrl,
  jsonUrl,
  poseModel,
  sampleStride,
  processedFrames,
  detectedFrames,
  averageConfidence,
  errorMessage,
  expiresInMinutes = 10,
}: PoseResultsPreviewProps) {
  /*
   * Zachowujemy pierwszy zestaw signed URL.
   * Odświeżenie statusu analizy nie zresetuje filmu.
   */
  const activeVideoUrlRef =
    useRef<string | null>(videoUrl);

  const activeThumbnailUrlRef =
    useRef<string | null>(thumbnailUrl);

  const activeJsonUrlRef =
    useRef<string | null>(jsonUrl);

  const activeVideoUrl =
    activeVideoUrlRef.current;

  const activeThumbnailUrl =
    activeThumbnailUrlRef.current;

  const activeJsonUrl =
    activeJsonUrlRef.current;

  const [playbackError, setPlaybackError] =
    useState(false);

  const confidence =
    averageConfidence === null
      ? null
      : Number(averageConfidence);

  const confidencePercent =
    confidence !== null &&
    Number.isFinite(confidence)
      ? `${(confidence * 100).toFixed(1)}%`
      : "Brak danych";

  const detectionPercent =
    processedFrames &&
    detectedFrames !== null
      ? `${(
          (detectedFrames / processedFrames) *
          100
        ).toFixed(1)}%`
      : "Brak danych";

  function refreshAccess() {
    window.location.reload();
  }

  return (
    <section className="overflow-hidden rounded-[30px] border border-emerald-400/15 bg-white/[0.035]">
      <header className="flex flex-wrap items-center justify-between gap-5 border-b border-white/10 px-6 py-6 sm:px-8">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.19em] text-emerald-300">
            <ShieldCheck className="size-4" />
            Wynik RTMW Wholebody
          </div>

          <h2 className="mt-3 text-2xl font-semibold text-white">
            Wykryty szkielet pracownika
          </h2>

          <p className="mt-2 text-sm leading-6 text-slate-500">
            Wyniki zapisano w prywatnym magazynie
            i udostępniono przez czasowy adres dostępu.
          </p>
        </div>

        <div className="rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-2 text-xs font-semibold text-emerald-200">
          Etap AI ukończony
        </div>
      </header>

      <div className="grid gap-3 border-b border-white/10 p-6 sm:grid-cols-2 sm:p-8 lg:grid-cols-5">
        <Metric
          label="Model"
          value={poseModel || "RTMW Wholebody"}
        />

        <Metric
          label="Próbkowanie"
          value={
            sampleStride
              ? `Co ${sampleStride}. klatkę`
              : "Brak danych"
          }
        />

        <Metric
          label="Klatki modelu"
          value={
            processedFrames?.toLocaleString(
              "pl-PL",
            ) ?? "Brak danych"
          }
        />

        <Metric
          label="Wykrycie osoby"
          value={detectionPercent}
        />

        <Metric
          label="Średnia pewność"
          value={confidencePercent}
        />
      </div>

      {errorMessage ? (
        <ResultError
          message={errorMessage}
          onRefresh={refreshAccess}
        />
      ) : (
        <div className="p-6 sm:p-8">
          {activeVideoUrl &&
          !playbackError ? (
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-black">
              <video
                controls
                playsInline
                preload="metadata"
                poster={
                  activeThumbnailUrl ??
                  undefined
                }
                onError={() =>
                  setPlaybackError(true)
                }
                className="aspect-video max-h-[720px] w-full bg-black object-contain"
              >
                <source
                  src={activeVideoUrl}
                  type="video/mp4"
                />

                Twoja przeglądarka nie obsługuje
                odtwarzania tego filmu.
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
              Przeglądarka nie mogła odtworzyć
              filmu wynikowego. Miniatura pozostaje
              dostępna. Może być potrzebna zmiana
              kodeka filmu na H.264.
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
            <p className="max-w-xl text-xs leading-5 text-slate-500">
              Adresy dostępu wygasają po około{" "}
              {expiresInMinutes} minutach. Odśwież
              stronę, aby wygenerować nowe.
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
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4">
      <p className="text-[9px] uppercase tracking-[0.16em] text-slate-600">
        {label}
      </p>

      <p className="mt-2 truncate text-sm font-semibold text-white">
        {value}
      </p>
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