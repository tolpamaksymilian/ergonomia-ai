import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Clock3,
  ShieldCheck,
} from "lucide-react";

import type {
  RiskAssessmentSummary,
  RiskLevel,
} from "@/types/analysis";

type RiskAssessmentCardProps = {
  summary: RiskAssessmentSummary;
  completedAt: string | null;
};

const levelPresentation: Record<
  RiskLevel,
  {
    label: string;
    icon: typeof CheckCircle2;
    badgeClass: string;
  }
> = {
  low: {
    label: "Niskie",
    icon: CheckCircle2,
    badgeClass: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
  },
  moderate: {
    label: "Umiarkowane",
    icon: AlertTriangle,
    badgeClass: "border-amber-300/25 bg-amber-300/10 text-amber-200",
  },
  high: {
    label: "Wysokie",
    icon: AlertTriangle,
    badgeClass: "border-orange-400/25 bg-orange-400/10 text-orange-200",
  },
  critical: {
    label: "Bardzo wysokie",
    icon: AlertOctagon,
    badgeClass: "border-red-400/25 bg-red-400/10 text-red-200",
  },
  insufficient_data: {
    label: "Brak danych",
    icon: CircleHelp,
    badgeClass: "border-slate-400/20 bg-slate-400/10 text-slate-200",
  },
};

const zoneLabels: Record<string, string> = {
  neck: "Szyja",
  trunk: "Tułów",
  left_upper_limb: "Lewa kończyna górna",
  right_upper_limb: "Prawa kończyna górna",
  left_hand: "Lewa dłoń",
  right_hand: "Prawa dłoń",
};

const metricLabels: Record<string, string> = {
  trunk_inclination_deg: "Pochylenie tułowia",
  neck_flexion_deg: "Zgięcie szyi",
  left_upper_arm_elevation_deg: "Elewacja lewego ramienia",
  right_upper_arm_elevation_deg: "Elewacja prawego ramienia",
  left_elbow_flexion_deg: "Zgięcie lewego łokcia",
  right_elbow_flexion_deg: "Zgięcie prawego łokcia",
  left_forearm_inclination_deg: "Pochylenie lewego przedramienia",
  right_forearm_inclination_deg: "Pochylenie prawego przedramienia",
  left_wrist_flexion_deg: "Zgięcie lewego nadgarstka",
  right_wrist_flexion_deg: "Zgięcie prawego nadgarstka",
  left_hand_closure_ratio: "Zamknięcie lewej dłoni",
  right_hand_closure_ratio: "Zamknięcie prawej dłoni",
  left_pinch_distance_ratio: "Chwyt lewej dłoni",
  right_pinch_distance_ratio: "Chwyt prawej dłoni",
};

