import {
  CheckCircle2,
  Clock3,
  LoaderCircle,
} from "lucide-react";

import { FeatureStatusBadge } from "@/components/project/feature-status-badge";
import {
  calculateProjectProgress,
  type ProjectStage,
  type ProjectStageStatus,
} from "@/config/project-status";

const groups: Array<{
  status: ProjectStageStatus;
  title: string;
  description: string;
  icon: typeof CheckCircle2;
  accent: string;
}> = [
  {
    status: "completed",
    title: "Gotowe",
    description: "Elementy działające w aktualnej wersji systemu.",
    icon: CheckCircle2,
    accent: "text-emerald-300",
  },
  {
    status: "in_progress",
    title: "W realizacji",
    description: "Najbliższe prace łączące istniejące moduły.",
    icon: LoaderCircle,
    accent: "text-cyan-300",
  },
  {
    status: "planned",
    title: "Planowane",
    description: "Funkcje, których aplikacja jeszcze nie udostępnia.",
    icon: Clock3,
    accent: "text-slate-400",
  },
];

export function ProjectRoadmap({
  stages,
  showProgress = false,
}: {
  stages: readonly ProjectStage[];
  showProgress?: boolean;
}) {
  const progress = calculateProjectProgress(stages);

  return (
    <div>
      {showProgress && (
        <div className="mb-6 rounded-[26px] border border-white/10 bg-slate-950/45 p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Postęp wynikający z etapów
              </p>
              <p className="mt-2 text-4xl font-bold text-white">
                {progress}%
              </p>
            </div>
            <p className="max-w-xl text-sm leading-6 text-slate-400">
              Gotowe etapy liczą się jako 1, realizowane jako 0,5,
              a planowane jako 0. Wartość nie jest zapisywana w bazie.
            </p>
          </div>
          <div
            className="mt-5 h-2 overflow-hidden rounded-full bg-white/10"
            role="progressbar"
            aria-label="Postęp rozwoju systemu"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-3">
        {groups.map((group) => {
          const items = stages.filter(
            (stage) => stage.status === group.status,
          );
          const Icon = group.icon;

          return (
            <section
              key={group.status}
              className="min-w-0 rounded-[28px] border border-white/10 bg-white/[0.03] p-6"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-3">
                  <Icon
                    className={`mt-0.5 size-6 shrink-0 ${group.accent}`}
                    aria-hidden="true"
                  />
                  <div>
                    <h3 className="text-xl font-semibold text-white">
                      {group.title}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-slate-500">
                      {group.description}
                    </p>
                  </div>
                </div>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-semibold text-slate-300">
                  {items.length}
                </span>
              </div>

              <ul className="mt-6 space-y-3">
                {items.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <p className="min-w-0 flex-1 break-words font-semibold text-slate-100">
                        {item.title}
                      </p>
                      <FeatureStatusBadge status={item.status} />
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-500">
                      {item.description}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
