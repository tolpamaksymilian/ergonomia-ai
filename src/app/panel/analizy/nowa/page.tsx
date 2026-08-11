import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  ShieldCheck,
} from "lucide-react";

import { NewAnalysisForm } from "@/components/analyses/new-analysis-form";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function NewAnalysisPage() {
  const { user } = await requireUser();

  return (
    <main className="ui-page relative px-5 py-8 sm:px-8">
      <Background />

      <div className="relative mx-auto max-w-5xl">
        <header className="ui-surface flex flex-wrap items-center justify-between gap-4 px-6 py-5 backdrop-blur-xl">
          <div className="flex items-center gap-2"><ThemeToggle /><Link
            href="/panel"
            className="flex items-center gap-3"
          >
            <span className="flex size-11 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
              <Activity className="size-6 text-emerald-300" />
            </span>

            <span>
              <span className="block font-bold">
                Ergonomia AI
              </span>

              <span className="block text-xs text-slate-500">
                Nowa analiza
              </span>
            </span>
          </Link>

          <Link
            href="/panel"
            className="ui-button-secondary text-sm"
          >
            <ArrowLeft className="size-4" />
            Powrót do panelu
          </Link></div>
        </header>

        <section className="ui-card mt-8 overflow-hidden bg-gradient-to-br from-brand-soft via-card to-card p-8 sm:p-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">
            <ShieldCheck className="size-4" />
            Prywatne przesyłanie
          </div>

          <h1 className="mt-7 text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
            Utwórz nową analizę ergonomii
          </h1>

          <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-400">
            Dodaj nagranie stanowiska pracy. Film zostanie
            zapisany w prywatnym magazynie i skierowany
            do kolejki lokalnego workera AI.
          </p>
        </section>

        <div className="mt-6">
          <NewAnalysisForm
            userId={user.id}
          />
        </div>
      </div>
    </main>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-52 -top-40 size-[620px] rounded-full bg-emerald-500/[0.07] blur-[160px]" />

      <div className="absolute -right-52 top-[500px] size-[620px] rounded-full bg-cyan-500/[0.07] blur-[170px]" />

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
