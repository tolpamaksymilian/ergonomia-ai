import Link from "next/link";
import {
  ArrowRight,
  Box,
  BrainCircuit,
  Code2,
  Database,
  FileWarning,
  Hand,
  ScanSearch,
  ServerCog,
  ShieldCheck,
} from "lucide-react";

import { PipelineOverview } from "@/components/project/pipeline-overview";
import { ProjectVersionCards } from "@/components/project/project-version-cards";
import { countProjectStages, projectStatus } from "@/config/project-status";

const technologyIcons = [Code2, Database, ServerCog, ScanSearch, BrainCircuit, Hand, Box, ShieldCheck] as const;

export function ProjectOverview() {
  const counts = countProjectStages(projectStatus.stages);

  return (
    <section className="relative overflow-hidden px-5 pb-24 pt-32 sm:px-6 sm:pt-40">
      <Background />
      <div className="relative mx-auto max-w-7xl">
        <div className="grid gap-8 lg:grid-cols-[1fr_0.72fr] lg:items-end">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-300">Co robi system?</p>
            <h1 className="mt-5 max-w-4xl text-4xl font-bold tracking-[-0.04em] sm:text-6xl">
              Zamienia krótki film w uporządkowane dane o ruchu
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
              Wykrywa pracownika, analizuje pozycję i przygotowuje pomiary do dalszej oceny.
            </p>
          </div>
          <aside className="rounded-[26px] border border-amber-300/15 bg-amber-400/[0.06] p-6">
            <ShieldCheck className="size-6 text-amber-300" aria-hidden="true" />
            <p className="mt-4 font-semibold text-amber-100">
              System wspiera analizę i nie zastępuje oceny specjalisty.
            </p>
          </aside>
        </div>

        <section className="mt-20" aria-labelledby="pipeline-heading">
          <SectionHeading eyebrow="Jak działa?" title="Pipeline od filmu do danych" id="pipeline-heading" />
          <div className="mt-9">
            <PipelineOverview stages={projectStatus.fullPipeline} />
          </div>
        </section>

        <section className="mt-20" aria-labelledby="working-heading">
          <SectionHeading eyebrow="Co już działa?" title="Gotowe moduły i ich wersje" id="working-heading" />
          <p className="mt-5 max-w-3xl text-slate-400">
            {counts.completed} etapy są gotowe. Risk Engine działa niezależnie, a podłączenie go do kolejki jest w realizacji.
          </p>
          <div className="mt-8">
            <ProjectVersionCards />
          </div>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.technologies.map((technology, index) => {
              const Icon = technologyIcons[index];
              return (
                <article key={technology.name} className="rounded-[22px] border border-white/10 bg-white/[0.035] p-5">
                  <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                  <h3 className="mt-4 font-semibold">{technology.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-500">{technology.description}</p>
                </article>
              );
            })}
          </div>

          <details className="mt-6 rounded-2xl border border-white/10 bg-white/[0.025] p-5">
            <summary className="cursor-pointer font-semibold text-cyan-200 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-300">
              Pokaż 14 metryk technicznych
            </summary>
            <ul className="mt-5 grid gap-2 text-sm text-slate-400 sm:grid-cols-2 lg:grid-cols-3">
              {projectStatus.metricNames.map((metric) => (
                <li key={metric} className="rounded-xl border border-white/[0.06] bg-slate-950/35 px-4 py-3">{metric}</li>
              ))}
            </ul>
          </details>
        </section>

        <section className="mt-20 rounded-[30px] border border-white/10 bg-gradient-to-br from-amber-400/[0.06] via-slate-900/60 to-cyan-400/[0.04] p-7 sm:p-9" aria-labelledby="limitations-heading">
          <div className="flex items-center gap-3">
            <FileWarning className="size-6 text-amber-300" aria-hidden="true" />
            <SectionHeading eyebrow="Jakie ma ograniczenia?" title="Nagranie ma znaczenie" id="limitations-heading" />
          </div>
          <ul className="mt-7 grid gap-3 sm:grid-cols-2">
            {projectStatus.limitations.map((limitation) => (
              <li key={limitation} className="flex items-start gap-3 rounded-2xl border border-white/[0.07] bg-black/15 p-4 text-sm leading-6 text-slate-300">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-300" />
                {limitation}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-12 flex flex-wrap gap-3">
          <Link href="/panel/analizy/nowa" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300">
            Rozpocznij analizę <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
          <Link href="/o-autorze" className="inline-flex min-h-11 items-center rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3 font-semibold transition hover:bg-white/[0.08]">
            O autorze
          </Link>
        </div>
      </div>
    </section>
  );
}

function SectionHeading({ eyebrow, title, id }: { eyebrow: string; title: string; id: string }) {
  return (
    <div>
      <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-300">{eyebrow}</p>
      <h2 id={id} className="mt-3 text-3xl font-bold tracking-[-0.03em] sm:text-4xl">{title}</h2>
    </div>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-0 size-[580px] rounded-full bg-emerald-500/[0.07] blur-[160px]" />
      <div className="absolute -right-52 top-[700px] size-[620px] rounded-full bg-cyan-500/[0.06] blur-[170px]" />
    </div>
  );
}
