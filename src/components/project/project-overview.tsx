"use client";

import Link from "next/link";
import { motion } from "motion/react";
import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  CircleDot,
  Clock3,
  Code2,
  Database,
  FileText,
  FileVideo,
  GitBranch,
  Globe2,
  LockKeyhole,
  ScanSearch,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type RoadmapStatus = "done" | "next" | "planned";

type RoadmapItem = {
  title: string;
  description: string;
  weight: number;
  completion: number;
  status: RoadmapStatus;
};

const roadmap: RoadmapItem[] = [
  {
    title: "Fundament aplikacji",
    description:
      "GitHub, Next.js, Vercel, Supabase, publiczna strona i połączenie z bazą.",
    weight: 12,
    completion: 100,
    status: "done",
  },
  {
    title: "Logowanie i role",
    description: "Rejestracja, potwierdzanie e-maila, logowanie, profile oraz role user i admin.",
    weight: 10,
    completion: 100,
    status: "done",
  },
  {
    title: "Panel reguł administratora",
    description:
      "Kąty, czasy, punktacja, poziomy ryzyka, wersjonowanie i symulator.",
    weight: 18,
    completion: 0,
    status: "planned",
  },
  {
    title: "Obsługa analiz wideo",
    description:
      "Upload, zadania analizy, status przetwarzania i prywatne pliki.",
    weight: 12,
    completion: 0,
    status: "planned",
  },
  {
    title: "Pipeline AI",
    description:
      "Sylwetka, dłonie, punkty ciała, geometria, śledzenie i analiza czasowa.",
    weight: 24,
    completion: 0,
    status: "planned",
  },
  {
    title: "Wyniki i raportowanie",
    description:
      "Wykresy, zdarzenia, film wynikowy, JSON oraz raport PDF.",
    weight: 14,
    completion: 0,
    status: "planned",
  },
  {
    title: "Walidacja i pilotaż",
    description:
      "Porównanie wyników z ekspertem, testy nagrań i stabilizacja systemu.",
    weight: 10,
    completion: 0,
    status: "planned",
  },
];

const projectProgress = Math.round(
  roadmap.reduce(
    (sum, item) => sum + item.weight * (item.completion / 100),
    0,
  ),
);

const technologies: TechnologyProps[] = [
  {
    icon: Globe2,
    name: "Next.js i Vercel",
    description: "Publiczna aplikacja i automatyczne wdrożenia.",
  },
  {
    icon: Database,
    name: "Supabase",
    description: "PostgreSQL, logowanie, polityki dostępu i storage.",
  },
  {
    icon: BrainCircuit,
    name: "Modele AI",
    description: "RTMW, RTMW3D, MediaPipe Hands i modele obiektów.",
  },
  {
    icon: SlidersHorizontal,
    name: "Silnik reguł",
    description: "Edytowalne pomiary, czasy i metody oceny.",
  },
  {
    icon: FileVideo,
    name: "Analiza wideo",
    description: "FFmpeg, OpenCV oraz niezależny worker Python.",
  },
  {
    icon: LockKeyhole,
    name: "Bezpieczeństwo",
    description: "Prywatne filmy, RLS, role i wersjonowanie zmian.",
  },
];

