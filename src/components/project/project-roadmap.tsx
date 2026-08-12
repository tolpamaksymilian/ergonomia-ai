import { ChevronDown } from "lucide-react";

import { FeatureStatusBadge } from "@/components/project/feature-status-badge";
import {
  calculateProjectProgress,
  countProjectStages,
  projectStageGroups,
  type ProjectStage,
} from "@/config/project-status";

export function ProjectRoadmap({
  stages,
  showProgress = false,
}: {
  stages: readonly ProjectStage[];
  showProgress?: boolean;
}) {
  const progress = calculateProjectProgress(stages);
  const counts = countProjectStages(stages);

  return (
    <div>
      {showProgress && (
        <div className="ui-card mb-6 p-5 sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Postęp projektu</p>
              <p className="mt-2 text-4xl font-bold text-foreground">{progress}%</p>
            </div>
            <p className="text-sm text-slate-400">
              {counts.completed} gotowych · {counts.inProgress} w realizacji · {counts.planned} planowanych
            </p>
          </div>
          <div className="mt-5 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label="Postęp rozwoju systemu" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
            <div className="h-full rounded-full bg-primary" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {projectStageGroups.map((group) => {
          const items = stages.filter((stage) => stage.group === group.id);
          const completed = items.filter((stage) => stage.status === "completed").length;

          return (
            <details
              key={group.id}
              open={group.id === "risk"}
              className="group ui-card min-w-0 p-5 open:bg-surface-muted"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-semibold text-foreground">{group.label}</h3>
                  <p className="mt-1 text-xs text-slate-500">{group.description}</p>
                </div>
                <span className="flex shrink-0 items-center gap-2 text-xs text-slate-400">
                  {completed}/{items.length}
                  <ChevronDown className="size-4 transition group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                </span>
              </summary>

              <ul className="mt-5 space-y-2 border-t border-border pt-4">
                {items.map((item) => (
                  <li key={item.id} className="rounded-lg border border-border bg-surface-muted p-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-foreground">{item.title}</p>
                      <FeatureStatusBadge status={item.status} />
                    </div>
                    <p className="mt-1.5 text-xs leading-5 text-slate-500">{item.description}</p>
                  </li>
                ))}
              </ul>
            </details>
          );
        })}
      </div>
    </div>
  );
}
