import Link from "next/link";
import { Activity } from "lucide-react";

import { MainNavigation } from "@/components/layout/main-navigation";
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
      <div className="relative mx-auto flex max-w-7xl items-center justify-between rounded-2xl border border-white/10 bg-slate-950/70 px-5 py-3 shadow-2xl shadow-black/20 backdrop-blur-xl">
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

        <MainNavigation isAuthenticated={Boolean(user)} isAdmin={isAdmin} />
      </div>
    </header>
  );
}
