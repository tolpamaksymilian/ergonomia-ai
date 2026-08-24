"use client";

import { Layers3 } from "lucide-react";
import { useMemo, useState } from "react";

import { DEVIATION_LABELS, QUALITY_WARNING_LABELS } from "@/lib/analysis-review/config";
import { formatDuration, formatTimestamp } from "@/lib/analysis-review/formatters";
import type { TimelineSegment } from "@/lib/analysis-review/schemas";

const LAYERS = [
  ["posture", "Postawa"],
  ["hands", "Dłonie"],
  ["holding", "Chwyt"],
  ["quality", "Jakość"],
  ["events", "Zdarzenia"],
  ["assessment", "RULA / REBA"],
] as const;

type AnalysisTimelineProps = {
  segments: TimelineSegment[];
  duration: number;
  currentTime: number;
  onSeek: (time: number) => void;
};

export function AnalysisTimeline({ segments, duration, currentTime, onSeek }: AnalysisTimelineProps) {
  const [visible, setVisible] = useState<Set<TimelineSegment["layer"]>>(() => new Set(["posture", "holding", "quality", "events", "assessment"]));
  const tracks = useMemo(() => {
    const map = new Map<string, TimelineSegment[]>();
    for (const segment of segments) {
      if (!visible.has(segment.layer)) continue;
      const key = `${segment.layer}:${segment.track}`;
      map.set(key, [...(map.get(key) ?? []), segment]);
    }
    return [...map.entries()].slice(0, 18);
  }, [segments, visible]);
  const safeDuration = duration > 0 ? duration : Math.max(1, ...segments.map((item) => item.end));

  function toggleLayer(layer: TimelineSegment["layer"]) {
    setVisible((current) => {
      const next = new Set(current);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }

  function seekFromPointer(event: React.MouseEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    onSeek(((event.clientX - bounds.left) / Math.max(1, bounds.width)) * safeDuration);
  }

  return (
    <section className="review-panel min-w-0" aria-labelledby="timeline-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="review-eyebrow"><Layers3 className="size-4" /> Oś analizy</p>
          <h2 id="timeline-title" className="mt-2 text-xl font-semibold">Timeline zsynchronizowany z filmem</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Kolory postawy pokazują wyłącznie geometryczne pasma odchylenia, nie poziom ryzyka. Turkus oznacza jawną rekonstrukcję lub ciągłość wyłącznie techniczną.</p>
        </div>
        <div className="flex flex-wrap gap-2" aria-label="Widoczne warstwy osi czasu">
          {LAYERS.map(([layer, label]) => (
            <button key={layer} type="button" aria-pressed={visible.has(layer)} onClick={() => toggleLayer(layer)} className={`review-filter ${visible.has(layer) ? "review-filter-active" : ""}`}>{label}</button>
          ))}
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-950/45">
        <div className="grid grid-cols-[7.5rem_minmax(0,1fr)] sm:grid-cols-[11rem_minmax(0,1fr)]">
          <div className="border-b border-r border-white/[0.07] px-3 py-2 text-[10px] uppercase tracking-wider text-slate-600">Warstwa</div>
          <div className="relative border-b border-white/[0.07] px-3 py-2 text-[10px] tabular-nums text-slate-600">
            <span>00:00</span><span className="absolute left-1/2 -translate-x-1/2">{formatTimestamp(safeDuration / 2)}</span><span className="float-right">{formatTimestamp(safeDuration)}</span>
          </div>
          {tracks.length ? tracks.map(([key, trackSegments]) => {
            const first = trackSegments[0];
            return (
              <div key={key} className="contents">
                <div className="truncate border-b border-r border-white/[0.06] px-3 py-2 text-[11px] font-medium text-slate-400" title={first?.label}>{trackLabel(first)}</div>
                <div
                  className="relative min-h-9 cursor-crosshair border-b border-white/[0.06] bg-[linear-gradient(90deg,transparent_49.8%,rgba(255,255,255,.035)_50%,transparent_50.2%)]"
                  onClick={seekFromPointer}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowRight") onSeek(Math.min(safeDuration, currentTime + 1));
                    if (event.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 1));
                  }}
                  role="slider"
                  tabIndex={0}
                  aria-label={`Oś czasu: ${trackLabel(first)}`}
                  aria-valuemin={0}
                  aria-valuemax={safeDuration}
                  aria-valuenow={Math.min(safeDuration, currentTime)}
                >
                  {trackSegments.map((segment) => {
                    const left = Math.max(0, Math.min(100, segment.start / safeDuration * 100));
                    const width = Math.max(0.22, Math.min(100 - left, (segment.end - segment.start) / safeDuration * 100));
                    return (
                      <button
                        key={segment.id}
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onSeek(segment.start); }}
                        className={`absolute inset-y-2 rounded-sm opacity-80 transition hover:opacity-100 focus-visible:z-20 focus-visible:outline-2 focus-visible:outline-white ${segmentClass(segment)}`}
                        style={{ left: `${left}%`, width: `${width}%` }}
                        aria-label={`${segmentLabel(segment)}, ${formatTimestamp(segment.start)}–${formatTimestamp(segment.end)}`}
                        title={`${segmentLabel(segment)} · ${formatTimestamp(segment.start)}–${formatTimestamp(segment.end)} · ${formatDuration(segment.end - segment.start)}`}
                      />
                    );
                  })}
                  <span className="pointer-events-none absolute inset-y-0 z-10 w-px bg-white shadow-[0_0_8px_white]" style={{ left: `${Math.min(100, currentTime / safeDuration * 100)}%` }} />
                </div>
              </div>
            );
          }) : <p className="col-span-2 px-4 py-7 text-center text-sm text-slate-500">Brak danych dla wybranych warstw.</p>}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-slate-500">
        {(["neutral", "mild", "elevated", "strong", "unknown"] as const).map((band) => <span key={band} className="flex items-center gap-2"><i className={`size-2.5 rounded-sm ${segmentClass({ band } as TimelineSegment)}`} />{DEVIATION_LABELS[band]}</span>)}
        <span className="flex items-center gap-2"><i className="size-2.5 rounded-sm bg-cyan-500" />Rekonstrukcja jawna</span>
        <span className="flex items-center gap-2"><i className="size-2.5 rounded-sm bg-sky-700" />Tylko ciągłość timeline’u</span>
      </div>
    </section>
  );
}

