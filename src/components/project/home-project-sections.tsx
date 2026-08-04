import Link from "next/link";
import { ArrowRight, Hand, MoveUpRight, ScanFace, Timer } from "lucide-react";

import { PipelineOverview } from "@/components/project/pipeline-overview";
import {
  calculateProjectProgress,
  countProjectStages,
  projectStatus,
} from "@/config/project-status";

const metricIcons = [ScanFace, MoveUpRight, Hand, Timer] as const;

export function HomeProjectSections() {
  const progress = calculateProjectProgress(projectStatus.stages);
  const counts = countProjectStages(projectStatus.stages);

  return (
    <>
      <section className="relative px-5 py-20 sm:px-6 sm:py-24">
        <Separator />
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Jak to działa" title="Trzy proste kroki" />
          <div className="mt-10">
            <PipelineOverview stages={projectStatus.publicWorkflow} compact />
          </div>
        </div>
      </section>

      <section className="px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow="Możliwości"
            title="Ruch opisany czytelnymi danymi"
          />
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.metricGroups.map((metric, index) => {
              const Icon = metricIcons[index];
              return (
                <article
                  key={metric.name}
                  className="min-w-0 rounded-[24px] border border-white/10 bg-white/[0.035] p-6"
                >
                  <div className="flex size-11 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.08]">
                    <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold">{metric.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-500">
                    {metric.description}
                  </p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-24 sm:px-6 sm:pb-28">
        <div className="mx-auto grid max-w-7xl gap-5 rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/70 to-cyan-400/[0.07] p-7 sm:p-9 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">
              Aktualny etap projektu
            </p>
            <div className="mt-4 flex flex-wrap items-baseline gap-4">
              <p className="text-5xl font-bold text-white">{progress}%</p>
              <p className="text-slate-300">
                {counts.completed} z {projectStatus.stages.length} etapów jest gotowych.
              </p>
            </div>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-400">
              Analiza pozy i metryk działa. Trwa podłączanie niezależnego Risk Engine do kolejki.
            </p>
          </div>
          <Link
            href="/o-projekcie"
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-5 py-3 font-semibold transition hover:bg-white/[0.1] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-300"
          >
            Zobacz projekt
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
      <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-400">
        {eyebrow}
      </p>
      <h2 className="mt-4 text-3xl font-bold tracking-[-0.035em] sm:text-5xl">
        {title}
      </h2>
    </div>
  );
}

function Separator() {
  return (
    <div className="absolute inset-x-5 top-0 mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-white/15 to-transparent sm:inset-x-6" />
  );
}
