"use client";

import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { useState } from "react";
import { Crosshair, Info } from "lucide-react";

import { ModelFallback } from "@/components/landing/model-fallback";
import {
  analysisRegions,
  getAnalysisRegion,
  type AnalysisFocusMode,
  type AnalysisRegionId,
} from "@/config/analysis-visualization";

const DynamicErgonomicSkeleton = dynamic(
  () =>
    import("@/components/three/ergonomic-skeleton").then(
      (module) => module.ErgonomicSkeleton,
    ),
  {
    ssr: false,
    loading: () => <ModelFallback />,
  },
);

export function ErgonomicVisualization({
  focusMode,
}: {
  focusMode: AnalysisFocusMode;
}) {
  const [activeRegion, setActiveRegion] = useState<AnalysisRegionId>("trunk");
  const shouldReduceMotion = useReducedMotion();
  const region = getAnalysisRegion(activeRegion);

  return (
    <div className="relative">
      <DynamicErgonomicSkeleton
        activeRegion={activeRegion}
        focusMode={focusMode}
        onRegionChange={setActiveRegion}
        reducedMotion={Boolean(shouldReduceMotion)}
      />

      <div
        className="pointer-events-none absolute left-4 top-4 z-20 max-w-[220px] rounded-2xl border border-cyan-300/15 bg-slate-950/80 p-3 shadow-2xl backdrop-blur-xl sm:left-5 sm:top-5 sm:max-w-[245px] sm:p-4"
        aria-live="polite"
      >
        <div className="flex items-center gap-2 text-[9px] font-semibold uppercase tracking-[0.17em] text-cyan-300/75">
          <Crosshair className="size-3.5" aria-hidden="true" />
          Analizowany obszar
        </div>
        <p className="mt-2 text-sm font-semibold text-white sm:text-base">
          {region.label}
        </p>
        <p className="mt-1 text-[11px] font-medium text-emerald-200 sm:text-xs">
          {region.metric}
        </p>
        <p className="mt-2 hidden text-xs leading-5 text-slate-400 sm:block">
          {region.description}
        </p>
      </div>

      <div className="absolute inset-x-3 bottom-3 z-20 rounded-2xl border border-white/10 bg-slate-950/80 p-2.5 shadow-2xl backdrop-blur-xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:w-[276px] sm:p-3">
        <p className="mb-2 hidden items-center gap-2 px-1 text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-500 sm:flex">
          <Info className="size-3" aria-hidden="true" />
          Wybierz strefę lub wskaż model
        </p>
        <div className="grid grid-cols-3 gap-1.5">
          {analysisRegions.map((item) => {
            const active = item.id === activeRegion;

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveRegion(item.id)}
                aria-pressed={active}
                className={`min-w-0 rounded-lg border px-2 py-2 text-[10px] font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 sm:text-[11px] motion-reduce:transition-none ${
                  active
                    ? "border-cyan-300/30 bg-cyan-400/15 text-cyan-100"
                    : "border-white/[0.07] bg-white/[0.035] text-slate-400 hover:bg-white/[0.08] hover:text-slate-200"
                }`}
              >
                <span className="block truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