function trackLabel(segment: TimelineSegment | undefined) {
  if (!segment) return "Dane";
  if (segment.layer === "posture") return segment.label;
  if (segment.layer === "holding") return `Chwyt · ${segment.label}`;
  if (segment.layer === "hands") return `Dłoń · ${segment.track === "left" ? "lewa" : "prawa"}`;
  if (segment.layer === "events") return "Kluczowe zdarzenia";
  if (segment.layer === "assessment") return "Pozycje RULA / REBA";
  return segment.track === "body" ? "Jakość sylwetki" : QUALITY_WARNING_LABELS[segment.track] ?? segment.label;
}

function segmentLabel(segment: TimelineSegment) {
  if (segment.description) return `${segment.label}: ${segment.description}`;
  if (segment.layer === "posture" && segment.band) return `${segment.label}: ${DEVIATION_LABELS[segment.band]}`;
  return QUALITY_WARNING_LABELS[segment.label] ?? segment.label;
}

function segmentClass(segment: TimelineSegment) {
  if (segment.layer === "holding") return "bg-fuchsia-400";
  if (segment.layer === "hands") return "bg-orange-500";
  if (segment.layer === "quality") return "bg-slate-400";
  if (segment.layer === "events") return "bg-neutral-500";
  if (segment.layer === "assessment") return "bg-orange-300";
  if (segment.usability === "usable_for_timeline_only") return "bg-sky-700";
  if (segment.provenance === "TEMPORALLY_RECONSTRUCTED" || segment.provenance === "FLOW_TRACKED") return "bg-cyan-500";
  return {
    neutral: "bg-lime-400",
    mild: "bg-amber-300",
    elevated: "bg-orange-400",
    strong: "bg-red-400",
    unknown: "bg-slate-500",
  }[segment.band ?? "unknown"];
}
