import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Hand,
  MoveUpRight,
  ScanFace,
  Timer,
} from "lucide-react";

import { PipelineOverview } from "@/components/project/pipeline-overview";
import {
  calculateProjectProgress,
  projectStatus,
} from "@/config/project-status";
import { release } from "@/config/release";

const metricIcons = [ScanFace, MoveUpRight, Hand, Timer] as const;
const plannedHighlights = [
  "charts",
  "key-frames",
  "pdf",
  "threshold-panel",
  "comparison",
  "workstation-simulator",
] as const;

export function HomeProjectSections({ isAuthenticated }: { isAuthenticated: boolean }) {
  const mvpProgress = calculateProjectProgress(projectStatus.mvpStages);
  const fullProgress = calculateProjectProgress(projectStatus.stages);
  const planned = plannedHighlights
    .map((id) => projectStatus.stages.find((stage) => stage.id === id))
    .filter((stage) => stage !== undefined);

  return (
    <>
      <section id="jak-to-dziala" className="relative px-5 py-20 sm:px-6 sm:py-24">
        <Separator />
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Jak to działa" title="Od filmu do czytelnego raportu" />
          <div className="mt-10">
            <PipelineOverview stages={projectStatus.publicWorkflow} compact />
          </div>
        </div>
      </section>

      <section className="px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Możliwości" title="Najważniejsze dane o ruchu" />
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.metricGroups.map((metric, index) => {
              const Icon = metricIcons[index];
              return (
                <article key={metric.name} className="min-w-0 rounded-[24px] border border-white/10 bg-white/[0.035] p-6">
                  <div className="flex size-11 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.08]">
                    <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold">{metric.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-500">{metric.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-7xl rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/70 to-cyan-400/[0.07] p-7 sm:p-9">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">Aktualna wersja</p>
              <h2 className="mt-3 text-3xl font-bold">{release.version}</h2>
              <p className="mt-3 max-w-2xl text-slate-300">Pierwsza wersja testowa z pełnym przepływem od filmu do raportu.</p>
            </div>
            <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-4 py-2 text-sm font-semibold text-amber-100">
              {release.statusLabel}
            </span>
          </div>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <ProgressCard label="Wersja testowa MVP" value={mvpProgress} />
            <ProgressCard label="Pełny plan projektu" value={fullProgress} />
          </div>
          <p className="mt-5 text-sm leading-6 text-slate-400">
            MVP działa end-to-end. Pełna wizja nadal obejmuje walidację, hosting workerów i kolejne metody oceny.
          </p>
        </div>
      </section>

      <section id="planowane-funkcje" className="scroll-mt-24 px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Planowane funkcje" title="Co rozwijamy dalej" />
          <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {planned.map((stage) => (
              <article key={stage.id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <BarChart3 className="size-5 text-slate-500" aria-hidden="true" />
                <h3 className="mt-4 font-semibold">{stage.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500">{stage.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="px-5 pb-24 sm:px-6 sm:pb-28">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 rounded-[30px] border border-emerald-300/15 bg-emerald-300/[0.06] p-7 sm:flex-row sm:items-center sm:p-9">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">Gotowy do testu?</p>
            <h2 className="mt-3 text-2xl font-bold sm:text-3xl">Prześlij krótkie nagranie stanowiska</h2>
          </div>
          <Link href={isAuthenticated ? "/panel/analizy/nowa" : "/logowanie"} className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300">
            Rozpocznij analizę
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </>
  );
}

function ProgressCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-5">
      <div className="flex items-center justify-between gap-4">
        <p className="font-semibold text-slate-200">{label}</p>
        <p className="text-xl font-bold text-cyan-200">{value}%</p>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10" aria-label={`${label}: ${value}%`}>
        <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-400">{eyebrow}</p>
      <h2 className="mt-4 text-3xl font-bold tracking-[-0.035em] sm:text-5xl">{title}</h2>
    </div>
  );
}

function Separator() {
  return <div className="absolute inset-x-5 top-0 mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-white/15 to-transparent sm:inset-x-6" />;
}
