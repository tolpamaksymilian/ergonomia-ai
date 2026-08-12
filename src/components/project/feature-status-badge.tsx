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
      "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/35 dark:text-emerald-300",
  },
  in_progress: {
    label: "W realizacji",
    icon: LoaderCircle,
    className:
      "border-orange-200 bg-orange-50 text-orange-800 dark:border-orange-800 dark:bg-orange-950/35 dark:text-orange-300",
  },
  planned: {
    label: "Planowane",
    icon: Clock3,
    className:
      "border-border bg-surface-muted text-muted-foreground",
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
