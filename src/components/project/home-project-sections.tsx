import Link from "next/link";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  CircleDot,
  Hand,
  MoveDown,
  MoveUpRight,
  ScanFace,
  ScanLine,
  Target,
} from "lucide-react";

import { FeatureStatusBadge } from "@/components/project/feature-status-badge";
import { PipelineOverview } from "@/components/project/pipeline-overview";
import { projectStatus } from "@/config/project-status";

const metricIcons = [
  MoveDown,
  ScanFace,
  MoveUpRight,
  Target,
  ScanLine,
  Activity,
  Hand,
  CircleDot,
] as const;

export function HomeProjectSections() {
  return (
    <>
      <section className="relative px-5 py-24 sm:px-6 sm:py-28">
        <Separator />
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow="Jak działa system"
            title="Od prywatnego nagrania do uporządkowanych pomiarów"
            description="Każdy etap ma jasno określony zakres. Końcowa ocena i raport są wyraźnie oddzielone od funkcji dostępnych obecnie."
          />
          <div className="mt-12">
            <PipelineOverview stages={projectStatus.publicWorkflow} compact />
          </div>
        </div>
      </section>

      <section className="px-5 pb-24 sm:px-6 sm:pb-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeading
            eyebrow="Co system analizuje"
            title="Techniczne metryki ruchu ciała i dłoni"
            description="Obecne pomiary przygotowują wiarygodne dane geometryczne do dalszej oceny. Nie są jeszcze końcowym poziomem ryzyka."
          />

          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {projectStatus.metrics.map((metric, index) => {
              const Icon = metricIcons[index];

              return (
                <article
                  key={metric.name}
                  className="group min-w-0 rounded-[24px] border border-white/10 bg-white/[0.035] p-6 transition hover:-translate-y-1 hover:border-cyan-400/25"
                >
                  <div className="flex size-11 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.08]">
                    <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                  </div>
                  <h3 className="mt-5 break-words text-lg font-semibold">
                    {metric.name}
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-slate-500">
                    {metric.description}
                  </p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-5 pb-28 sm:px-6">
        <div className="mx-auto max-w-7xl overflow-hidden rounded-[34px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/70 to-cyan-400/[0.07] p-6 sm:p-10">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <SectionHeading
              eyebrow="Aktualny etap rozwoju"
              title="Działające fundamenty, uczciwie oznaczone kolejne kroki"
              description="Status pochodzi ze wspólnej konfiguracji projektu używanej również na stronie „O projekcie” i w panelu administratora."
            />
            <Link
              href="/o-projekcie"
              className="group inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-5 py-3 font-semibold transition hover:bg-white/[0.09]"
            >
              Pełna architektura
              <ArrowRight className="size-4 transition group-hover:translate-x-1" />
            </Link>
          </div>

          <div className="mt-10 grid gap-6 xl:grid-cols-2">
            <FeatureColumn
              title="Działa"
              description="Funkcje dostępne w obecnej wersji aplikacji lub gotowe lokalnie."
              status="completed"
              features={projectStatus.workingFeatures}
            />
            <FeatureColumn
              title="W przygotowaniu"
              description="Funkcje rozwijane lub planowane — nie są przedstawiane jako gotowe."
              status="planned"
              features={projectStatus.plannedFeatures}
            />
          </div>
        </div>
      </section>
    </>
  );
}

function FeatureColumn({
  title,
  description,
  status,
  features,
}: {
  title: string;
  description: string;
  status: "completed" | "planned";
  features: readonly {
    title: string;
    description: string;
  }[];
}) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-slate-950/35 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-2xl font-semibold">{title}</h3>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500">
            {description}
          </p>
        </div>
        <FeatureStatusBadge status={status} />
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {features.map((feature) => (
          <article
            key={feature.title}
            className="min-w-0 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4"
          >
            <div className="flex items-start gap-3">
              <CheckCircle2
                className={`mt-0.5 size-4 shrink-0 ${
                  status === "completed"
                    ? "text-emerald-300"
                    : "text-slate-600"
                }`}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <h4 className="break-words text-sm font-semibold text-slate-100">
                  {feature.title}
                </h4>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {feature.description}
                </p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="max-w-4xl">
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-400">
        {eyebrow}
      </p>
      <h2 className="mt-5 text-4xl font-bold tracking-[-0.035em] sm:text-5xl">
        {title}
      </h2>
      <p className="mt-6 text-lg leading-8 text-slate-400">
        {description}
      </p>
    </div>
  );
}

function Separator() {
  return (
    <div className="absolute inset-x-5 top-0 mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-white/15 to-transparent sm:inset-x-6" />
  );
}
