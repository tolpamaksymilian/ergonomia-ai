import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  LogIn,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { createClient } from "@/lib/supabase/server";

export async function SiteHeader() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  let isAdmin = false;

  if (user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", user.id)
      .maybeSingle();

    isAdmin = profile?.role === "admin";
  }

  return (
    <header className="fixed inset-x-0 top-0 z-50 px-4 pt-4">
      <div className="mx-auto flex max-w-7xl items-center justify-between rounded-2xl border border-white/10 bg-slate-950/70 px-5 py-3 shadow-2xl shadow-black/20 backdrop-blur-xl">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-3"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-emerald-400/30 bg-emerald-400/10">
            <Activity className="size-5 text-emerald-300" />
          </span>

          <span className="min-w-0">
            <span className="block truncate text-sm font-bold tracking-wide text-white">
              Ergonomia AI
            </span>

            <span className="hidden truncate text-[10px] uppercase tracking-[0.22em] text-slate-500 sm:block">
              Analiza pozy i ruchu
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
          <Link
            href="/"
            className="transition hover:text-white"
          >
            Strona główna
          </Link>

          <Link
            href="/o-projekcie"
            className="transition hover:text-white"
          >
            O projekcie
          </Link>

          <Link
            href="/test-bazy"
            className="transition hover:text-white"
          >
            Status
          </Link>
        </nav>

        {user ? (
          <Link
            href={isAdmin ? "/admin" : "/panel"}
            className="flex shrink-0 items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-semibold text-emerald-200 transition hover:border-emerald-300/60 hover:bg-emerald-400/15 sm:px-4"
          >
            {isAdmin ? (
              <ShieldCheck className="size-4" />
            ) : (
              <UserRound className="size-4" />
            )}

            <span className="hidden sm:inline">
              {isAdmin ? "Panel admina" : "Mój panel"}
            </span>

            <ArrowUpRight className="size-4" />
          </Link>
        ) : (
          <Link
            href="/logowanie"
            className="flex shrink-0 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm font-semibold text-white transition hover:border-emerald-400/30 hover:bg-emerald-400/10 hover:text-emerald-200 sm:px-4"
          >
            <LogIn className="size-4" />

            <span className="hidden sm:inline">
              Zaloguj się
            </span>
          </Link>
        )}
      </div>
    </header>
  );
}
