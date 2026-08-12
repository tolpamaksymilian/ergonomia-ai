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
                  className="ui-card p-5"
                >
                  <Icon className="size-5 text-primary" aria-hidden="true" />
                  <h3 className="mt-4 font-semibold text-foreground">{capability.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{capability.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-20 sm:px-6 sm:pb-24">
        <div className="ui-card mx-auto flex max-w-7xl flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full border border-orange-200 bg-brand-soft px-3 py-1 text-xs font-semibold text-accent-foreground dark:border-orange-800">
                {release.statusLabel}
              </span>
              <span className="rounded-full border border-border bg-surface-muted px-3 py-1 font-mono text-xs font-semibold text-muted-foreground">v{release.version}</span>
            </div>
            <h2 className="mt-4 flex items-center gap-2 text-2xl font-bold text-foreground"><span className="size-2.5 rounded-full bg-emerald-500" aria-hidden="true" />Pełny przepływ jest gotowy do testów</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Pierwsza wersja testowa prowadzi od filmu do raportu.
            </p>
          </div>
          <Link
            href="/o-projekcie"
            className="ui-button-secondary shrink-0 text-sm hover:border-orange-200 hover:bg-brand-soft"
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
                <article key={plan.id} className="ui-card p-5">
                  <div className="flex items-start justify-between gap-3">
                    <Icon className="size-5 text-slate-400" aria-hidden="true" />
                    <span className="rounded-full border border-border bg-surface-muted px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Planowane
                    </span>
                  </div>
                  <h3 className="mt-4 font-semibold text-foreground">{plan.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{plan.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-24 sm:px-6 sm:pb-28">
        <div className="ui-card mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 p-7 sm:flex-row sm:items-center sm:p-9">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-foreground">Sprawdź nagranie</p>
            <h2 className="mt-3 text-2xl font-bold sm:text-3xl">Rozpocznij nową analizę</h2>
          </div>
          <Link
            href={isAuthenticated ? "/panel/analizy/nowa" : "/logowanie"}
            className="ui-button-primary min-h-12 px-6 py-3"
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
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-primary">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-bold tracking-[-0.035em] text-foreground sm:text-4xl">{title}</h2>
    </div>
  );
}

function Separator() {
  return (
    <div className="absolute inset-x-5 top-0 mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-white/15 to-transparent sm:inset-x-6" />
  );
}
