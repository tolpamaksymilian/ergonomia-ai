import { ArrowDown, ArrowRight } from "lucide-react";

import { FeatureStatusBadge } from "@/components/project/feature-status-badge";
import type { ProjectStage } from "@/config/project-status";

export function PipelineOverview({
  stages,
  compact = false,
}: {
  stages: readonly ProjectStage[];
  compact?: boolean;
}) {
  return (
    <ol
      aria-label="Etapy pipeline'u Ergonomia AI"
      className={
        compact
          ? "grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
          : "grid gap-4 md:grid-cols-2 xl:grid-cols-3"
      }
    >
      {stages.map((stage, index) => (
        <li key={stage.id} className="relative min-w-0">
          <article className="h-full rounded-[24px] border border-white/10 bg-white/[0.035] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.07] font-mono text-sm font-bold text-cyan-200">
                {String(index + 1).padStart(2, "0")}
              </span>
              <FeatureStatusBadge status={stage.status} />
            </div>

            <h3 className="mt-5 break-words text-lg font-semibold text-white">
              {stage.title}
            </h3>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              {stage.description}
            </p>
          </article>

          {index < stages.length - 1 && (
            <>
              <ArrowDown
                className="mx-auto my-1 size-4 text-slate-700 sm:hidden"
                aria-hidden="true"
              />
              {index % 3 !== 2 && (
                <ArrowRight
                  className="absolute -right-3.5 top-1/2 z-10 hidden size-3.5 -translate-y-1/2 text-cyan-400/35 xl:block"
                  aria-hidden="true"
                />
              )}
            </>
          )}
        </li>
      ))}
    </ol>
  );
}
