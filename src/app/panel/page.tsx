import { redirect } from "next/navigation";
import Link from "next/link";
import {
  Activity,
  FileVideo,
  LayoutDashboard,
  LogOut,
  Plus,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { signOutAction } from "@/actions/auth";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function UserPanelPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/logowanie");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("full_name, role, created_at")
    .eq("id", user.id)
    .single();

  return (
    <main className="min-h-screen bg-[#050b14] p-5 text-white sm:p-8">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-wrap items-center justify-between gap-5 rounded-[26px] border border-white/10 bg-slate-950/60 px-6 py-5 backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-2xl bg-emerald-400/10">
              <Activity className="size-6 text-emerald-300" />
            </span>

            <div>
              <p className="font-bold">Ergonomia AI</p>

              <p className="text-xs text-slate-500">
                Panel użytkownika
              </p>
            </div>
          </div>

          <form action={signOutAction}>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]"
            >
              <LogOut className="size-4" />
              Wyloguj się
            </button>
          </form>
        </header>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1fr_0.36fr]">
          <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/60 to-cyan-400/[0.08] p-8 sm:p-10">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-400">
              Witaj w systemie
            </p>

            <h1 className="mt-5 text-4xl font-bold tracking-[-0.035em] sm:text-5xl">
              {profile?.full_name || "Użytkowniku"}
            </h1>

            <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-400">
              Konto zostało poprawnie zalogowane. W
              kolejnych etapach pojawi się tutaj możliwość
              przesyłania filmów i tworzenia analiz
              ergonomicznych.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/panel/analizy/nowa"
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300"
              >
                <Plus className="size-5" />
                Utwórz nową analizę
              </Link>

              <Link
                href="/panel/analizy"
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3 font-semibold text-white transition hover:bg-white/[0.08]"
              >
                <FileVideo className="size-5 text-cyan-300" />
                Historia analiz
              </Link>
            </div>

          </div>

          <div className="rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-cyan-400/10">
              <UserRound className="size-6 text-cyan-300" />
            </div>

            <p className="mt-6 text-xs uppercase tracking-[0.18em] text-slate-500">
              Zalogowane konto
            </p>

            <p className="mt-2 break-all font-semibold">
              {user.email}
            </p>

            <p className="mt-5 text-sm text-slate-500">
              Rola
            </p>

            <p className="mt-1 font-semibold text-emerald-300">
              {profile?.role ?? "user"}
            </p>
          </div>
        </section>

        <section className="mt-6 grid gap-5 md:grid-cols-2">
          <DashboardCard
            icon={LayoutDashboard}
            title="Dashboard"
            description="Podsumowanie analiz, poziomów ryzyka i ostatnich działań."
          />

          <DashboardCard
            icon={FileVideo}
            title="Analizy wideo"
            description="Tworzenie nowej analizy oraz przeglądanie historii."
          />
        </section>
      </div>
    </main>
  );
}

function DashboardCard({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <article className="rounded-[26px] border border-white/10 bg-white/[0.03] p-7 opacity-60">
      <div className="flex items-center justify-between">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-white/[0.05]">
          <Icon className="size-6 text-slate-400" />
        </div>

        <span className="rounded-full bg-white/[0.05] px-3 py-1 text-xs text-slate-500">
          W przygotowaniu
        </span>
      </div>

      <h2 className="mt-6 text-xl font-semibold">
        {title}
      </h2>

      <p className="mt-3 leading-7 text-slate-500">
        {description}
      </p>
    </article>
  );
}