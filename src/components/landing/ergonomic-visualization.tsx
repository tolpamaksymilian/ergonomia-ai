"use client";

import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { useSyncExternalStore } from "react";

import { ModelFallback } from "@/components/landing/model-fallback";
import type {
  AnalysisFocusMode,
  AnalysisRegionId,
} from "@/config/analysis-visualization";
import { getCurrentTheme, subscribeToTheme, type AppTheme } from "@/lib/theme";

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
  activeRegion,
  onRegionHover,
  onRegionSelect,
}: {
  focusMode: AnalysisFocusMode;
  activeRegion: AnalysisRegionId;
  onRegionHover: (region: AnalysisRegionId | null) => void;
  onRegionSelect: (region: AnalysisRegionId) => void;
}) {
  const shouldReduceMotion = useReducedMotion();
  const theme = useSyncExternalStore(subscribeToTheme, getCurrentTheme, (): AppTheme => "light");

  return (
    <div className="relative overflow-hidden bg-[radial-gradient(circle_at_50%_42%,rgba(249,115,22,0.07),transparent_58%)] dark:bg-[radial-gradient(circle_at_50%_42%,rgba(249,115,22,0.08),transparent_58%)]">
      <DynamicErgonomicSkeleton
        activeRegion={activeRegion}
        focusMode={focusMode}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        reducedMotion={Boolean(shouldReduceMotion)}
        theme={theme}
      />
    </div>
  );
}