export function RiskAssessmentCard({
  summary,
  completedAt,
}: RiskAssessmentCardProps) {
  const presentation = levelPresentation[summary.overall_level];
  const LevelIcon = presentation.icon;
  const isDevelopmentProfile = summary.profile.status === "development";

  return (
    <section
      aria-labelledby="risk-assessment-heading"
      className="overflow-hidden rounded-[30px] border border-white/10 bg-slate-950/65"
    >
      <div className="grid gap-6 border-b border-border bg-gradient-to-br from-primary/[0.08] via-transparent to-transparent p-6 sm:p-8 lg:grid-cols-[1fr_auto] lg:items-start">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
            Techniczny screening ergonomiczny
          </p>
          <h2 id="risk-assessment-heading" className="mt-3 text-2xl font-semibold">
            Wynik Risk Engine V1
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            Transparentna klasyfikacja metryk i czasu ekspozycji według jawnego,
            wersjonowanego profilu. Wynik wspiera analizę i nie zastępuje oceny
            specjalisty.
          </p>
        </div>

        <div
          className={`inline-flex w-fit items-center gap-2 rounded-2xl border px-4 py-3 font-semibold ${presentation.badgeClass}`}
        >
          <LevelIcon className="size-5" aria-hidden="true" />
          {presentation.label}
        </div>
      </div>

      {summary.insufficient_data && (
        <div className="m-6 rounded-2xl border border-amber-300/20 bg-amber-300/[0.07] p-5 text-sm leading-6 text-amber-100/85 sm:m-8">
          Dostępne dane nie wystarczają do wiarygodnej klasyfikacji technicznej.
          Brak danych nie został potraktowany jako niski poziom.
        </div>
      )}

      <dl className="grid gap-3 p-6 sm:grid-cols-2 sm:p-8 lg:grid-cols-5">
          <TechnicalMetric
            label="Pokrycie poprawnymi danymi"
            value={formatPercent(summary.valid_metric_ratio)}
          />
          <TechnicalMetric
            label="Pokrycie oceny stref"
            value={formatPercent(summary.data_coverage)}
          />
          <TechnicalMetric label="Przetworzone klatki" value={String(summary.frame_count)} />
          <TechnicalMetric
            label="Wynik agregacji technicznej"
            value={formatScore(summary.overall_score)}
          />
          <TechnicalMetric
            label="Jakość danych"
            value={
              summary.insufficient_data
                ? "Niewystarczająca"
                : "Wystarczająca do klasyfikacji"
            }
          />
      </dl>

      <div className="grid gap-6 border-t border-white/[0.08] p-6 sm:p-8 lg:grid-cols-2">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-slate-100">
            <ShieldCheck className="size-5 text-primary" aria-hidden="true" />
            Profil oceny
          </h3>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <Detail label="Nazwa" value={summary.profile.profile_name} />
            <Detail label="Wersja" value={summary.profile.profile_version} />
            <Detail label="Identyfikator" value={summary.profile.profile_id} />
            <Detail label="Status" value={formatProfileStatus(summary.profile.status)} />
          </dl>

          {isDevelopmentProfile && (
            <p className="mt-4 rounded-2xl border border-amber-300/20 bg-amber-300/[0.06] p-4 text-sm leading-6 text-amber-100/80">
              Użyto profilu rozwojowego. Progi nie są profilem produkcyjnym ani
              metodą normatywną i wymagają zatwierdzenia przez kompetentnego
              specjalistę.
            </p>
          )}
        </div>

        <div>
          <h3 className="font-semibold text-slate-100">Najważniejsze wskazania</h3>
          {summary.highest_risk_zones.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {summary.highest_risk_zones.map((zone) => (
                <span
                  key={zone}
                  className="rounded-full border border-orange-300/20 bg-orange-300/[0.07] px-3 py-1.5 text-xs font-medium text-orange-100"
                >
                  {zoneLabels[zone] ?? zone}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-500">
              Brak stref możliwych do wyróżnienia na podstawie dostępnego
              podsumowania.
            </p>
          )}

          {summary.dominant_metrics.length > 0 && (
            <ul className="mt-5 space-y-2 text-sm text-slate-300">
              {summary.dominant_metrics.map((metric) => (
                <li
                  key={metric.metric_name}
                  className="flex items-center justify-between gap-4 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3"
                >
                  <span>{metricLabels[metric.metric_name] ?? metric.metric_name}</span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {levelPresentation[metric.level].label}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-white/[0.08] px-6 py-5 text-xs text-slate-500 sm:px-8">
        <span>{summary.key_frames_count} kandydatów kluczowych klatek</span>
        <span>{summary.enabled_metric_count} aktywnych metryk</span>
        {completedAt && (
          <span className="inline-flex items-center gap-1.5">
            <Clock3 className="size-3.5" aria-hidden="true" />
            Zakończono {formatDate(completedAt)}
          </span>
        )}
      </div>
    </section>
  );
}

function TechnicalMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
      <dt className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{label}</dt>
      <dd className="mt-2 font-semibold text-slate-100">{value}</dd>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
      <dt className="text-[10px] uppercase tracking-[0.14em] text-slate-600">{label}</dt>
      <dd className="mt-1 break-words text-slate-300">{value}</dd>
    </div>
  );
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("pl-PL", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatScore(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "Brak danych";
  return new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 }).format(value);
}

function formatProfileStatus(status: RiskAssessmentSummary["profile"]["status"]) {
  return {
    development: "Rozwojowy",
    draft: "Szkic",
    approved: "Zatwierdzony",
    archived: "Archiwalny",
  }[status];
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(value));
}
