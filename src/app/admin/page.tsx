import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  ListChecks,
  LogOut,
  ShieldCheck,
  Users,
} from "lucide-react";

import { signOutAction } from "@/actions/auth";
import { ProjectRoadmap } from "@/components/project/project-roadmap";
import { ProjectVersionCards } from "@/components/project/project-version-cards";
import { projectStatus } from "@/config/project-status";
import { requireAdmin } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const { supabase, user, profile } = await requireAdmin();

  const [
    { count: usersCount, error: usersCountError },
    { data: latestProfiles, error: latestProfilesError },
  ] = await Promise.all([
    supabase.from("profiles").select("id", {
      count: "exact",
      head: true,
    }),
    supabase
      .from("profiles")
      .select("id, full_name, role, created_at")
      .order("created_at", { ascending: false })
      .limit(5),
  ]);

  const hasDatabaseError =
    Boolean(usersCountError) || Boolean(latestProfilesError);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] p-5 text-white sm:p-8">
      <Background />

      <div className="relative mx-auto max-w-7xl">
        <header className="flex flex-wrap items-center justify-between gap-5 rounded-[26px] border border-white/10 bg-slate-950/65 px-6 py-5 shadow-2xl shadow-black/20 backdrop-blur-xl">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
              <Activity className="size-6 text-emerald-300" />
            </span>
            <span>
              <span className="block font-bold">Ergonomia AI</span>
              <span className="block text-xs text-slate-500">
                Panel administratora
              </span>
            </span>
          </Link>

          <nav className="flex flex-wrap items-center gap-3" aria-label="Nawigacja panelu administratora">
            <Link
              href="#rozwoj-systemu"
              className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/20 bg-cyan-400/[0.08] px-4 py-2.5 text-sm font-semibold text-cyan-200 transition hover:bg-cyan-400/[0.13]"
            >
              <ListChecks className="size-4" />
              Rozwój systemu
            </Link>
            <Link
              href="/panel"
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]"
            >
              <ArrowLeft className="size-4" />
              Panel użytkownika
            </Link>
            <form action={signOutAction}>
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:border-red-400/30 hover:bg-red-400/10 hover:text-red-200"
              >
                <LogOut className="size-4" />
                Wyloguj się
              </button>
            </form>
          </nav>
        </header>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1fr_0.38fr]">
          <div className="overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.1] via-slate-900/65 to-cyan-400/[0.08] p-8 sm:p-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">
              <ShieldCheck className="size-4" />
              Dostęp administratora
            </div>
            <h1 className="mt-7 text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
              Stan i rozwój systemu
            </h1>
            <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">
              Panel pokazuje rzeczywisty zakres działających modułów,
              zintegrowany etap metryk ergonomicznych oraz Risk Engine
              rozwijany jako kolejny niezależny etap.
            </p>
            <div className="mt-8 flex flex-wrap gap-3 text-sm">
              <StatusBadge label="Sesja aktywna" />
              <StatusBadge label="Rola administratora" />
              <StatusBadge label="RLS aktywne" />
            </div>
          </div>

          <aside className="rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
            <div className="flex items-start justify-between gap-4">
              <div className="flex size-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
                <Users className="size-6 text-cyan-300" />
              </div>
              <p className="text-3xl font-bold">
                {hasDatabaseError ? "—" : usersCount ?? 0}
              </p>
            </div>
            <p className="mt-6 text-xs uppercase tracking-[0.18em] text-slate-500">
              Administrator
            </p>
            <p className="mt-2 text-xl font-semibold">
              {profile?.full_name || "Administrator"}
            </p>
            <p className="mt-2 break-all text-sm text-slate-400">
              {user.email}
            </p>
            <p className="mt-5 text-sm text-slate-500">
              Konta w tabeli profili: {hasDatabaseError ? "brak danych" : usersCount ?? 0}
            </p>
          </aside>
        </section>

        <section className="mt-6">
          <ProjectVersionCards />
        </section>

        <section
          id="rozwoj-systemu"
          className="mt-10 scroll-mt-6 rounded-[32px] border border-white/10 bg-white/[0.025] p-5 sm:p-8"
        >
          <div className="max-w-4xl">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-cyan-300">
              Rozwój systemu
            </p>
            <h2 className="mt-4 text-3xl font-bold tracking-[-0.03em] sm:text-4xl">
              Roadmapa oparta na rzeczywistych etapach
            </h2>
            <p className="mt-5 text-lg leading-8 text-slate-400">
              Status i procent są wyliczane z jednej publicznej konfiguracji.
              Nie są przechowywane w Supabase ani wpisywane ręcznie w widoku.
            </p>
          </div>
          <div className="mt-8">
            <ProjectRoadmap stages={projectStatus.stages} showProgress />
          </div>
        </section>

        <section className="mt-8 rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Ostatnie konta
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                Użytkownicy systemu
              </h2>
            </div>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-400">
              Ostatnie 5 profili
            </span>
          </div>

          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            {latestProfiles?.length ? (
              latestProfiles.map((item) => (
                <article
                  key={item.id}
                  className="flex min-w-0 flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold">
                      {item.full_name || "Użytkownik bez nazwy"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Utworzono: {formatDate(item.created_at)}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                      item.role === "admin"
                        ? "bg-emerald-400/10 text-emerald-300"
                        : "bg-cyan-400/10 text-cyan-300"
                    }`}
                  >
                    {item.role === "admin" ? "Administrator" : "Użytkownik"}
                  </span>
                </article>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 p-8 text-center text-slate-500 lg:col-span-2">
                Brak profili do wyświetlenia.
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function StatusBadge({ label }: { label: string }) {
  return (
    <span className="flex items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-400/[0.06] px-3 py-1.5 text-emerald-200">
      <span className="size-2 rounded-full bg-emerald-400" />
      {label}
    </span>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeZone: "Europe/Warsaw",
  }).format(new Date(value));
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-48 -top-40 size-[620px] rounded-full bg-emerald-500/[0.07] blur-[160px]" />
      <div className="absolute -right-48 top-[420px] size-[620px] rounded-full bg-cyan-500/[0.07] blur-[170px]" />
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
