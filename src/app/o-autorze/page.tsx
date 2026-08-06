import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Code2, Cpu, Factory, LineChart, ShieldCheck } from "lucide-react";

import { AuthorPortrait } from "@/components/author/author-portrait";
import { SiteHeader } from "@/components/layout/site-header";
import { SiteFooter } from "@/components/layout/site-footer";
import { authorProfile } from "@/config/author";

export const metadata: Metadata = {
  title: { absolute: "O autorze — Ergonomia AI" },
  description: "Poznaj autora projektu Ergonomia AI i założenia stojące za rozwojem systemu.",
};

const interestIcons = [Cpu, Code2, ShieldCheck, Factory, LineChart] as const;

export default function AuthorPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />
      <section className="relative px-5 pb-20 pt-32 sm:px-6 sm:pb-24 sm:pt-40">
        <Background />
        <div className="relative mx-auto max-w-7xl">
          <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-300">O autorze</p>
              <h1 className="mt-5 text-4xl font-bold tracking-[-0.04em] sm:text-6xl">{authorProfile.name}</h1>
              <p className="mt-3 text-lg font-medium text-cyan-200">{authorProfile.role}</p>
              <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">{authorProfile.summary}</p>
              <div className="mt-7 flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-slate-300">
                <BookOpen className="size-5 shrink-0 text-emerald-300" aria-hidden="true" />
                {authorProfile.education}
              </div>
            </div>
            <div className="overflow-hidden rounded-[30px] border border-cyan-300/15 bg-slate-950/55 shadow-[0_30px_100px_rgba(0,0,0,0.4)]">
              <AuthorPortrait />
            </div>
          </div>

          <section className="mt-20" aria-labelledby="interests-heading">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-300">Obszary zainteresowań</p>
            <h2 id="interests-heading" className="mt-4 text-3xl font-bold tracking-[-0.03em] sm:text-4xl">Technologia blisko praktyki</h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {authorProfile.interests.map((interest, index) => {
                const Icon = interestIcons[index];
                return (
                  <article key={interest} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                    <Icon className="size-5 text-cyan-300" aria-hidden="true" />
                    <h3 className="mt-4 text-sm font-semibold leading-6">{interest}</h3>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="mt-20 grid gap-8 rounded-[30px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.07] via-slate-900/65 to-cyan-400/[0.06] p-7 sm:p-10 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-300">Dlaczego powstał projekt</p>
              <h2 className="mt-4 text-3xl font-bold tracking-[-0.03em] sm:text-4xl">Od obserwacji do działającego narzędzia</h2>
              {authorProfile.projectMotivation.map((paragraph) => (
                <p key={paragraph} className="mt-4 leading-7 text-slate-300">{paragraph}</p>
              ))}
            </div>
            <Link href="/o-projekcie" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300">
              Poznaj projekt
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </section>
        </div>
      </section>
      <SiteFooter />
    </main>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-0 size-[560px] rounded-full bg-emerald-500/[0.07] blur-[150px]" />
      <div className="absolute -right-48 top-60 size-[600px] rounded-full bg-cyan-500/[0.07] blur-[160px]" />
    </div>
  );
}
