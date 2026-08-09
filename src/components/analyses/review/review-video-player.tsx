"use client";

import { Pause, Play, RotateCcw, SkipBack, SkipForward } from "lucide-react";
import type { RefObject } from "react";
import { useEffect, useState } from "react";

import { formatTimestamp } from "@/lib/analysis-review/formatters";
import type { KeyMoment } from "@/lib/analysis-review/schemas";

type ReviewVideoPlayerProps = {
  videoRef: RefObject<HTMLVideoElement | null>;
  overlayUrl: string | null;
  originalUrl: string | null;
  posterUrl: string | null;
  fileName: string;
  currentTime: number;
  duration: number;
  keyMoments: KeyMoment[];
  onTimeUpdate: (time: number, duration: number) => void;
  onSeek: (time: number) => void;
};

export function ReviewVideoPlayer({
  videoRef,
  overlayUrl,
  originalUrl,
  posterUrl,
  fileName,
  currentTime,
  duration,
  keyMoments,
  onTimeUpdate,
  onSeek,
}: ReviewVideoPlayerProps) {
  const [source, setSource] = useState<"overlay" | "original">(overlayUrl ? "overlay" : "original");
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [error, setError] = useState(false);
  const activeUrl = source === "overlay" ? overlayUrl : originalUrl;

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !activeUrl) return;
    const resumeAt = currentTime;
    const wasPlaying = !video.paused;
    video.load();
    const restore = () => {
      video.currentTime = Math.min(resumeAt, Number.isFinite(video.duration) ? video.duration : resumeAt);
      video.playbackRate = playbackRate;
      if (wasPlaying) void video.play();
    };
    video.addEventListener("loadedmetadata", restore, { once: true });
    return () => video.removeEventListener("loadedmetadata", restore);
  // Source changes intentionally preserve the shared player time.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeUrl]);

  function togglePlayback() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }

  function changeRate(value: number) {
    setPlaybackRate(value);
    if (videoRef.current) videoRef.current.playbackRate = value;
  }

  function adjacentMoment(direction: -1 | 1) {
    const sorted = [...keyMoments].sort((a, b) => a.time - b.time);
    const target = direction === 1
      ? sorted.find((moment) => moment.time > currentTime + 0.15)
      : [...sorted].reverse().find((moment) => moment.time < currentTime - 0.15);
    if (target) onSeek(target.time);
  }

  return (
    <section className="min-w-0 overflow-hidden rounded-[28px] border border-white/10 bg-slate-950/70 shadow-2xl shadow-black/20">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">Podgląd analizy</p>
          <p className="mt-1 truncate text-sm text-slate-400">{fileName}</p>
        </div>
        {overlayUrl && originalUrl && (
          <div className="flex rounded-xl border border-white/10 bg-black/25 p-1" aria-label="Źródło filmu">
            {(["overlay", "original"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={source === value}
                onClick={() => setSource(value)}
                className={`rounded-lg px-3 py-2 text-xs font-semibold transition focus-visible:outline-2 focus-visible:outline-cyan-200 ${source === value ? "bg-cyan-300 text-slate-950" : "text-slate-400 hover:text-white"}`}
              >
                {value === "overlay" ? "Analiza" : "Oryginał"}
              </button>
            ))}
          </div>
        )}
      </header>

      <div className="relative aspect-video bg-black">
        {activeUrl && !error ? (
          <video
            ref={videoRef}
            playsInline
            controls
            preload="metadata"
            poster={posterUrl ?? undefined}
            className="size-full object-contain"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onError={() => setError(true)}
            onLoadedMetadata={(event) => onTimeUpdate(event.currentTarget.currentTime, event.currentTarget.duration)}
            onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime, event.currentTarget.duration)}
          >
            <source src={activeUrl} />
          </video>
        ) : (
          <div className="flex size-full items-center justify-center px-6 text-center text-sm text-slate-500">
            Film podglądowy jest chwilowo niedostępny. Pozostałe dane analizy nadal można przeglądać.
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-white/[0.08] px-4 py-3 sm:px-5">
        <button type="button" onClick={togglePlayback} aria-label={playing ? "Wstrzymaj film" : "Odtwórz film"} className="review-icon-button">
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
        <button type="button" onClick={() => adjacentMoment(-1)} aria-label="Poprzedni ważny moment" className="review-icon-button">
          <SkipBack className="size-4" />
        </button>
        <button type="button" onClick={() => adjacentMoment(1)} aria-label="Następny ważny moment" className="review-icon-button">
          <SkipForward className="size-4" />
        </button>
        <button type="button" onClick={() => onSeek(0)} aria-label="Przejdź na początek" className="review-icon-button">
          <RotateCcw className="size-4" />
        </button>
        <span className="ml-1 text-xs tabular-nums text-slate-400">{formatTimestamp(currentTime)} / {formatTimestamp(duration)}</span>
        <label className="ml-auto flex items-center gap-2 text-xs text-slate-400">
          Tempo
          <select
            value={playbackRate}
            onChange={(event) => changeRate(Number(event.target.value))}
            className="rounded-lg border border-white/10 bg-slate-900 px-2 py-1.5 text-white focus-visible:outline-2 focus-visible:outline-cyan-200"
            aria-label="Prędkość odtwarzania"
          >
            {[0.5, 1, 1.5, 2].map((rate) => <option key={rate} value={rate}>{rate}×</option>)}
          </select>
        </label>
      </footer>
    </section>
  );
}
