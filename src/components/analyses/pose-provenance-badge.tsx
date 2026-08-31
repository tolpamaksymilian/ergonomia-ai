"use client";

import { ChevronDown, Cpu, TriangleAlert } from "lucide-react";

export type PoseProvenance = {
  workerVersion: string | null;
  poseVersion: string | null;
  poseSchema: string | null;
  qualityProfile: string | null;
  workerInstanceId: string | null;
  workerStartedAt: string | null;
  processingStartedAt: string | null;
  processingFinishedAt: string | null;
  buildId: string | null;
  runId: string | null;
  artifactGenerationId: string | null;
  primaryPoseModel: string | null;
  temporalPoseExpert: string | null;
  trajectoryExpert: string | null;
  handModel: string | null;
  temporalExpertsEnabled: boolean | null;
  temporalExpertsActuallyUsed: boolean | null;
  temporalExpertFramesCount: number | null;
  modelUsage: Record<string, unknown> | null;
  staleArtifact?: boolean;
};

export function PoseProvenanceBadge({ value, active = false }: { value: PoseProvenance; active?: boolean }) {
  const assigned = Boolean(value.workerVersion && value.poseVersion);
  const shortPose = value.poseVersion?.replace(/^pose-v/, "") ?? null;
  const identity = assigned
    ? `Worker ${value.workerVersion} · Pose ${shortPose} · ${value.qualityProfile ?? "profil nieznany"}`
    : "Worker jeszcze nieprzypisany";
  const summary = active && assigned ? `Analizuje: ${identity}` : identity;

  return (
    <details className={`group rounded-xl border px-3 py-2 text-xs ${value.staleArtifact ? "border-red-300/30 bg-red-300/[0.07]" : "border-cyan-300/20 bg-cyan-300/[0.06]"}`}>
      <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
        {value.staleArtifact ? <TriangleAlert className="size-3.5 text-red-300" /> : <Cpu className="size-3.5 text-cyan-300" />}
        <span>{value.staleArtifact ? `STALE_ARTIFACT · ${summary}` : summary}</span>
        <ChevronDown className="size-3.5 text-slate-500 transition group-open:rotate-180" />
      </summary>
      <dl className="mt-3 grid gap-x-5 gap-y-2 border-t border-white/10 pt-3 sm:grid-cols-2">
        <Datum label="Run ID" value={value.runId} />
        <Datum label="Artifact generation" value={value.artifactGenerationId} />
        <Datum label="Worker instance" value={value.workerInstanceId} />
        <Datum label="Pose schema" value={value.poseSchema} />
        <Datum label="RTMW" value={value.primaryPoseModel ?? (assigned ? "ACTIVE" : null)} />
        <Datum label="TAR" value={expertLabel(value.temporalPoseExpert, value.temporalExpertsEnabled, value.temporalExpertsActuallyUsed, value.temporalExpertFramesCount)} />
        <Datum label="TAP" value={expertLabel(value.trajectoryExpert, value.temporalExpertsEnabled, value.temporalExpertsActuallyUsed, value.temporalExpertFramesCount)} />
        <Datum label="Dłonie" value={value.handModel} />
        <Datum label="Build" value={value.buildId} />
        <Datum label="Start przetwarzania" value={formatDate(value.processingStartedAt)} />
        <Datum label="Koniec przetwarzania" value={formatDate(value.processingFinishedAt)} />
      </dl>
    </details>
  );
}

function Datum({ label, value }: { label: string; value: string | null }) {
  return <div className="min-w-0"><dt className="text-slate-500">{label}</dt><dd className="mt-0.5 break-all text-slate-300">{value ?? "—"}</dd></div>;
}

function expertLabel(name: string | null, enabled: boolean | null, used: boolean | null, frames: number | null) {
  if (!name) return null;
  if (!enabled) return `${name}: wyłączony`;
  if (!used) return `${name}: aktywny, nieużyty`;
  return `${name}: użyty${frames !== null ? ` · ${frames} kl.` : ""}`;
}

function formatDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("pl-PL", { dateStyle: "short", timeStyle: "medium" }).format(date);
}
