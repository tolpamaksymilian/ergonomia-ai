"use client";

import Link from "next/link";
import { motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Cloud,
  Database,
  Globe2,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type SystemStatusData = {
  appName: string;
  status: string;
  version: string;
  updatedAt: string;
};

type SystemStatusViewProps = {
  data?: SystemStatusData;
  errorMessage?: string;
};

export function SystemStatusView({
  data,
  errorMessage,
}: SystemStatusViewProps) {
  const isOnline = Boolean(data && data.status === "online" && !errorMessage);

  const checks: StatusCheckProps[] = [
    {
      icon: Globe2,
      name: "Aplikacja webowa",
      description: "Publiczne wdrożenie Next.js",
      value: isOnline ? "Dostępna" : "Problem",
      healthy: isOnline,
    },
    {
      icon: Database,
      name: "Baza danych",
      description: "Supabase PostgreSQL",
      value: isOnline ? "Połączona" : "Brak połączenia",
      healthy: isOnline,
    },
    {
      icon: ShieldCheck,
      name: "Bezpieczny odczyt",
      description: "Row Level Security",
      value: isOnline ? "Aktywny" : "Niedostępny",
      healthy: isOnline,
    },
  ];

  return (
    <section className="relative overflow-hidden px-5 pb-24 pt-36 sm:px-6">
      <Background />

      <div className="relative mx-auto max-w-7xl">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="grid gap-10 lg:grid-cols-[1fr_0.68fr] lg:items-end"
        >
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/[0.08] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">
              <Activity className="size-4" />
              Status infrastruktury
            </div>

            <h1 className="mt-7 max-w-4xl text-5xl font-bold tracking-[-0.045em] text-white sm:text-6xl">
              System działa i jest{" "}
              <span className="bg-gradient-to-r from-emerald-300 to-cyan-300 bg-clip-text text-transparent">
                dostępny publicznie.
              </span>
            </h1>

            <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-400">
              Ta strona wykonuje rzeczywiste zapytanie do bazy Supabase.
              Dzięki temu potwierdza działanie aplikacji, połączenia z bazą
              oraz publicznej polityki odczytu.
            </p>
          </div>

          <div
            className={`rounded-[28px] border p-6 backdrop-blur-xl ${
              isOnline
                ? "border-emerald-400/20 bg-emerald-400/[0.07]"
                : "border-red-400/20 bg-red-400/[0.07]"
            }`}
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Stan ogólny
                </p>

                <p
                  className={`mt-2 text-2xl font-bold ${
                    isOnline ? "text-emerald-300" : "text-red-300"
                  }`}
                >
                  {isOnline ? "Wszystkie systemy działają" : "Wykryto problem"}
                </p>
              </div>

              <div
                className={`relative flex size-14 items-center justify-center rounded-2xl ${
                  isOnline
                    ? "bg-emerald-400/10 text-emerald-300"
                    : "bg-red-400/10 text-red-300"
                }`}
              >
                {isOnline ? (
                  <>
                    <span className="absolute size-5 animate-ping rounded-full bg-emerald-400/30" />
                    <CheckCircle2 className="relative size-7" />
                  </>
                ) : (
                  <TriangleAlert className="size-7" />
                )}
              </div>
            </div>
          </div>
        </motion.div>

        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {checks.map((check, index) => (
            <motion.div
              key={check.name}
              initial={{ opacity: 0, y: 22 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.55,
                delay: 0.12 + index * 0.08,
              }}
            >
              <StatusCheck {...check} />
            </motion.div>
          ))}
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
          <motion.div
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.38 }}
            className="overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.035]"
          >
            <div className="flex items-center justify-between border-b border-white/10 px-6 py-5">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  Informacje o środowisku
                </p>

                <h2 className="mt-2 text-xl font-semibold">
                  Produkcyjna instancja aplikacji
                </h2>
              </div>

              <Cloud className="size-6 text-cyan-300" />
            </div>

            <div className="grid gap-px bg-white/10 sm:grid-cols-3">
              <EnvironmentMetric
                label="Aplikacja"
                value={data?.appName ?? "Ergonomia AI"}
              />

              <EnvironmentMetric
                label="Wersja"
                value={data?.version ?? "Nieznana"}
              />

              <EnvironmentMetric
                label="Środowisko"
                value="Production"
              />
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.46 }}
            className="rounded-[28px] border border-white/10 bg-gradient-to-br from-cyan-400/[0.08] to-emerald-400/[0.04] p-6"
          >
            <div className="flex size-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
              <RefreshCw className="size-5 text-cyan-300" />
            </div>

            <p className="mt-6 text-xs uppercase tracking-[0.18em] text-slate-500">
              Ostatnia aktualizacja
            </p>

            <p className="mt-2 text-xl font-semibold text-white">
              {data?.updatedAt ?? "Brak danych"}
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-400">
              Data pochodzi bezpośrednio z rekordu zapisanego w bazie danych.
            </p>
          </motion.div>
        </div>

        {errorMessage && (
          <div className="mt-6 rounded-2xl border border-red-400/20 bg-red-400/[0.07] p-5">
            <p className="font-semibold text-red-300">
              Szczegóły błędu połączenia
            </p>

            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-sm text-red-200/80">
              {errorMessage}
            </pre>
          </div>
        )}

        <div className="mt-12 flex flex-wrap gap-4">
          <Link
            href="/"
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3 font-semibold text-white transition hover:bg-white/[0.08]"
          >
            Strona główna
          </Link>

          <Link
            href="/o-projekcie"
            className="group flex items-center gap-2 rounded-xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300"
          >
            Zobacz rozwój projektu
            <ArrowRight className="size-4 transition group-hover:translate-x-1" />
          </Link>
        </div>
      </div>
    </section>
  );
}

type StatusCheckProps = {
  icon: LucideIcon;
  name: string;
  description: string;
  value: string;
  healthy: boolean;
};

function StatusCheck({
  icon: Icon,
  name,
  description,
  value,
  healthy,
}: StatusCheckProps) {
  return (
    <article className="h-full rounded-[26px] border border-white/10 bg-white/[0.035] p-6 transition hover:-translate-y-1 hover:border-emerald-400/20 hover:bg-white/[0.05]">
      <div className="flex items-start justify-between gap-4">
        <div className="flex size-12 items-center justify-center rounded-2xl border border-white/10 bg-slate-950/50">
          <Icon className="size-6 text-cyan-300" />
        </div>

        <span
          className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${
            healthy
              ? "bg-emerald-400/10 text-emerald-300"
              : "bg-red-400/10 text-red-300"
          }`}
        >
          <span
            className={`size-2 rounded-full ${
              healthy ? "bg-emerald-400" : "bg-red-400"
            }`}
          />
          {value}
        </span>
      </div>

      <h2 className="mt-6 text-xl font-semibold">{name}</h2>

      <p className="mt-2 text-sm leading-6 text-slate-400">
        {description}
      </p>
    </article>
  );
}

function EnvironmentMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="bg-[#07111f] px-6 py-5">
      <p className="text-[10px] uppercase tracking-[0.17em] text-slate-500">
        {label}
      </p>

      <p className="mt-2 truncate font-semibold text-white">{value}</p>
    </div>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-20 size-[520px] rounded-full bg-emerald-500/[0.08] blur-[140px]" />
      <div className="absolute -right-40 top-60 size-[520px] rounded-full bg-cyan-500/[0.08] blur-[140px]" />

      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.8) 1px, transparent 1px)",
          backgroundSize: "54px 54px",
        }}
      />
    </div>
  );
}