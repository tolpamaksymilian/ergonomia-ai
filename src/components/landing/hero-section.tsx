"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { useState } from "react";
import {
  ArrowRight,
  BrainCircuit,
  CircleDot,
  Crosshair,
  Hand,
  ListChecks,
  LogIn,
  ScanLine,
  ScanSearch,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import {
  ErgonomicSkeleton,
  type FocusMode,
} from "@/components/three/ergonomic-skeleton";

const focusModes: Array<{
  id: FocusMode;
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
  const [focusMode, setFocusMode] = useState<FocusMode>("full");

  return (
    <section className="relative overflow-hidden px-5 pb-24 pt-32 sm:px-6 sm:pt-36">
      <BackgroundEffects />

      <div className="relative mx-auto grid min-h-[780px] max-w-7xl items-center gap-14 lg:grid-cols-[0.92fr_1.08fr] xl:gap-20">
        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.75, ease: "easeOut" }}
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200">
            <Sparkles className="size-4" />
            Analiza krótkich nagrań stanowiska pracy
          </div>

          <h1 className="mt-8 max-w-4xl text-5xl font-bold leading-[1.03] tracking-[-0.045em] text-white sm:text-6xl xl:text-7xl">
            Analiza ergonomii pracy{" "}
            <span className="bg-gradient-to-r from-emerald-300 via-cyan-200 to-sky-300 bg-clip-text text-transparent">
              wspierana przez AI
            </span>
          </h1>

          <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300">
            Prześlij krótkie nagranie stanowiska pracy. System wykryje
            pracownika, przeanalizuje ruch ciała i dłoni oraz przygotuje dane
            potrzebne do oceny obciążenia ergonomicznego.
          </p>

          <div className="mt-9 flex flex-wrap gap-4">
            <Link
              href={
                isAuthenticated
                  ? "/panel/analizy/nowa"
                  : "/logowanie"
              }
              className="group flex items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3.5 font-semibold text-slate-950 shadow-xl shadow-emerald-500/20 transition hover:-translate-y-0.5 hover:bg-emerald-300"
            >
              {isAuthenticated
                ? "Utwórz nową analizę"
                : "Zaloguj się i rozpocznij"}
              <ArrowRight className="size-5 transition group-hover:translate-x-1" />
            </Link>

            <Link
              href={isAuthenticated ? "/o-projekcie" : "/rejestracja"}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-6 py-3.5 font-semibold text-white backdrop-blur transition hover:border-white/20 hover:bg-white/[0.08]"
            >
              {isAuthenticated ? (
                <ScanLine className="size-5 text-cyan-300" />
              ) : (
                <LogIn className="size-5 text-cyan-300" />
              )}
              {isAuthenticated ? "Jak działa system" : "Utwórz konto"}
            </Link>
          </div>

          <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-slate-400">
            <span className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-emerald-400" />
              Prywatne filmy
            </span>
            <span className="flex items-center gap-2">
              <ScanSearch className="size-4 text-emerald-400" />
              Pose Pipeline V3.0
            </span>
            <span className="flex items-center gap-2">
              <ListChecks className="size-4 text-cyan-300" />
              14 metryk technicznych
            </span>
          </div>

          <div className="mt-12 grid gap-4 sm:grid-cols-2">
            <InfoCard
              icon={BrainCircuit}
              title="Działa obecnie"
              text="Wykrywanie pracownika, analiza ciała i dłoni, aktywny fragment oraz dane pozy."
            />

            <InfoCard
              icon={ShieldCheck}
              title="Rozwijany etap"
              text="Silnik metryk działa lokalnie. Końcowa ocena ryzyka i raport nie są jeszcze dostępne."
            />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 28 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{
            duration: 0.9,
            delay: 0.15,
            ease: "easeOut",
          }}
          className="relative"
        >
          <div className="absolute inset-10 rounded-full bg-emerald-400/10 blur-[120px]" />

          <div className="relative overflow-hidden rounded-[34px] border border-white/10 bg-[#07111f]/90 shadow-[0_30px_100px_rgba(0,0,0,0.55)] backdrop-blur-xl">
            <PreviewHeader />

            <div className="border-b border-white/10 px-4 py-4 sm:px-5">
              <div className="flex flex-wrap gap-3">
                {focusModes.map((mode) => {
                  const Icon = mode.icon;
                  const active = focusMode === mode.id;

                  return (
                    <button
                      key={mode.id}
                      type="button"
                      onClick={() => setFocusMode(mode.id)}
                      className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
                        active
                          ? "border border-emerald-400/25 bg-emerald-400/10 text-emerald-200 shadow-lg shadow-emerald-500/10"
                          : "border border-white/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
                      }`}
                    >
                      <Icon className="size-4" />
                      {mode.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="relative overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(8,145,178,0.12),transparent_62%)]" />

              <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-cyan-300/60 to-transparent" />

              <CornerMarkers />

              <ErgonomicSkeleton focusMode={focusMode} />

              <AngleBadge className="left-[7%] top-[18%]" label="Szyja" value="pomiar 2D" color="emerald" />

              <AngleBadge
                className="left-[7%] top-[48%]"
                label="Tułów"
                value="pomiar 2D"
                color="cyan"
              />

              <AngleBadge
                className="right-[7%] top-[34%]"
                label="Łokieć"
                value="pomiar 2D"
                color="amber"
              />

              <ZoomDetails />
            </div>

            <div className="grid gap-3 border-t border-white/10 bg-slate-950/45 p-4 sm:grid-cols-4 sm:p-5">
              <Metric
                icon={Crosshair}
                label="Punkty ciała"
                value="133"
              />

              <Metric
                icon={ListChecks}
                label="Metryki"
                value="14"
              />

              <Metric
                icon={Hand}
                label="Dłonie"
                value="Walidowane"
              />

              <Metric
                icon={BrainCircuit}
                label="Model"
                value="RTMW + YOLOX"
              />
            </div>
          </div>

          <div className="pointer-events-none absolute -bottom-5 left-10 right-10 h-12 rounded-full bg-emerald-400/10 blur-3xl" />
        </motion.div>
      </div>
    </section>
  );
}

function PreviewHeader() {
  return (
    <div className="relative z-20 flex items-center justify-between border-b border-white/10 bg-slate-950/35 px-5 py-4">
      <div>
        <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-slate-500">
          Podgląd analizy
        </p>

        <p className="mt-1 text-sm font-semibold text-white">
          Techniczny podgląd danych pozy
        </p>
      </div>

      <div className="flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-semibold text-emerald-200">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
        </span>
        Pose V3.0
      </div>
    </div>
  );
}

function ZoomDetails() {
  return (
    <>
      <div className="absolute bottom-24 left-5 z-20 hidden w-[180px] rounded-2xl border border-white/10 bg-slate-950/80 p-4 backdrop-blur-xl sm:block">
        <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">
          Zoom diagnostyczny
        </p>
        <p className="mt-2 text-sm font-semibold text-white">
          Skupienie kamery na kluczowych strefach
        </p>
        <p className="mt-2 text-xs leading-5 text-slate-400">
          Przełączaj widok między całą sylwetką, górną częścią ciała i prawym
          ramieniem.
        </p>
      </div>

      <div className="absolute bottom-24 right-5 z-20 hidden w-[180px] rounded-2xl border border-white/10 bg-slate-950/80 p-4 backdrop-blur-xl sm:block">
        <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">
          Metryki techniczne
        </p>
        <p className="mt-2 text-2xl font-bold text-cyan-300">14</p>
        <p className="mt-2 text-xs leading-5 text-slate-400">
          Surowe pomiary przygotowujące dane do przyszłej oceny ergonomicznej.
        </p>
      </div>
    </>
  );
}

function AngleBadge({
  className,
  label,
  value,
  color,
}: {
  className: string;
  label: string;
  value: string;
  color: "emerald" | "cyan" | "amber";
}) {
  const styles = {
    emerald:
      "border-emerald-300/25 bg-emerald-400/10 text-emerald-200",
    cyan:
      "border-cyan-300/25 bg-cyan-400/10 text-cyan-200",
    amber:
      "border-amber-300/25 bg-amber-400/10 text-amber-200",
  };

  return (
    <div
      className={`pointer-events-none absolute z-20 hidden rounded-xl border px-3 py-2 shadow-xl backdrop-blur-md sm:block ${className} ${styles[color]}`}
    >
      <p className="text-[9px] uppercase tracking-[0.16em] opacity-65">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-bold">{value}</p>
    </div>
  );
}

function CornerMarkers() {
  const common =
    "pointer-events-none absolute z-10 size-8 border-cyan-300/25";

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
    <div className="flex items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.035] px-3 py-3">
      <div
        className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${
          variant === "warning"
            ? "bg-amber-400/10 text-amber-300"
            : "bg-cyan-400/[0.08] text-cyan-300"
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
            variant === "warning" ? "text-amber-300" : "text-white"
          }`}
        >
          {value}
        </p>
      </div>
    </div>
  );
}

function InfoCard({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof BrainCircuit;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex size-11 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
        <Icon className="size-5 text-cyan-300" />
      </div>

      <h3 className="mt-4 text-lg font-semibold text-white">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
    </div>
  );
}

function BackgroundEffects() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute left-[-12%] top-[-22%] size-[640px] rounded-full bg-emerald-500/[0.09] blur-[150px]" />
      <div className="absolute bottom-[-30%] right-[-12%] size-[680px] rounded-full bg-cyan-500/[0.09] blur-[160px]" />

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
