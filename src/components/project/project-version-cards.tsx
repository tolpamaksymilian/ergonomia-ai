import {
  BrainCircuit,
  FileText,
  MonitorCog,
  Ruler,
  ShieldCheck,
  Tag,
} from "lucide-react";

import { projectStatus } from "@/config/project-status";
import { release } from "@/config/release";

const versions = [
  {
    label: "Wersja aplikacji",
    value: release.version,
    icon: Tag,
  },
  {
    label: "Pose Pipeline",
    value: projectStatus.versions.posePipeline,
    icon: BrainCircuit,
  },
  {
    label: "Metrics Engine",
    value: projectStatus.versions.ergonomicsMetricsEngine,
    icon: Ruler,
  },
  {
    label: "Risk Engine",
    value: projectStatus.versions.riskEngine,
    icon: ShieldCheck,
  },
  {
    label: "Tryb workerów",
    value: projectStatus.versions.workerMode,
    icon: MonitorCog,
  },
  {
    label: "Raport końcowy",
    value: projectStatus.versions.finalReport,
    icon: FileText,
  },
] as const;

export function ProjectVersionCards() {
  return (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
      {versions.map((version) => {
        const Icon = version.icon;

        return (
          <div
            key={version.label}
            className="min-w-0 rounded-[22px] border border-white/10 bg-white/[0.035] p-5"
          >
            <Icon className="size-5 text-cyan-300" aria-hidden="true" />
            <dt className="mt-4 text-[10px] uppercase tracking-[0.16em] text-slate-500">
              {version.label}
            </dt>
            <dd className="mt-2 break-words font-semibold text-white">
              {version.value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
