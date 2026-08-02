import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  ShieldCheck,
} from "lucide-react";

import { NewAnalysisForm } from "@/components/analyses/new-analysis-form";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function NewAnalysisPage() {
  const { user } = await requireUser();

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] px-5 py-8 text-white sm:px-8">
      <Background />

      <div className="relative mx-auto max-w-5xl">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-[26px] border border-white/10 bg-slate-950/65 px-6 py-5 backdrop-blur-xl">
          <Link
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
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]"
          >
            <ArrowLeft className="size-4" />
            Powrót do panelu
          </Link>
        </header>

        <section className="mt-8 overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/65 to-cyan-400/[0.08] p-8 sm:p-10">
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
            do kolejki przyszłego workera AI.
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