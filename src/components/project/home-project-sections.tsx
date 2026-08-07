import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Box,
  FileText,
  Hand,
  Move3d,
  Ruler,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";

import { PipelineOverview } from "@/components/project/pipeline-overview";
import { projectStatus } from "@/config/project-status";
import { release } from "@/config/release";

const capabilityIcons = [Move3d, Ruler, Hand, ShieldCheck] as const;
const planIcons = [BarChart3, FileText, ScanSearch, Box] as const;

export function HomeProjectSections({ isAuthenticated }: { isAuthenticated: boolean }) {
  return (
    <>
      <section id="jak-to-dziala" className="relative px-5 py-20 sm:px-6 sm:py-24">
        <Separator />
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Jak to działa" title="Trzy proste kroki" />
          <div className="mt-9">
            <PipelineOverview stages={projectStatus.publicWorkflow} compact />
          </div>
        </div>
      </section>

      <section className="px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Możliwości" title="Najważniejsze elementy analizy" />
          <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.metricGroups.map((capability, index) => {
              const Icon = capabilityIcons[index];
              return (
                <article
                  key={capability.name}
                  className="rounded-[22px] border border-white/[0.08] bg-white/[0.03] p-5"
                >
                  <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                  <h3 className="mt-4 font-semibold text-white">{capability.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{capability.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 rounded-[26px] border border-emerald-300/15 bg-emerald-300/[0.05] p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-xs font-semibold text-amber-100">
                {release.statusLabel}
              </span>
              <span className="font-mono text-sm text-emerald-200">v{release.version}</span>
            </div>
            <h2 className="mt-4 text-2xl font-bold text-white">Pełny przepływ jest gotowy do testów</h2>
            <p className="mt-2 text-sm text-slate-400">
              Pierwsza wersja testowa prowadzi od filmu do raportu.
            </p>
          </div>
          <Link
            href="/o-projekcie"
            className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/[0.09] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-cyan-300"
          >
            O projekcie
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section id="planowane-funkcje" className="scroll-mt-24 px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Co dalej" title="Kolejne kierunki rozwoju" />
          <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.publicPlans.map((plan, index) => {
              const Icon = planIcons[index];
              return (
                <article key={plan.id} className="rounded-[22px] border border-white/[0.08] bg-white/[0.025] p-5">
                  <div className="flex items-start justify-between gap-3">
                    <Icon className="size-5 text-slate-400" aria-hidden="true" />
                    <span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      Planowane
                    </span>
                  </div>
                  <h3 className="mt-4 font-semibold text-white">{plan.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{plan.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-24 sm:px-6 sm:pb-28">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 rounded-[28px] border border-cyan-300/15 bg-[#0a1724] p-7 sm:flex-row sm:items-center sm:p-9">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-300">Sprawdź nagranie</p>
            <h2 className="mt-3 text-2xl font-bold sm:text-3xl">Rozpocznij nową analizę</h2>
          </div>
          <Link
            href={isAuthenticated ? "/panel/analizy/nowa" : "/logowanie"}
            className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300"
          >
            Rozpocznij analizę
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </>
  );
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-bold tracking-[-0.035em] text-white sm:text-4xl">{title}</h2>
    </div>
  );
}

function Separator() {
  return (
    <div className="absolute inset-x-5 top-0 mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-white/15 to-transparent sm:inset-x-6" />
  );
}
