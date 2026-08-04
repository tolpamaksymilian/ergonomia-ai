import Link from "next/link";
import {
  ArrowRight,
  BrainCircuit,
  Database,
  FileWarning,
  Hand,
  LockKeyhole,
  MonitorCog,
  ScanSearch,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { PipelineOverview } from "@/components/project/pipeline-overview";
import { ProjectVersionCards } from "@/components/project/project-version-cards";
import { projectStatus } from "@/config/project-status";

const technologyIcons = [
  ScanSearch,
  BrainCircuit,
  Hand,
  MonitorCog,
  Database,
  ShieldCheck,
  LockKeyhole,
] as const;

export function ProjectOverview() {
  return (
    <section className="relative overflow-hidden px-5 pb-28 pt-36 sm:px-6">
      <Background />

      <div className="relative mx-auto max-w-7xl">
        <div className="grid gap-10 lg:grid-cols-[1fr_0.72fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200">
              <Sparkles className="size-4" aria-hidden="true" />
              Cel projektu
            </div>

            <h1 className="mt-8 max-w-4xl text-5xl font-bold leading-[1.05] tracking-[-0.045em] sm:text-6xl">
              Krótkie nagranie zamieniane w{" "}
              <span className="bg-gradient-to-r from-emerald-300 via-cyan-200 to-sky-300 bg-clip-text text-transparent">
                uporządkowane dane o ruchu
              </span>
            </h1>

            <p className="mt-7 max-w-3xl text-lg leading-8 text-slate-300">
              Ergonomia AI ma wspierać analizę stanowisk pracy za pomocą
              krótkich filmów i modeli AI. System wykrywa pracownika,
              analizuje ciało i dłonie oraz przygotowuje techniczne pomiary
              do dalszej interpretacji.
            </p>

            <div className="mt-9 flex flex-wrap gap-4">
              <Link
                href="/panel/analizy/nowa"
                className="group inline-flex items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3.5 font-semibold text-slate-950 transition hover:bg-emerald-300"
              >
                Utwórz analizę
                <ArrowRight className="size-5 transition group-hover:translate-x-1" />
              </Link>
              <Link
                href="/"
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-6 py-3.5 font-semibold transition hover:bg-white/[0.08]"
              >
                Strona główna
              </Link>
            </div>
          </div>

          <aside className="rounded-[30px] border border-amber-300/15 bg-amber-400/[0.06] p-7 sm:p-8">
            <div className="flex size-12 items-center justify-center rounded-2xl border border-amber-300/20 bg-amber-400/10">
              <ShieldCheck className="size-6 text-amber-300" aria-hidden="true" />
            </div>
            <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">
              Rola systemu
            </p>
            <h2 className="mt-3 text-2xl font-semibold">
              Wsparcie specjalisty, nie jego automatyczny zamiennik
            </h2>
            <p className="mt-4 leading-7 text-slate-300/80">
              System ma wspierać ocenę i porządkować dane pomiarowe.
              Ostateczna interpretacja powinna należeć do osoby posiadającej
              odpowiednie kompetencje.
            </p>
          </aside>
        </div>

        <section className="mt-24">
          <SectionHeading
            eyebrow="Architektura procesu"
            title="Jeden pipeline, czytelnie oznaczone granice"
            description="Działające etapy prowadzą do wersjonowanego JSON pozy i lokalnego silnika metryk. Ocena ryzyka oraz raport pozostają planowane."
          />
          <div className="mt-12">
            <PipelineOverview stages={projectStatus.fullPipeline} />
          </div>
        </section>

        <section className="mt-24">
          <SectionHeading
            eyebrow="Aktualne wersje"
            title="Stan modułów bez danych udawanych przez interfejs"
            description="Informacje wersji i trybu workera są publiczną konfiguracją aplikacji, a nie wartościami pobieranymi z bazy."
          />
          <div className="mt-10">
            <ProjectVersionCards />
          </div>
        </section>

        <section className="mt-24">
          <SectionHeading
            eyebrow="Modele i technologie"
            title="Moduły o jasno rozdzielonych zadaniach"
            description="Każdy element odpowiada za konkretną część procesu, dzięki czemu pomiary nie są mieszane z przyszłą oceną ryzyka."
          />
          <div className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {projectStatus.technologies.map((technology, index) => {
              const Icon = technologyIcons[index];

              return (
                <article
                  key={technology.name}
                  className="min-w-0 rounded-[26px] border border-white/10 bg-white/[0.035] p-7 transition hover:-translate-y-1 hover:border-cyan-400/20"
                >
                  <div className="flex size-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.08]">
                    <Icon className="size-6 text-cyan-300" aria-hidden="true" />
                  </div>
                  <h3 className="mt-6 break-words text-xl font-semibold">
                    {technology.name}
                  </h3>
                  <p className="mt-3 leading-7 text-slate-400">
                    {technology.description}
                  </p>
                </article>
              );
            })}
          </div>
        </section>

        <section className="mt-24 overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-amber-400/[0.07] via-slate-900/60 to-cyan-400/[0.05] p-7 sm:p-10">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-amber-300">
                Ograniczenia analizy
              </p>
              <h2 className="mt-4 text-3xl font-bold tracking-[-0.03em] sm:text-4xl">
                Wiarygodność zaczyna się od jakości nagrania
              </h2>
              <p className="mt-5 text-lg leading-8 text-slate-400">
                Modele odrzucają dane, których nie można bezpiecznie użyć.
                Brak pomiaru jest lepszy niż sztucznie pewny wynik.
              </p>
            </div>
            <FileWarning className="size-10 text-amber-300" aria-hidden="true" />
          </div>

          <ul className="mt-10 grid gap-4 md:grid-cols-2">
            {projectStatus.limitations.map((limitation) => (
              <li
                key={limitation}
                className="flex items-start gap-3 rounded-2xl border border-white/[0.07] bg-black/15 p-5 text-sm leading-6 text-slate-300"
              >
                <span className="mt-2 size-2 shrink-0 rounded-full bg-amber-300" />
                {limitation}
              </li>
            ))}
          </ul>
        </section>
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

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-0 size-[600px] rounded-full bg-emerald-500/[0.08] blur-[160px]" />
      <div className="absolute -right-52 top-[700px] size-[650px] rounded-full bg-cyan-500/[0.07] blur-[170px]" />
      <div
        className="absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.8) 1px, transparent 1px)",
          backgroundSize: "54px 54px",
        }}
      />
    </div>
  );
}
