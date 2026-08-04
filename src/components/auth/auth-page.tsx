import Link from "next/link";
import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { AuthForm } from "@/components/auth/auth-form";

type AuthPageProps = {
  mode: "login" | "register";
  notice?: string;
};

export function AuthPage({
  mode,
  notice,
}: AuthPageProps) {
  const isRegister = mode === "register";

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] px-5 py-8 text-white sm:px-6">
      <Background />

      <div className="relative mx-auto grid min-h-[calc(100vh-4rem)] max-w-7xl overflow-hidden rounded-[34px] border border-white/10 bg-slate-950/50 shadow-2xl shadow-black/40 backdrop-blur-xl lg:grid-cols-[0.95fr_1.05fr]">
        <section className="relative hidden overflow-hidden border-r border-white/10 p-12 lg:flex lg:flex-col lg:justify-between">
          <div>
            <Link
              href="/"
              className="inline-flex items-center gap-3"
            >
              <span className="flex size-11 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
                <Activity className="size-6 text-emerald-300" />
              </span>

              <span>
                <span className="block font-bold">
                  Ergonomia AI
                </span>

                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Analiza pozy i ruchu
                </span>
              </span>
            </Link>

            <h1 className="mt-24 max-w-xl text-5xl font-bold leading-[1.06] tracking-[-0.045em]">
              Analiza ergonomii oparta na{" "}
              <span className="bg-gradient-to-r from-emerald-300 to-cyan-300 bg-clip-text text-transparent">
                mierzalnych danych.
              </span>
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-400">
              Prywatny panel pozwala przesyłać nagrania,
              obserwować postęp i przeglądać film wynikowy
              oraz dane pozy pracownika.
            </p>
          </div>

          <div className="grid gap-4">
            <Benefit
              icon={BrainCircuit}
              title="Modułowa analiza AI"
              description="YOLOX-X, RTMW WholeBody i osobna walidacja dłoni pracują jako rozdzielone moduły."
            />

            <Benefit
              icon={ShieldCheck}
              title="Prywatność danych"
              description="Filmy oraz wyniki są dostępne wyłącznie dla właściciela i administratora."
            />

            <Benefit
              icon={CheckCircle2}
              title="Ocena rozwijana etapami"
              description="Silnik metryk działa lokalnie, a końcowa ocena ryzyka i raport są w przygotowaniu."
            />
          </div>
        </section>

        <section className="flex items-center justify-center p-6 sm:p-10 lg:p-14">
          <div className="w-full max-w-md">
            <Link
              href="/"
              className="mb-10 inline-flex items-center gap-3 lg:hidden"
            >
              <span className="flex size-10 items-center justify-center rounded-xl bg-emerald-400/10">
                <Activity className="size-5 text-emerald-300" />
              </span>

              <span className="font-bold">
                Ergonomia AI
              </span>
            </Link>

            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-400">
              {isRegister
                ? "Nowe konto"
                : "Panel użytkownika"}
            </p>

            <h2 className="mt-4 text-4xl font-bold tracking-[-0.035em]">
              {isRegister
                ? "Rozpocznij korzystanie z systemu"
                : "Zaloguj się do swojego konta"}
            </h2>

            <p className="mt-4 leading-7 text-slate-400">
              {isRegister
                ? "Utwórz konto i potwierdź swój adres e-mail."
                : "Podaj adres e-mail oraz hasło przypisane do konta."}
            </p>

            {notice && (
              <div className="mt-6 rounded-2xl border border-red-400/20 bg-red-400/[0.08] px-4 py-3 text-sm leading-6 text-red-200">
                {notice}
              </div>
            )}

            <AuthForm mode={mode} />
          </div>
        </section>
      </div>
    </main>
  );
}

function Benefit({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <article className="flex gap-4 rounded-2xl border border-white/10 bg-white/[0.035] p-5">
      <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-cyan-400/10">
        <Icon className="size-5 text-cyan-300" />
      </div>

      <div>
        <h2 className="font-semibold">{title}</h2>

        <p className="mt-1 text-sm leading-6 text-slate-400">
          {description}
        </p>
      </div>
    </article>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 -top-40 size-[600px] rounded-full bg-emerald-500/[0.08] blur-[160px]" />

      <div className="absolute -bottom-48 -right-40 size-[650px] rounded-full bg-cyan-500/[0.08] blur-[170px]" />

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
