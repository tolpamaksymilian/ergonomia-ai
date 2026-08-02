import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  FileVideo,
  LogOut,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { signOutAction } from "@/actions/auth";
import { requireAdmin } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const { supabase, user, profile } = await requireAdmin();

  const [
    { count: usersCount, error: usersCountError },
    { data: latestProfiles, error: latestProfilesError },
  ] = await Promise.all([
    supabase
      .from("profiles")
      .select("id", {
        count: "exact",
        head: true,
      }),

    supabase
      .from("profiles")
      .select("id, full_name, role, created_at")
      .order("created_at", {
        ascending: false,
      })
      .limit(5),
  ]);

  const hasDatabaseError =
    Boolean(usersCountError) || Boolean(latestProfilesError);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] p-5 text-white sm:p-8">
      <Background />

      <div className="relative mx-auto max-w-7xl">
        <header className="flex flex-wrap items-center justify-between gap-5 rounded-[26px] border border-white/10 bg-slate-950/65 px-6 py-5 shadow-2xl shadow-black/20 backdrop-blur-xl">
          <Link
            href="/"
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
                Panel administratora
              </span>
            </span>
          </Link>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/panel"
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]"
            >
              <ArrowLeft className="size-4" />
              Panel użytkownika
            </Link>

            <form action={signOutAction}>
              <button
                type="submit"
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:border-red-400/30 hover:bg-red-400/10 hover:text-red-200"
              >
                <LogOut className="size-4" />
                Wyloguj się
              </button>
            </form>
          </div>
        </header>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1fr_0.4fr]">
          <div className="overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.1] via-slate-900/65 to-cyan-400/[0.08] p-8 sm:p-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">
              <ShieldCheck className="size-4" />
              Dostęp administratora
            </div>

            <h1 className="mt-7 text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
              Centrum zarządzania systemem
            </h1>

            <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">
              To miejsce będzie służyło do konfiguracji reguł
              ergonomicznych, metod oceny, progów ryzyka,
              użytkowników oraz kolejki analiz.
            </p>

            <div className="mt-8 flex flex-wrap gap-3 text-sm">
              <StatusBadge label="Sesja aktywna" />
              <StatusBadge label="Rola administratora" />
              <StatusBadge label="RLS aktywne" />
            </div>
          </div>

          <aside className="rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
            <div className="flex size-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
              <ShieldCheck className="size-6 text-cyan-300" />
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

            <div className="mt-6 border-t border-white/10 pt-5">
              <p className="text-sm text-slate-500">
                Uprawnienie
              </p>

              <p className="mt-1 font-semibold text-emerald-300">
                Pełny dostęp administracyjny
              </p>
            </div>
          </aside>
        </section>

        <section className="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            icon={Users}
            label="Użytkownicy"
            value={
              hasDatabaseError
                ? "Błąd"
                : String(usersCount ?? 0)
            }
            description="Konta zapisane w tabeli profili."
          />

          <StatCard
            icon={FileVideo}
            label="Analizy"
            value="0"
            description="Analizy wideo zostaną dodane w następnym etapie."
          />

          <StatCard
            icon={SlidersHorizontal}
            label="Zestawy reguł"
            value="0"
            description="Konfiguracje REBA, RULA i metod własnych."
          />

          <StatCard
            icon={Settings2}
            label="Wersja"
            value="0.2.0"
            description="Logowanie, profile i role aplikacyjne."
          />
        </section>

        <section className="mt-6 grid gap-6 lg:grid-cols-[1fr_0.7fr]">
          <div className="rounded-[30px] border border-white/10 bg-white/[0.035] p-7">
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

            <div className="mt-6 space-y-3">
              {latestProfiles?.length ? (
                latestProfiles.map((item) => (
                  <article
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4"
                  >
                    <div>
                      <p className="font-semibold">
                        {item.full_name || "Użytkownik bez nazwy"}
                      </p>

                      <p className="mt-1 text-xs text-slate-500">
                        Utworzono:{" "}
                        {formatDate(item.created_at)}
                      </p>
                    </div>

                    <span
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                        item.role === "admin"
                          ? "bg-emerald-400/10 text-emerald-300"
                          : "bg-cyan-400/10 text-cyan-300"
                      }`}
                    >
                      {item.role === "admin"
                        ? "Administrator"
                        : "Użytkownik"}
                    </span>
                  </article>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-white/10 p-8 text-center text-slate-500">
                  Brak profili do wyświetlenia.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-cyan-400/[0.07] to-emerald-400/[0.04] p-7">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
              Następny etap
            </p>

            <h2 className="mt-4 text-3xl font-bold tracking-[-0.03em]">
              Struktura analiz wideo
            </h2>

            <p className="mt-5 leading-7 text-slate-400">
              Następnie utworzymy tabele analiz, statusy kolejki,
              prywatny bucket filmów oraz formularz przesyłania
              pierwszego nagrania.
            </p>

            <div className="mt-7 space-y-3 text-sm text-slate-300">
              <NextStep label="Tabela analyses" />
              <NextStep label="Prywatny Storage" />
              <NextStep label="Upload filmu" />
              <NextStep label="Status przetwarzania" />
            </div>
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

type StatCardProps = {
  icon: LucideIcon;
  label: string;
  value: string;
  description: string;
};

function StatCard({
  icon: Icon,
  label,
  value,
  description,
}: StatCardProps) {
  return (
    <article className="rounded-[26px] border border-white/10 bg-white/[0.035] p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex size-11 items-center justify-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.08]">
          <Icon className="size-5 text-cyan-300" />
        </div>

        <p className="text-3xl font-bold">
          {value}
        </p>
      </div>

      <h2 className="mt-5 font-semibold">
        {label}
      </h2>

      <p className="mt-2 text-sm leading-6 text-slate-500">
        {description}
      </p>
    </article>
  );
}

function NextStep({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-black/15 px-4 py-3">
      <span className="size-2 rounded-full bg-cyan-300" />
      {label}
    </div>
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