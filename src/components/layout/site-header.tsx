import Link from "next/link";
import { Activity } from "lucide-react";

import { MainNavigation } from "@/components/layout/main-navigation";
import { ThemeToggle } from "@/components/layout/theme-toggle";
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
      <div className="relative mx-auto flex max-w-7xl items-center justify-between rounded-xl border border-border bg-surface/95 px-5 py-3 shadow-sm backdrop-blur-xl">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-3"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-brand-soft">
            <Activity className="size-5 text-primary" />
          </span>

          <span className="min-w-0">
            <span className="block truncate text-sm font-bold tracking-wide text-foreground">
              Ergonomia AI
            </span>

            <span className="hidden truncate text-[10px] uppercase tracking-[0.22em] text-muted-foreground sm:block">
              Analiza pozy i ruchu
            </span>
          </span>
        </Link>

        <div className="flex items-center gap-2"><ThemeToggle /><MainNavigation isAuthenticated={Boolean(user)} isAdmin={isAdmin} /></div>
      </div>
    </header>
  );
}
