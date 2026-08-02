import {
  BrainCircuit,
  ChartNoAxesCombined,
  FileText,
  Hand,
  ScanSearch,
  SlidersHorizontal,
} from "lucide-react";

import { HeroSection } from "@/components/landing/hero-section";
import { SiteHeader } from "@/components/layout/site-header";

const features = [
  {
    icon: ScanSearch,
    title: "Analiza pozycji",
    description:
      "Wykrywanie punktów ciała, postawy pracownika i ruchów wykonywanych podczas pracy.",
  },
  {
    icon: SlidersHorizontal,
    title: "Reguły administratora",
    description:
      "Pełna edycja zakresów kątów, czasu trwania, punktacji i poziomów ryzyka.",
  },
  {
    icon: BrainCircuit,
    title: "Modułowe modele AI",
    description:
      "Osobne modele dla sylwetki, dłoni, obiektów, głębi oraz analizy przestrzennej.",
  },
  {
    icon: Hand,
    title: "Analiza dłoni",
    description:
      "Punkty palców, pozycja nadgarstka, kontakt z przedmiotem i przybliżona klasyfikacja chwytu.",
  },
  {
    icon: ChartNoAxesCombined,
    title: "Wyniki w czasie",
    description:
      "Wykresy ryzyka, zdarzenia, czas przekroczeń oraz przejście do krytycznego momentu filmu.",
  },
  {
    icon: FileText,
    title: "Raportowanie",
    description:
      "Film ze szkieletem, szczegółowy JSON, dane tabelaryczne oraz raport PDF.",
  },
];

export default function HomePage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />

      <HeroSection />

      <section className="relative px-6 py-28">
        <div className="absolute inset-x-0 top-0 mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-white/15 to-transparent" />

        <div className="mx-auto max-w-7xl">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-emerald-400">
              Możliwości systemu
            </p>

            <h2 className="mt-5 text-4xl font-bold tracking-[-0.03em] sm:text-5xl">
              Od pojedynczego filmu do pełnej oceny ergonomicznej
            </h2>

            <p className="mt-6 text-lg leading-8 text-slate-400">
              Architektura systemu oddziela wykrywanie punktów ciała
              od obliczeń i oceny. Dzięki temu zasady można zmieniać
              bez ponownego trenowania modeli AI.
            </p>
          </div>

          <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => {
              const Icon = feature.icon;

              return (
                <article
                  key={feature.title}
                  className="group relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.035] p-7 transition duration-300 hover:-translate-y-1 hover:border-emerald-400/25 hover:bg-white/[0.055]"
                >
                  <div className="absolute right-0 top-0 size-28 rounded-full bg-emerald-400/5 blur-3xl transition group-hover:bg-emerald-400/10" />

                  <div className="relative">
                    <div className="flex size-12 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
                      <Icon className="size-6 text-emerald-300" />
                    </div>

                    <h3 className="mt-6 text-xl font-semibold">
                      {feature.title}
                    </h3>

                    <p className="mt-3 leading-7 text-slate-400">
                      {feature.description}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-6 pb-28">
        <div className="mx-auto max-w-7xl overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-500/10 via-slate-900/70 to-cyan-500/10 p-8 sm:p-12">
          <div className="grid gap-10 lg:grid-cols-[1fr_0.8fr] lg:items-center">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.25em] text-cyan-300">
                Projekt rozwijany publicznie
              </p>

              <h2 className="mt-5 text-3xl font-bold tracking-[-0.03em] sm:text-5xl">
                Każda kolejna wersja będzie dostępna online
              </h2>

              <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
                Strona, baza danych i kolejne moduły są wdrażane
                automatycznie przez GitHub i Vercel. Moduł AI zostanie
                uruchomiony jako niezależny worker.
              </p>
            </div>

            <div className="rounded-3xl border border-white/10 bg-black/20 p-7">
              <p className="text-sm text-slate-400">Aktualny etap</p>

              <p className="mt-2 text-2xl font-bold">
                Fundament aplikacji
              </p>

              <div className="mt-6 h-2 overflow-hidden rounded-full bg-white/10">
                <div className="h-full w-[12%] rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400" />
              </div>

              <div className="mt-3 flex justify-between text-xs text-slate-500">
                <span>Rozpoczęcie</span>
                <span>12% ukończone</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}