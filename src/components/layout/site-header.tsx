import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  LogIn,
  UserRound,
} from "lucide-react";

import { createClient } from "@/lib/supabase/server";

export async function SiteHeader() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <header className="fixed inset-x-0 top-0 z-50 px-4 pt-4">
      <div className="mx-auto flex max-w-7xl items-center justify-between rounded-2xl border border-white/10 bg-slate-950/70 px-5 py-3 shadow-2xl shadow-black/20 backdrop-blur-xl">
        <Link
          href="/"
          className="flex items-center gap-3"
        >
          <span className="flex size-10 items-center justify-center rounded-xl border border-emerald-400/30 bg-emerald-400/10">
            <Activity className="size-5 text-emerald-300" />
          </span>

          <span>
            <span className="block text-sm font-bold tracking-wide text-white">
              Ergonomia AI
            </span>

            <span className="block text-[10px] uppercase tracking-[0.22em] text-slate-500">
              Intelligent posture analysis
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
          <Link
            className="transition hover:text-white"
            href="/"
          >
            Strona główna
          </Link>

          <Link
            className="transition hover:text-white"
            href="/o-projekcie"
          >
            O projekcie
          </Link>

          <Link
            className="transition hover:text-white"
            href="/test-bazy"
          >
            Status
          </Link>
        </nav>

        {user ? (
          <Link
            href="/panel"
            className="flex items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-semibold text-emerald-200 transition hover:border-emerald-300/60 hover:bg-emerald-400/15"
          >
            <UserRound className="size-4" />
            Mój panel
            <ArrowUpRight className="size-4" />
          </Link>
        ) : (
          <Link
            href="/logowanie"
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-white transition hover:border-emerald-400/30 hover:bg-emerald-400/10 hover:text-emerald-200"
          >
            <LogIn className="size-4" />
            Zaloguj się
          </Link>
        )}
      </div>
    </header>
  );
}