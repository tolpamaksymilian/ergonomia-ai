import {
  CheckCircle2,
  Clock3,
  LoaderCircle,
} from "lucide-react";

import type { ProjectStageStatus } from "@/config/project-status";

const statusDetails = {
  completed: {
    label: "Gotowe",
    icon: CheckCircle2,
    className:
      "border-emerald-400/20 bg-emerald-400/10 text-emerald-200",
  },
  in_progress: {
    label: "W realizacji",
    icon: LoaderCircle,
    className:
      "border-cyan-400/20 bg-cyan-400/10 text-cyan-200",
  },
  planned: {
    label: "Planowane",
    icon: Clock3,
    className:
      "border-white/10 bg-white/[0.05] text-slate-400",
  },
} satisfies Record<
  ProjectStageStatus,
  {
    label: string;
    icon: typeof CheckCircle2;
    className: string;
  }
>;

export function FeatureStatusBadge({
  status,
}: {
  status: ProjectStageStatus;
}) {
  const details = statusDetails[status];
  const Icon = details.icon;

  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${details.className}`}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {details.label}
    </span>
  );
}
