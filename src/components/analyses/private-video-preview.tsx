"use client";

import { useRef, useState } from "react";
import {
  ExternalLink,
  FileVideo,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

type PrivateVideoPreviewProps = {
  signedUrl: string | null;
  fileName: string;
  mimeType: string;
  errorMessage?: string | null;
  expiresInMinutes?: number;
};

export function PrivateVideoPreview({
  signedUrl,
  fileName,
  mimeType,
  errorMessage,
  expiresInMinutes = 10,
}: PrivateVideoPreviewProps) {
  /*
   * Zachowujemy pierwszy signed URL przez cały czas życia
   * komponentu. Odświeżanie statusu analizy nie podmieni
   * źródła aktualnie odtwarzanego filmu.
   */
  const activeSignedUrlRef = useRef<string | null>(
    signedUrl,
  );

  const activeSignedUrl =
    activeSignedUrlRef.current;

  const [playbackError, setPlaybackError] =
    useState(false);

  const hasError =
    Boolean(errorMessage) ||
    !activeSignedUrl ||
    playbackError;

  function handleRefreshAccess() {
    /*
     * Pełne odświeżenie strony pobierze nowy signed URL
     * ważny przez kolejne kilka minut.
     */
    window.location.reload();
  }

  return (
    <section className="overflow-hidden rounded-[30px] border border-white/10 bg-white/[0.035]">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-6 py-5 sm:px-7">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
            <FileVideo className="size-6 text-cyan-300" />
          </div>

          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Prywatny film źródłowy
            </p>

            <h2 className="mt-1 truncate text-xl font-semibold text-white">
              {fileName}
            </h2>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.07] px-3 py-1.5 text-xs font-semibold text-emerald-200">
          <ShieldCheck className="size-4" />
          Dostęp czasowy
        </div>
      </header>

      {hasError ? (
        <div className="p-6 sm:p-8">
          <div className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl border border-dashed border-amber-300/20 bg-amber-400/[0.045] px-6 text-center">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-amber-400/10">
              <TriangleAlert className="size-7 text-amber-300" />
            </div>

            <h3 className="mt-5 text-xl font-semibold text-white">
              Podgląd filmu jest chwilowo niedostępny
            </h3>

            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
              {errorMessage ||
                "Adres dostępu mógł wygasnąć albo przeglądarka nie mogła odtworzyć tego formatu filmu."}
            </p>

            <button
              type="button"
              onClick={handleRefreshAccess}
              className="mt-6 inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-5 py-3 font-semibold text-white transition hover:border-cyan-400/30 hover:bg-cyan-400/10 hover:text-cyan-200"
            >
              <RefreshCw className="size-5" />
              Odśwież dostęp
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="relative bg-black">
            <video
              controls
              playsInline
              preload="metadata"
              onLoadedData={() =>
                setPlaybackError(false)
              }
              onError={() =>
                setPlaybackError(true)
              }
              className="aspect-video max-h-[680px] w-full bg-black object-contain"
            >
              <source
                src={activeSignedUrl}
                type={mimeType}
              />

              Twoja przeglądarka nie obsługuje odtwarzania tego filmu.
            </video>

            <div className="pointer-events-none absolute left-4 top-4 rounded-xl border border-white/10 bg-slate-950/75 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300 backdrop-blur-xl">
              Materiał źródłowy
            </div>
          </div>

          <footer className="flex flex-wrap items-center justify-between gap-4 border-t border-white/10 px-6 py-4 sm:px-7">
            <p className="text-xs leading-5 text-slate-500">
              Adres podglądu jest ważny przez około{" "}
              {expiresInMinutes} minut. Odśwież stronę,
              aby wygenerować nowy.
            </p>

            <a
              href={activeSignedUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold text-white transition hover:border-cyan-400/30 hover:bg-cyan-400/10 hover:text-cyan-200"
            >
              <ExternalLink className="size-4" />
              Otwórz film
            </a>
          </footer>
        </>
      )}
    </section>
  );
}