export function ProjectOverview() {
  return (
    <section className="relative overflow-hidden px-5 pb-28 pt-36 sm:px-6">
      <Background />

      <div className="relative mx-auto max-w-7xl">
        <motion.div
          initial={{ opacity: 0, y: 26 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.75 }}
          className="grid gap-12 lg:grid-cols-[1fr_0.7fr] lg:items-center"
        >
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200">
              <Sparkles className="size-4" />
              Publiczny projekt technologiczny
            </div>

            <h1 className="mt-8 max-w-4xl text-5xl font-bold leading-[1.05] tracking-[-0.045em] sm:text-6xl">
              Tworzymy system, który zamienia film w{" "}
              <span className="bg-gradient-to-r from-emerald-300 via-cyan-200 to-sky-300 bg-clip-text text-transparent">
                mierzalną ocenę ergonomii.
              </span>
            </h1>

            <p className="mt-7 max-w-3xl text-lg leading-8 text-slate-300">
              Ergonomia AI będzie wykrywać sylwetkę pracownika, obliczać
              kąty, analizować czas utrzymywania pozycji i wykorzystywać
              konfigurowalne metody REBA, RULA oraz reguły własne.
            </p>

            <div className="mt-9 flex flex-wrap gap-4">
              <Link
                href="/test-bazy"
                className="group flex items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3.5 font-semibold text-slate-950 transition hover:bg-emerald-300"
              >
                Sprawdź status
                <ArrowRight className="size-5 transition group-hover:translate-x-1" />
              </Link>

              <Link
                href="/"
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-6 py-3.5 font-semibold text-white transition hover:bg-white/[0.08]"
              >
                Strona główna
              </Link>
            </div>
          </div>

          <ProgressCard progress={projectProgress} />
        </motion.div>

        <section className="mt-28">
          <SectionHeading
            eyebrow="Roadmapa"
            title="Od fundamentu aplikacji do zwalidowanego systemu AI"
            description="Postęp jest obliczany na podstawie wag poszczególnych etapów. Nie jest wpisywany ręcznie jako przypadkowa wartość."
          />

          <div className="mt-12 space-y-4">
            {roadmap.map((item, index) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, x: -24 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.25 }}
                transition={{
                  duration: 0.5,
                  delay: Math.min(index * 0.05, 0.25),
                }}
              >
                <RoadmapCard
                  item={item}
                  index={index + 1}
                />
              </motion.div>
            ))}
          </div>
        </section>

        <section className="mt-28">
          <SectionHeading
            eyebrow="Architektura"
            title="Modułowa technologia bez uzależnienia oceny od jednego modelu"
            description="Modele dostarczają dane pomiarowe, natomiast wynik oblicza oddzielny, wersjonowany silnik reguł."
          />

          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {technologies.map((technology, index) => (
              <motion.div
                key={technology.name}
                initial={{ opacity: 0, y: 22 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.25 }}
                transition={{
                  duration: 0.5,
                  delay: index * 0.06,
                }}
              >
                <Technology {...technology} />
              </motion.div>
            ))}
          </div>
        </section>

        <section className="mt-28 grid gap-6 lg:grid-cols-2">
          <div className="rounded-[30px] border border-white/10 bg-white/[0.035] p-8">
            <div className="flex size-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
              <Code2 className="size-6 text-cyan-300" />
            </div>

            <p className="mt-7 text-xs uppercase tracking-[0.2em] text-cyan-300">
              Aktualnie rozwijamy
            </p>

            <h2 className="mt-3 text-3xl font-bold">
              Panel administratora i strukturę analiz
            </h2>

            <p className="mt-5 leading-7 text-slate-400">
              Logowanie, profile i role są już aktywne. Obecnie rozwijamy
              bezpieczny panel administratora oraz strukturę danych potrzebną
              do obsługi analiz wideo.
            </p>
          </div>

          <div className="rounded-[30px] border border-amber-300/15 bg-amber-400/[0.06] p-8">
            <div className="flex size-12 items-center justify-center rounded-2xl border border-amber-300/20 bg-amber-400/10">
              <FileText className="size-6 text-amber-300" />
            </div>

            <p className="mt-7 text-xs uppercase tracking-[0.2em] text-amber-300">
              Ważne ograniczenie
            </p>

            <h2 className="mt-3 text-3xl font-bold">
              System będzie wspierał, a nie zastępował eksperta
            </h2>

            <p className="mt-5 leading-7 text-slate-300/80">
              Wyniki powinny być interpretowane razem z warunkami pracy,
              jakością nagrania i profesjonalną oceną specjalisty.
            </p>
          </div>
        </section>

        <section className="mt-28 overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/60 to-cyan-400/[0.08] p-8 sm:p-12">
          <div className="grid gap-10 lg:grid-cols-[1fr_0.75fr] lg:items-center">
            <div>
              <div className="flex items-center gap-3">
                <GitBranch className="size-6 text-white" />

                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">
                  Rozwój publiczny
                </p>
              </div>

              <h2 className="mt-6 text-4xl font-bold tracking-[-0.035em]">
                Każdy ukończony etap trafia bezpośrednio do wersji online
              </h2>

              <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-400">
                GitHub przechowuje kod, a Vercel automatycznie publikuje
                kolejne wersje po zatwierdzeniu zmian w głównej gałęzi.
              </p>
            </div>

            <div className="rounded-3xl border border-white/10 bg-black/20 p-6">
              <HistoryItem
                version="0.1.0"
                title="Fundament aplikacji"
                description="Next.js, Vercel, Supabase i pierwsze publiczne strony."
                current
              />

              <HistoryItem
                version="0.2.0"
                title="Logowanie i role"
                description="Planowana kolejna wersja systemu."
              />
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}

