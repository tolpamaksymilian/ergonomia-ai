import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Bot,
  Braces,
  ChartNoAxesCombined,
  Cog,
  Compass,
} from "lucide-react";

import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { AuthorModelLoader } from "@/components/three/author-model/author-model-loader";
import { authorProfile } from "@/config/author";

export const metadata: Metadata = {
  title: { absolute: "Maksymilian Tołpa — autor projektu Ergonomia AI" },
  description:
    "Poznaj autora projektu Ergonomia AI, jego doświadczenie i kierunek rozwoju systemu.",
};

const focusIcons = [Braces, Cog, ChartNoAxesCombined, Bot] as const;

export default function AuthorPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />
      <section className="relative px-5 pb-24 pt-32 sm:px-6 sm:pt-40">
        <Background />
        <div className="relative mx-auto max-w-7xl">
          <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
            <header className="lg:col-start-1 lg:row-start-1">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">O autorze</p>
              <h1 className="mt-5 text-4xl font-bold tracking-[-0.045em] sm:text-6xl">{authorProfile.name}</h1>
              <p className="mt-3 text-lg font-medium text-cyan-200">{authorProfile.role}</p>
            </header>

            <div className="relative overflow-hidden rounded-[30px] border border-white/[0.09] bg-[#07131e] shadow-[0_32px_100px_rgba(0,0,0,0.38)] lg:col-start-2 lg:row-span-2 lg:row-start-1">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_52%_34%,rgba(45,212,191,0.09),transparent_46%)]" />
              <AuthorModelLoader />
              <div className="absolute inset-x-5 bottom-4 flex flex-wrap items-center justify-between gap-2 text-[10px] uppercase tracking-[0.14em] text-slate-500">
                <span>Symboliczny awatar 3D</span>
                <span>Lee Perry-Smith · CC BY 3.0</span>
              </div>
            </div>

            <div className="lg:col-start-1 lg:row-start-2">
              <p className="max-w-xl text-lg leading-8 text-slate-300">{authorProfile.summary}</p>
              <p className="mt-4 max-w-xl leading-7 text-slate-400">{authorProfile.about}</p>
              <div className="mt-6 flex items-center gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 text-sm text-slate-300">
                <BookOpen className="size-5 shrink-0 text-emerald-300" aria-hidden="true" />
                {authorProfile.education}
              </div>
            </div>
          </div>

          <section className="mt-20" aria-labelledby="focus-heading">
            <SectionHeading eyebrow="Czym się zajmuję" title="Technologia, która ma praktyczne zastosowanie" id="focus-heading" />
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {authorProfile.focusAreas.map((area, index) => {
                const Icon = focusIcons[index];
                return (
                  <article key={area.title} className="rounded-[22px] border border-white/[0.08] bg-white/[0.03] p-5">
                    <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                    <h3 className="mt-4 font-semibold">{area.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-400">{area.description}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="mt-20" aria-labelledby="experience-heading">
            <SectionHeading eyebrow="Moje doświadczenie" title="Różne perspektywy, jeden warsztat" id="experience-heading" />
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {authorProfile.experience.map((item, index) => (
                <article key={item.title} className="rounded-[22px] border border-white/[0.08] bg-[#091520] p-6">
                  <span className="font-mono text-xs text-emerald-300">0{index + 1}</span>
                  <h3 className="mt-4 text-lg font-semibold">{item.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{item.description}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="mt-20 grid gap-8 rounded-[28px] border border-emerald-300/15 bg-emerald-300/[0.045] p-7 sm:p-9 lg:grid-cols-[0.8fr_1.2fr]" aria-labelledby="motivation-heading">
            <div>
              <Compass className="size-6 text-emerald-300" aria-hidden="true" />
              <h2 id="motivation-heading" className="mt-4 text-3xl font-bold tracking-[-0.035em]">Dlaczego powstała Ergonomia AI</h2>
            </div>
            <div>
              {authorProfile.projectMotivation.map((paragraph) => (
                <p key={paragraph} className="mb-4 leading-7 text-slate-300 last:mb-0">{paragraph}</p>
              ))}
              <Link href="/o-projekcie" className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-5 py-3 text-sm font-semibold transition hover:bg-white/[0.09] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-cyan-300">
                Poznaj projekt
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>
          </section>

          <section className="mt-20" aria-labelledby="direction-heading">
            <SectionHeading eyebrow="Kierunek rozwoju" title="Nad czym chcę pracować dalej" id="direction-heading" />
            <ul className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {authorProfile.developmentDirections.map((direction) => (
                <li key={direction} className="rounded-2xl border border-white/[0.08] bg-white/[0.025] px-5 py-4 text-sm font-medium text-slate-300">
                  {direction}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </section>
      <SiteFooter />
    </main>
  );
}

function SectionHeading({ eyebrow, title, id }: { eyebrow: string; title: string; id: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">{eyebrow}</p>
      <h2 id={id} className="mt-3 text-3xl font-bold tracking-[-0.035em] sm:text-4xl">{title}</h2>
    </div>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-0 size-[540px] rounded-full bg-emerald-500/[0.055] blur-[160px]" />
      <div className="absolute -right-48 top-48 size-[580px] rounded-full bg-cyan-500/[0.05] blur-[170px]" />
    </div>
  );
}
