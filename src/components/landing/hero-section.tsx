"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  Check,
  CircleDot,
  Crosshair,
  FileCheck2,
  Hand,
  Info,
  ListChecks,
  ScanSearch,
} from "lucide-react";

import { ErgonomicVisualization } from "@/components/landing/ergonomic-visualization";
import {
  analysisRegions,
  getAnalysisRegion,
  type AnalysisFocusMode,
  type AnalysisRegionId,
} from "@/config/analysis-visualization";
import { POSE_PIPELINE_VERSION } from "@/config/project-status";

const focusModes: Array<{
  id: AnalysisFocusMode;
  label: string;
  icon: typeof ScanSearch;
}> = [
  {
    id: "full",
    label: "Cała sylwetka",
    icon: ScanSearch,
  },
  {
    id: "upper",
    label: "Górna część ciała",
    icon: CircleDot,
  },
  {
    id: "arm",
    label: "Prawe ramię",
    icon: Hand,
  },
];

export function HeroSection({
  isAuthenticated,
}: {
  isAuthenticated: boolean;
}) {
  const [focusMode, setFocusMode] = useState<AnalysisFocusMode>("full");
  const [selectedRegion, setSelectedRegion] =
    useState<AnalysisRegionId>("trunk");
  const [hoveredRegion, setHoveredRegion] =
    useState<AnalysisRegionId | null>(null);
  const activeRegion = hoveredRegion ?? selectedRegion;
  return (
    <section className="relative overflow-hidden px-5 pb-16 pt-28 sm:px-6 sm:pb-20 sm:pt-36">
      <BackgroundEffects />

      <div className="relative mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.86fr_1.14fr] lg:items-center xl:gap-16">
        <div>
          <h1 className="max-w-4xl text-4xl font-bold leading-[1.03] tracking-[-0.045em] text-foreground min-[420px]:text-5xl sm:text-6xl">
            Sprawdź ergonomię pracy na podstawie{" "}
            <span className="text-primary">
              filmu
            </span>
          </h1>

          <p className="mt-7 max-w-2xl text-lg leading-8 text-muted-foreground">
            System analizuje ruch, oblicza metryki postawy i przygotowuje czytelny raport.
          </p>

          <div className="mt-9 flex flex-wrap gap-4">
            <Link
              href={
                isAuthenticated
                  ? "/panel/analizy/nowa"
                  : "/logowanie"
              }
              className="ui-button-primary group px-6 py-3.5 motion-reduce:transition-none"
            >
              Rozpocznij analizę
              <ArrowRight className="size-5 transition group-hover:translate-x-1" />
            </Link>

            <Link
              href="#jak-to-dziala"
              className="ui-button-secondary px-6 py-3.5 backdrop-blur motion-reduce:transition-none"
            >
              <ScanSearch className="size-5 text-primary" />
              Zobacz, jak to działa
            </Link>
          </div>
        </div>

        <div className="relative">
          <div className="absolute inset-10 rounded-full bg-primary/10 blur-[120px]" />

          <div className="relative overflow-hidden rounded-2xl border border-border bg-card shadow-[0_10px_35px_rgba(0,0,0,0.08)] backdrop-blur-xl sm:rounded-3xl dark:shadow-[0_24px_70px_rgba(0,0,0,0.35)]">
            <PreviewHeader />

            <div className="border-b border-border bg-surface-muted px-4 py-4 sm:px-5">
              <div className="grid grid-cols-3 gap-2 sm:flex sm:flex-wrap sm:gap-3">
                {focusModes.map((mode) => {
                  const Icon = mode.icon;
                  const active = focusMode === mode.id;

                  return (
                    <button
                      key={mode.id}
                      type="button"
                      onClick={() => setFocusMode(mode.id)}
                      aria-pressed={active}
                      className={`flex min-w-0 items-center justify-center gap-1.5 rounded-lg border px-2 py-2.5 text-[11px] font-semibold transition sm:gap-2 sm:px-4 sm:text-sm motion-reduce:transition-none ${
                        active
                          ? "border-primary/40 bg-brand-soft text-accent-foreground"
                          : "border-border bg-surface text-muted-foreground hover:border-orange-200 hover:bg-brand-soft hover:text-foreground"
                      }`}
                    >
                      <Icon className="size-4" />
                      <span className="min-w-0 leading-tight sm:leading-normal">{mode.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="relative overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(249,115,22,0.06),transparent_62%)]" />

              <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />

              <CornerMarkers />

              <ErgonomicVisualization
                activeRegion={activeRegion}
                focusMode={focusMode}
                onRegionHover={setHoveredRegion}
                onRegionSelect={setSelectedRegion}
              />

              <AnalysisRegionControls
                activeRegion={activeRegion}
                onRegionSelect={(region) => {
                  setHoveredRegion(null);
                  setSelectedRegion(region);
                }}
                selectedRegion={selectedRegion}
              />
            </div>

            <div className="grid grid-cols-2 gap-3 border-t border-border bg-surface-muted p-4 sm:grid-cols-4 sm:p-5">
              <Metric
                icon={Crosshair}
                label="Analiza"
                value="Sylwetka i ruch"
              />

              <Metric
                icon={ListChecks}
                label="Metryki"
                value="14 pomiarów"
              />

              <Metric
                icon={Hand}
                label="Dłonie"
                value="Walidowane"
              />

              <Metric
                icon={FileCheck2}
                label="Wynik"
                value="Raport"
              />
            </div>
          </div>

          <div className="pointer-events-none absolute -bottom-5 left-10 right-10 h-12 rounded-full bg-primary/10 blur-3xl" />
        </div>
      </div>
    </section>
  );
}

function PreviewHeader() {
  return (
    <div className="relative z-20 flex items-center justify-between border-b border-border bg-card px-5 py-4">
      <div>
        <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-slate-500">
          Podgląd analizy
        </p>

        <p className="mt-1 text-sm font-semibold text-foreground">
          Techniczny podgląd danych pozy
        </p>
      </div>

      <div className="flex items-center gap-2 rounded-full border border-orange-200 bg-brand-soft px-3 py-1.5 text-xs font-semibold text-accent-foreground dark:border-orange-800">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
        </span>
        {POSE_PIPELINE_VERSION}
      </div>
    </div>
  );
}

function CornerMarkers() {
  const common =
    "pointer-events-none absolute z-10 size-8 border-primary/30";

  return (
    <>
      <span className={`${common} left-5 top-5 border-l border-t`} />
      <span className={`${common} right-5 top-5 border-r border-t`} />
      <span className={`${common} bottom-5 left-5 border-b border-l`} />
      <span className={`${common} bottom-5 right-5 border-b border-r`} />
    </>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  variant = "default",
}: {
  icon: typeof Crosshair;
  label: string;
  value: string;
  variant?: "default" | "warning";
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-3 py-3">
      <div
        className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${
          variant === "warning"
            ? "bg-amber-400/10 text-amber-300"
            : "bg-brand-soft text-accent-foreground"
        }`}
      >
        <Icon className="size-4" />
      </div>

      <div className="min-w-0">
        <p className="truncate text-[9px] uppercase tracking-[0.14em] text-slate-500">
          {label}
        </p>

        <p
          className={`mt-0.5 truncate text-sm font-bold ${
            variant === "warning" ? "text-amber-700 dark:text-amber-300" : "text-foreground"
          }`}
        >
          {value}
        </p>
      </div>
    </div>
  );
}

function BackgroundEffects() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute left-[-12%] top-[-22%] size-[640px] rounded-full bg-orange-200/25 blur-[150px] dark:bg-orange-950/15" />
      <div className="absolute bottom-[-30%] right-[-12%] size-[680px] rounded-full bg-neutral-200/35 blur-[160px] dark:bg-neutral-900/30" />

      <div
        className="absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.8) 1px, transparent 1px)",
          backgroundSize: "54px 54px",
          maskImage:
            "linear-gradient(to bottom, black, transparent 90%)",
        }}
      />
    </div>
  );
}

function AnalysisRegionControls({
  activeRegion,
  selectedRegion,
  onRegionSelect,
}: {
  activeRegion: AnalysisRegionId;
  selectedRegion: AnalysisRegionId;
  onRegionSelect: (region: AnalysisRegionId) => void;
}) {
  const region = getAnalysisRegion(activeRegion);

  return (
    <div className="relative z-20 grid gap-4 border-t border-border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_290px] sm:p-5">
      <div
        className="min-w-0 rounded-xl border border-border bg-surface-muted p-4"
        aria-live="polite"
      >
        <div className="flex items-center gap-2 text-[9px] font-semibold uppercase tracking-[0.17em] text-accent-foreground">
          <Crosshair className="size-3.5" aria-hidden="true" />
          Analizowany obszar
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="font-semibold text-foreground">{region.label}</p>
          <p className="text-xs font-medium text-accent-foreground">
            {region.metric}
          </p>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-400">
          {region.description}
        </p>
      </div>

      <div className="min-w-0">
        <p className="mb-2 flex items-center gap-2 px-1 text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          <Info className="size-3" aria-hidden="true" />
          Wybierz strefę lub wskaż model
        </p>
        <div className="grid grid-cols-3 gap-1.5">
          {analysisRegions.map((item) => {
            const active = item.id === selectedRegion;

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onRegionSelect(item.id)}
                aria-pressed={active}
                className={`flex min-h-11 min-w-0 items-center justify-center gap-1 rounded-lg border px-2 py-2.5 text-[10px] font-semibold transition sm:text-[11px] motion-reduce:transition-none ${
                  active
                    ? "border-primary/40 bg-brand-soft text-accent-foreground"
                    : "border-border bg-surface text-muted-foreground hover:border-orange-200 hover:bg-brand-soft hover:text-foreground"
                }`}
              >
                {active && (
                  <Check className="size-3 shrink-0" aria-hidden="true" />
                )}
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
