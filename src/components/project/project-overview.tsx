import Link from "next/link";
import { ArrowRight, CheckCircle2, FileWarning, ShieldCheck } from "lucide-react";

import { PipelineOverview } from "@/components/project/pipeline-overview";
import { projectStatus } from "@/config/project-status";
import { release } from "@/config/release";

const workingNow = [
  "Prywatne przesyłanie i kolejka filmów",
  "Analiza sylwetki, ruchu oraz dłoni",
  "Metryki i techniczna ocena ryzyka",
  "Raport dostępny w panelu i do druku",
] as const;

export function ProjectOverview() {
  return (
    <section className="relative overflow-hidden px-5 pb-24 pt-32 sm:px-6 sm:pt-40">
      <Background />
      <div className="relative mx-auto max-w-7xl">
        <header className="max-w-4xl">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">O projekcie</p>
          <h1 className="mt-5 text-4xl font-bold tracking-[-0.045em] text-white sm:text-6xl">
            Film zamieniony w czytelne dane o ergonomii
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
            System analizuje ruch pracownika, oblicza metryki i przygotowuje raport do dalszej interpretacji.
          </p>
        </header>

        <section className="mt-12 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="rounded-[24px] border border-emerald-300/15 bg-emerald-300/[0.05] p-6">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-xs font-semibold text-amber-100">
                {release.statusLabel}
              </span>
              <span className="font-mono text-sm text-emerald-200">v{release.version}</span>
            </div>
            <h2 className="mt-4 text-xl font-bold text-white">Pełny przepływ od filmu do raportu działa lokalnie.</h2>
          </div>
          <aside className="rounded-[24px] border border-amber-300/15 bg-amber-300/[0.05] p-6 lg:max-w-sm">
            <ShieldCheck className="size-5 text-amber-300" aria-hidden="true" />
            <p className="mt-3 text-sm font-semibold leading-6 text-amber-50">{projectStatus.disclaimer}</p>
          </aside>
        </section>

        <section className="mt-20" aria-labelledby="pipeline-heading">
          <SectionHeading eyebrow="Jak działa" title="Od nagrania do raportu" id="pipeline-heading" />
          <div className="mt-9">
            <PipelineOverview stages={projectStatus.fullPipeline} />
          </div>
        </section>

        <section className="mt-20 grid gap-8 lg:grid-cols-[1fr_0.85fr]" aria-labelledby="status-heading">
          <div>
            <SectionHeading eyebrow="Co obecnie działa" title="Gotowa wersja testowa" id="status-heading" />
            <ul className="mt-7 grid gap-3 sm:grid-cols-2">
              {workingNow.map((item) => (
                <li key={item} className="flex items-start gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4 text-sm leading-6 text-slate-300">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-300" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-accent-foreground">Technologie</p>
            <div className="mt-5 flex flex-wrap gap-2.5">
              {projectStatus.publicTechnologies.map((technology) => (
                <span key={technology} className="rounded-full border border-white/10 bg-white/[0.035] px-4 py-2 text-sm font-medium text-slate-300">
                  {technology}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-20 grid gap-8 lg:grid-cols-[0.8fr_1.2fr]" aria-labelledby="limitations-heading">
          <div>
            <FileWarning className="size-6 text-amber-300" aria-hidden="true" />
            <SectionHeading eyebrow="Ograniczenia" title="Nagranie ma znaczenie" id="limitations-heading" />
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {projectStatus.limitations.map((limitation) => (
              <li key={limitation} className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4 text-sm leading-6 text-slate-300">
                {limitation}
              </li>
            ))}
          </ul>
        </section>

        <section className="ui-card mt-20 p-7 sm:p-9" aria-labelledby="plan-heading">
          <SectionHeading eyebrow="Co jest planowane" title="Najbliższe kierunki" id="plan-heading" />
          <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.publicPlans.map((plan) => (
              <article key={plan.id} className="rounded-2xl border border-white/[0.08] bg-slate-950/30 p-4">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Planowane</span>
                <h3 className="mt-3 font-semibold text-white">{plan.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-400">{plan.description}</p>
              </article>
            ))}
          </div>
        </section>

        <div className="mt-10 flex flex-wrap gap-3">
          <Link href="/panel/analizy/nowa" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-emerald-300">
            Rozpocznij analizę <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
          <Link href="/o-autorze" className="ui-button-secondary">
            O autorze
          </Link>
        </div>
      </div>
    </section>
  );
}

function SectionHeading({ eyebrow, title, id }: { eyebrow: string; title: string; id: string }) {
  return (
    <div className="mt-3">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">{eyebrow}</p>
      <h2 id={id} className="mt-3 text-3xl font-bold tracking-[-0.035em] text-white sm:text-4xl">{title}</h2>
    </div>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-0 size-[540px] rounded-full bg-emerald-500/[0.055] blur-[160px]" />
      <div className="absolute -right-52 top-[700px] size-[600px] rounded-full bg-orange-200/20 blur-[170px] dark:bg-orange-950/10" />
    </div>
  );
}
