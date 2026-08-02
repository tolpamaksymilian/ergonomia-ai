"use client";

import Link from "next/link";
import { motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Cpu,
  Crosshair,
  Gauge,
  ScanLine,
  Sparkles,
} from "lucide-react";

import { ErgonomicSkeleton } from "@/components/three/ergonomic-skeleton";

export function HeroSection() {
  return (
    <section className="relative overflow-hidden px-5 pb-24 pt-32 sm:px-6 sm:pt-36">
      <BackgroundEffects />

      <div className="relative mx-auto grid min-h-[760px] max-w-7xl items-center gap-14 lg:grid-cols-[0.95fr_1.05fr] xl:gap-20">
        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.75,
            ease: "easeOut",
          }}
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200">
            <Sparkles className="size-4" />
            Inteligentna analiza ergonomii
          </div>

          <h1 className="mt-8 max-w-4xl text-5xl font-bold leading-[1.03] tracking-[-0.045em] text-white sm:text-6xl xl:text-7xl">
            Zobacz ryzyko, zanim stanie się{" "}
            <span className="bg-gradient-to-r from-emerald-300 via-cyan-200 to-sky-300 bg-clip-text text-transparent">
              problemem.
            </span>
          </h1>

          <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300">
            Analiza nagrań stanowisk pracy, automatyczne
            wykrywanie sylwetki, pomiar kątów i czasu
            utrzymywania niekorzystnych pozycji oraz
            konfigurowalna ocena ryzyka ergonomicznego.
          </p>

          <div className="mt-9 flex flex-wrap gap-4">
            <Link
              href="/o-projekcie"
              className="group flex items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3.5 font-semibold text-slate-950 shadow-xl shadow-emerald-500/20 transition hover:-translate-y-0.5 hover:bg-emerald-300"
            >
              Poznaj projekt

              <ArrowRight className="size-5 transition group-hover:translate-x-1" />
            </Link>

            <Link
              href="/test-bazy"
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-6 py-3.5 font-semibold text-white backdrop-blur transition hover:border-white/20 hover:bg-white/[0.08]"
            >
              <ScanLine className="size-5 text-cyan-300" />
              Status systemu
            </Link>
          </div>

          <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-slate-400">
            {[
              "Analiza wideo",
              "Edytowalne reguły",
              "REBA i RULA",
            ].map((item) => (
              <span key={item} className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-emerald-400" />
                {item}
              </span>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{
            opacity: 0,
            scale: 0.96,
            y: 28,
          }}
          animate={{
            opacity: 1,
            scale: 1,
            y: 0,
          }}
          transition={{
            duration: 0.9,
            delay: 0.15,
            ease: "easeOut",
          }}
          className="relative"
        >
          <div className="absolute inset-10 rounded-full bg-emerald-400/10 blur-[110px]" />

          <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-[#07111f]/90 shadow-[0_30px_100px_rgba(0,0,0,0.5)] backdrop-blur-xl">
            <PreviewHeader />

            <div className="relative overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(8,145,178,0.12),transparent_62%)]" />

              <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-cyan-300/60 to-transparent" />

              <CornerMarkers />

              <ErgonomicSkeleton />

              <AngleBadge
                className="left-[8%] top-[25%]"
                label="Kark"
                value="18°"
                color="emerald"
              />

              <AngleBadge
                className="left-[7%] top-[49%]"
                label="Tułów"
                value="12°"
                color="cyan"
              />

              <AngleBadge
                className="right-[7%] top-[37%]"
                label="Łokieć"
                value="96°"
                color="amber"
              />

              <RiskCard />

              <motion.div
                className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300 to-transparent shadow-[0_0_20px_rgba(34,211,238,0.8)]"
                animate={{
                  y: [35, 430, 35],
                  opacity: [0.2, 0.9, 0.2],
                }}
                transition={{
                  duration: 6,
                  repeat: Infinity,
                  ease: "linear",
                }}
              />
            </div>

            <div className="grid gap-3 border-t border-white/10 bg-slate-950/45 p-4 sm:grid-cols-4 sm:p-5">
              <Metric
                icon={Crosshair}
                label="Pewność"
                value="96,8%"
              />

              <Metric
                icon={Gauge}
                label="REBA"
                value="7"
                variant="warning"
              />

              <Metric
                icon={Clock3}
                label="Klatka"
                value="01:24"
              />

              <Metric
                icon={Cpu}
                label="Model"
                value="RTMW"
              />
            </div>
          </div>

          <div className="pointer-events-none absolute -bottom-5 left-10 right-10 h-12 rounded-full bg-emerald-400/10 blur-3xl" />
        </motion.div>
      </div>
    </section>
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

function PreviewHeader() {
  return (
    <div className="relative z-20 flex items-center justify-between border-b border-white/10 bg-slate-950/35 px-5 py-4">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10">
          <Activity className="size-5 text-cyan-300" />
        </div>

        <div>
          <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-slate-500">
            Podgląd analizy
          </p>

          <p className="mt-1 text-sm font-semibold text-white">
            Digital posture detection
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-semibold text-emerald-200">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
        </span>

        Analiza aktywna
      </div>
    </div>
  );
}

function RiskCard() {
  return (
    <div className="absolute right-5 top-5 z-20 hidden w-[155px] rounded-2xl border border-amber-300/15 bg-slate-950/80 p-4 shadow-2xl shadow-black/30 backdrop-blur-xl sm:block">
      <p className="text-[10px] uppercase tracking-[0.17em] text-slate-500">
        Poziom ryzyka
      </p>

      <p className="mt-2 text-lg font-bold text-amber-300">
        Podwyższony
      </p>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full w-[67%] rounded-full bg-gradient-to-r from-yellow-300 to-amber-500" />
      </div>

      <p className="mt-2 text-[10px] text-slate-500">
        Wynik REBA: 7
      </p>
    </div>
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
      <span
        className={`${common} left-5 top-5 border-l border-t`}
      />

      <span
        className={`${common} right-5 top-5 border-r border-t`}
      />

      <span
        className={`${common} bottom-5 left-5 border-b border-l`}
      />

      <span
        className={`${common} bottom-5 right-5 border-b border-r`}
      />
    </>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  variant = "default",
}: {
  icon: typeof Gauge;
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
            variant === "warning"
              ? "text-amber-300"
              : "text-white"
          }`}
        >
          {value}
        </p>
      </div>
    </div>
  );
}