function ProgressCard({ progress }: { progress: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.8, delay: 0.15 }}
      className="rounded-[32px] border border-white/10 bg-slate-900/65 p-7 shadow-2xl shadow-black/30 backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Postęp projektu
          </p>

          <p className="mt-3 text-5xl font-bold text-white">
            {progress}%
          </p>

          <p className="mt-2 text-sm text-slate-400">
            Fundament aplikacji ukończony
          </p>
        </div>

        <div
          className="relative flex size-32 items-center justify-center rounded-full"
          style={{
            background: `conic-gradient(#34d399 ${
              progress * 3.6
            }deg, rgba(255,255,255,0.08) 0deg)`,
          }}
        >
          <div className="flex size-[106px] items-center justify-center rounded-full bg-[#07111f]">
            <span className="text-2xl font-bold text-emerald-300">
              {progress}%
            </span>
          </div>
        </div>
      </div>

      <div className="mt-8 h-2 overflow-hidden rounded-full bg-white/10">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 1.2, delay: 0.45 }}
          className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400"
        />
      </div>

      <div className="mt-5 flex items-center gap-2 text-sm text-emerald-300">
        <CheckCircle2 className="size-4" />
        Wersja 0.1.0 dostępna online
      </div>
    </motion.div>
  );
}

function RoadmapCard({
  item,
  index,
}: {
  item: RoadmapItem;
  index: number;
}) {
  const statusStyles = {
    done: {
      label: "Ukończone",
      icon: CheckCircle2,
      badge: "bg-emerald-400/10 text-emerald-300",
      iconStyle: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
    },
    next: {
      label: "Następny etap",
      icon: CircleDot,
      badge: "bg-cyan-400/10 text-cyan-300",
      iconStyle: "border-cyan-400/20 bg-cyan-400/10 text-cyan-300",
    },
    planned: {
      label: "Planowane",
      icon: Clock3,
      badge: "bg-white/[0.06] text-slate-400",
      iconStyle: "border-white/10 bg-white/[0.04] text-slate-500",
    },
  };

  const style = statusStyles[item.status];
  const Icon = style.icon;

  return (
    <article className="grid gap-5 rounded-[26px] border border-white/10 bg-white/[0.03] p-6 transition hover:border-white/20 hover:bg-white/[0.045] md:grid-cols-[auto_1fr_auto] md:items-center">
      <div
        className={`flex size-12 items-center justify-center rounded-2xl border ${style.iconStyle}`}
      >
        <Icon className="size-5" />
      </div>

      <div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-slate-600">
            {String(index).padStart(2, "0")}
          </span>

          <h3 className="text-xl font-semibold">{item.title}</h3>

          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${style.badge}`}
          >
            {style.label}
          </span>
        </div>

        <p className="mt-3 leading-7 text-slate-400">
          {item.description}
        </p>
      </div>

      <div className="md:text-right">
        <p className="text-sm text-slate-500">Udział w projekcie</p>
        <p className="mt-1 text-xl font-bold text-white">
          {item.weight}%
        </p>
      </div>
    </article>
  );
}

type TechnologyProps = {
  icon: LucideIcon;
  name: string;
  description: string;
};

function Technology({
  icon: Icon,
  name,
  description,
}: TechnologyProps) {
  return (
    <article className="h-full rounded-[26px] border border-white/10 bg-white/[0.035] p-7 transition hover:-translate-y-1 hover:border-cyan-400/20">
      <div className="flex size-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.08]">
        <Icon className="size-6 text-cyan-300" />
      </div>

      <h3 className="mt-6 text-xl font-semibold">{name}</h3>

      <p className="mt-3 leading-7 text-slate-400">{description}</p>
    </article>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="max-w-4xl">
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-400">
        {eyebrow}
      </p>

      <h2 className="mt-5 text-4xl font-bold tracking-[-0.035em] sm:text-5xl">
        {title}
      </h2>

      <p className="mt-6 text-lg leading-8 text-slate-400">
        {description}
      </p>
    </div>
  );
}

function HistoryItem({
  version,
  title,
  description,
  current = false,
}: {
  version: string;
  title: string;
  description: string;
  current?: boolean;
}) {
  return (
    <div className="flex gap-4 border-b border-white/10 py-5 first:pt-0 last:border-0 last:pb-0">
      <div
        className={`mt-1 size-3 shrink-0 rounded-full ${
          current
            ? "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,0.8)]"
            : "bg-slate-700"
        }`}
      />

      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
          Wersja {version}
        </p>

        <p className="mt-2 font-semibold text-white">{title}</p>

        <p className="mt-1 text-sm leading-6 text-slate-400">
          {description}
        </p>
      </div>
    </div>
  );
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-40 top-0 size-[600px] rounded-full bg-emerald-500/[0.08] blur-[160px]" />
      <div className="absolute -right-52 top-[700px] size-[650px] rounded-full bg-cyan-500/[0.07] blur-[170px]" />

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