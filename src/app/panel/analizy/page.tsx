import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  Clock3,
  FileVideo,
  LoaderCircle,
  Plus,
  Search,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

const allowedStatuses = [
  "uploading",
  "queued",
  "processing",
  "completed",
  "failed",
  "cancelled",
] as const;

type AnalysisStatus =
  (typeof allowedStatuses)[number];

type AnalysesPageProps = {
  searchParams: Promise<{
    q?: string;
    status?: string;
  }>;
};

export default async function AnalysesPage({
  searchParams,
}: AnalysesPageProps) {
  const params = await searchParams;
  const { supabase } = await requireUser();

  const search = params.q?.trim() ?? "";

  const requestedStatus =
    params.status?.trim() ?? "";

  const selectedStatus =
    allowedStatuses.includes(
      requestedStatus as AnalysisStatus,
    )
      ? (requestedStatus as AnalysisStatus)
      : "";

  let query = supabase
    .from("analyses")
    .select(`
      id,
      title,
      description,
      status,
      progress,
      source_file_name,
      source_size_bytes,
      source_duration_seconds,
      source_width,
      source_height,
      risk_level,
      final_score,
      critical_events_count,
      error_message,
      created_at,
      updated_at,
      processing_stage
    `)
    .order("created_at", {
      ascending: false,
    });

  if (selectedStatus) {
    query = query.eq(
      "status",
      selectedStatus,
    );
  }

  if (search) {
    query = query.ilike(
      "title",
      `%${search}%`,
    );
  }

  const {
    data: analyses,
    error,
  } = await query;

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b14] px-5 py-8 text-white sm:px-8">
      <Background />

      <div className="relative mx-auto max-w-7xl">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-[26px] border border-white/10 bg-slate-950/65 px-6 py-5 shadow-2xl shadow-black/20 backdrop-blur-xl">
          <Link
            href="/panel"
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
                Historia analiz
              </span>
            </span>
          </Link>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/panel"
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm font-semibold transition hover:bg-white/[0.08]"
            >
              <ArrowLeft className="size-4" />
              Panel użytkownika
            </Link>

            <Link
              href="/panel/analizy/nowa"
              className="flex items-center gap-2 rounded-xl bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
            >
              <Plus className="size-4" />
              Nowa analiza
            </Link>
          </div>
        </header>

        <section className="mt-8 overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-emerald-400/[0.08] via-slate-900/65 to-cyan-400/[0.08] p-8 sm:p-10">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
            Analizy ergonomiczne
          </p>

          <h1 className="mt-5 text-4xl font-bold tracking-[-0.04em] sm:text-5xl">
            Historia Twoich nagrań
          </h1>

          <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-400">
            Przeglądaj przesłane filmy, ich status,
            postęp przetwarzania oraz przyszłe wyniki
            analizy ergonomicznej.
          </p>
        </section>

        <section className="mt-6 rounded-[28px] border border-white/10 bg-white/[0.035] p-5 sm:p-6">
          <form
            method="get"
            className="grid gap-4 lg:grid-cols-[1fr_260px_auto]"
          >
            <div>
              <label
                htmlFor="analysis-search"
                className="mb-2 block text-sm font-medium text-slate-300"
              >
                Szukaj po tytule
              </label>

              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-slate-500" />

                <input
                  id="analysis-search"
                  type="search"
                  name="q"
                  defaultValue={search}
                  placeholder="Np. stanowisko montażowe"
                  className="w-full rounded-xl border border-white/10 bg-slate-950/60 py-3.5 pl-12 pr-4 text-white outline-none transition placeholder:text-slate-600 focus:border-emerald-400/50"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="analysis-status"
                className="mb-2 block text-sm font-medium text-slate-300"
              >
                Status
              </label>

              <select
                id="analysis-status"
                name="status"
                defaultValue={selectedStatus}
                className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3.5 text-white outline-none transition focus:border-emerald-400/50"
              >
                <option value="">
                  Wszystkie statusy
                </option>

                <option value="uploading">
                  Przesyłanie
                </option>

                <option value="queued">
                  Oczekuje w kolejce
                </option>

                <option value="processing">
                  Analiza w toku
                </option>

                <option value="completed">
                  Ukończone
                </option>

                <option value="failed">
                  Nieudane
                </option>

                <option value="cancelled">
                  Anulowane
                </option>
              </select>
            </div>

            <div className="flex items-end gap-3">
              <button
                type="submit"
                className="flex min-h-[50px] flex-1 items-center justify-center gap-2 rounded-xl bg-cyan-400 px-5 font-semibold text-slate-950 transition hover:bg-cyan-300"
              >
                <Search className="size-4" />
                Filtruj
              </button>

              <Link
                href="/panel/analizy"
                className="flex min-h-[50px] items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] px-4 text-sm font-semibold transition hover:bg-white/[0.08]"
              >
                Wyczyść
              </Link>
            </div>
          </form>
        </section>

        {error && (
          <section className="mt-6 rounded-[26px] border border-red-400/20 bg-red-400/[0.07] p-6">
            <div className="flex items-start gap-4">
              <TriangleAlert className="mt-0.5 size-6 shrink-0 text-red-300" />

              <div>
                <p className="font-semibold text-red-200">
                  Nie udało się pobrać analiz
                </p>

                <p className="mt-2 text-sm leading-6 text-red-200/75">
                  {error.message}
                </p>
              </div>
            </div>
          </section>
        )}

        {!error &&
          analyses &&
          analyses.length === 0 && (
            <EmptyState
              filtered={Boolean(
                search || selectedStatus,
              )}
            />
          )}

        {!error &&
          analyses &&
          analyses.length > 0 && (
            <>
              <div className="mt-6 flex items-center justify-between gap-4">
                <p className="text-sm text-slate-500">
                  Znalezione analizy
                </p>

                <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-slate-300">
                  {analyses.length}
                </span>
              </div>

              <section className="mt-4 grid gap-5 lg:grid-cols-2">
                {analyses.map((analysis) => {
                  const status =
                    getStatusDetails(
                      analysis.status,
                      analysis.processing_stage,
                    );

                  const StatusIcon =
                    status.icon;

                  return (
                    <Link
                      key={analysis.id}
                      href={`/panel/analizy/${analysis.id}`}
                      className="group overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.035] transition duration-300 hover:-translate-y-1 hover:border-emerald-400/25 hover:bg-white/[0.05]"
                    >
                      <article className="p-6">
                        <div className="flex items-start justify-between gap-5">
                          <div className="flex min-w-0 items-start gap-4">
                            <div
                              className={`flex size-12 shrink-0 items-center justify-center rounded-2xl ${status.iconClass}`}
                            >
                              <StatusIcon
                                className={`size-6 ${
                                  status.animated
                                    ? "animate-spin"
                                    : ""
                                }`}
                              />
                            </div>

                            <div className="min-w-0">
                              <h2 className="truncate text-xl font-semibold transition group-hover:text-emerald-200">
                                {analysis.title}
                              </h2>

                              <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-500">
                                {analysis.description ||
                                  "Nie dodano opisu analizy."}
                              </p>
                            </div>
                          </div>

                          <span
                            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${status.badgeClass}`}
                          >
                            {status.label}
                          </span>
                        </div>

                        <div className="mt-6 grid gap-3 sm:grid-cols-3">
                          <SmallMetric
                            label="Plik"
                            value={
                              analysis.source_file_name
                            }
                          />

                          <SmallMetric
                            label="Rozmiar"
                            value={formatBytes(
                              Number(
                                analysis.source_size_bytes,
                              ),
                            )}
                          />

                          <SmallMetric
                            label="Długość"
                            value={formatDuration(
                              analysis.source_duration_seconds,
                            )}
                          />
                        </div>

                        <div className="mt-6">
                          <div className="flex items-center justify-between gap-4 text-xs">
                            <span className="text-slate-500">
                              Postęp
                            </span>

                            <span className="font-semibold text-cyan-300">
                              {analysis.progress}%
                            </span>
                          </div>

                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400"
                              style={{
                                width: `${analysis.progress}%`,
                              }}
                            />
                          </div>
                        </div>

                        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.07] pt-5">
                          <div className="flex items-center gap-2 text-xs text-slate-500">
                            <CalendarDays className="size-4" />

                            {formatDate(
                              analysis.created_at,
                            )}
                          </div>

                          <span className="text-sm font-semibold text-emerald-300 transition group-hover:translate-x-1">
                            Otwórz szczegóły →
                          </span>
                        </div>
                      </article>
                    </Link>
                  );
                })}
              </section>
            </>
          )}
      </div>
    </main>
  );
}

function EmptyState({
  filtered,
}: {
  filtered: boolean;
}) {
  return (
    <section className="mt-6 rounded-[30px] border border-dashed border-white/10 bg-white/[0.025] px-6 py-16 text-center">
      <div className="mx-auto flex size-16 items-center justify-center rounded-3xl border border-cyan-400/15 bg-cyan-400/[0.07]">
        <FileVideo className="size-8 text-cyan-300" />
      </div>

      <h2 className="mt-6 text-2xl font-semibold">
        {filtered
          ? "Brak analiz spełniających filtry"
          : "Nie utworzono jeszcze żadnej analizy"}
      </h2>

      <p className="mx-auto mt-3 max-w-xl leading-7 text-slate-500">
        {filtered
          ? "Zmień wyszukiwaną frazę lub wybierz inny status."
          : "Prześlij pierwsze nagranie stanowiska pracy i utwórz zadanie analizy."}
      </p>

      <div className="mt-7 flex flex-wrap justify-center gap-3">
        {filtered && (
          <Link
            href="/panel/analizy"
            className="rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3 font-semibold transition hover:bg-white/[0.08]"
          >
            Wyczyść filtry
          </Link>
        )}

        <Link
          href="/panel/analizy/nowa"
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300"
        >
          <Plus className="size-5" />
          Nowa analiza
        </Link>
      </div>
    </section>
  );
}

function SmallMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4">
      <p className="text-[9px] uppercase tracking-[0.15em] text-slate-600">
        {label}
      </p>

      <p className="mt-2 truncate text-sm font-semibold text-slate-200">
        {value}
      </p>
    </div>
  );
}

type StatusDetails = {
  label: string;
  icon: LucideIcon;
  animated: boolean;
  iconClass: string;
  badgeClass: string;
};

function getStatusDetails(
  status: string,
  processingStage: string | null,
): StatusDetails {
  if (
    status === "processing" &&
    processingStage === "ergonomics-processing"
  ) {
    return {
      label: "Obliczanie metryk",
      icon: LoaderCircle,
      animated: true,
      iconClass:
        "bg-cyan-400/10 text-cyan-300",
      badgeClass:
        "bg-cyan-400/10 text-cyan-300",
    };
  }

  if (
    status === "queued" &&
    processingStage === "ready-for-risk-assessment"
  ) {
    return {
      label: "Metryki gotowe",
      icon: CheckCircle2,
      animated: false,
      iconClass:
        "bg-emerald-400/10 text-emerald-300",
      badgeClass:
        "bg-emerald-400/10 text-emerald-300",
    };
  }

  if (
    status === "queued" &&
    processingStage === "ready-for-ergonomics"
  ) {
    return {
      label: "Poza gotowa",
      icon: CheckCircle2,
      animated: false,
      iconClass:
        "bg-emerald-400/10 text-emerald-300",
      badgeClass:
        "bg-emerald-400/10 text-emerald-300",
    };
  }

  switch (status) {
    case "uploading":
      return {
        label: "Przesyłanie",
        icon: LoaderCircle,
        animated: true,
        iconClass:
          "bg-cyan-400/10 text-cyan-300",
        badgeClass:
          "bg-cyan-400/10 text-cyan-300",
      };

    case "queued":
      return {
        label: "W kolejce",
        icon: Clock3,
        animated: false,
        iconClass:
          "bg-amber-400/10 text-amber-300",
        badgeClass:
          "bg-amber-400/10 text-amber-300",
      };

    case "processing":
      return {
        label: "Analiza w toku",
        icon: LoaderCircle,
        animated: true,
        iconClass:
          "bg-cyan-400/10 text-cyan-300",
        badgeClass:
          "bg-cyan-400/10 text-cyan-300",
      };

    case "completed":
      return {
        label: "Ukończona",
        icon: CheckCircle2,
        animated: false,
        iconClass:
          "bg-emerald-400/10 text-emerald-300",
        badgeClass:
          "bg-emerald-400/10 text-emerald-300",
      };

    case "failed":
      return {
        label: "Nieudana",
        icon: XCircle,
        animated: false,
        iconClass:
          "bg-red-400/10 text-red-300",
        badgeClass:
          "bg-red-400/10 text-red-300",
      };

    case "cancelled":
      return {
        label: "Anulowana",
        icon: XCircle,
        animated: false,
        iconClass:
          "bg-white/[0.06] text-slate-400",
        badgeClass:
          "bg-white/[0.06] text-slate-400",
      };

    default:
      return {
        label: "Robocza",
        icon: Clock3,
        animated: false,
        iconClass:
          "bg-white/[0.06] text-slate-400",
        badgeClass:
          "bg-white/[0.06] text-slate-400",
      };
  }
}

function formatBytes(
  bytes: number,
) {
  if (!Number.isFinite(bytes)) {
    return "Brak danych";
  }

  return `${(
    bytes /
    (1024 * 1024)
  ).toFixed(1)} MB`;
}

function formatDuration(
  value: number | string | null,
) {
  const seconds = Number(value);

  if (!Number.isFinite(seconds)) {
    return "Brak danych";
  }

  const totalSeconds =
    Math.max(0, Math.round(seconds));

  const minutes =
    Math.floor(totalSeconds / 60);

  const remainingSeconds =
    totalSeconds % 60;

  return `${minutes}:${String(
    remainingSeconds,
  ).padStart(2, "0")}`;
}

function formatDate(
  value: string,
) {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(value));
}

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-52 -top-40 size-[620px] rounded-full bg-emerald-500/[0.07] blur-[160px]" />

      <div className="absolute -right-52 top-[500px] size-[620px] rounded-full bg-cyan-500/[0.07] blur-[170px]" />

      <div
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.8) 1px, transparent 1px)",
          backgroundSize: "54px 54px",
        }}
      />
    </div>
  );
}
