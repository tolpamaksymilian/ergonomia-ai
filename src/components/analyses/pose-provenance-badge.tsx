"use client";

import { ChevronDown, Cpu, TriangleAlert } from "lucide-react";

export type PoseProvenance = {
  workerVersion: string | null;
  poseVersion: string | null;
  poseSchema: string | null;
  qualityProfile: string | null;
  requestedQualityProfile: string | null;
  effectiveQualityProfile: string | null;
  qualityProfileDegraded: boolean;
  degradationReason: string | null;
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
        {value.staleArtifact ? <TriangleAlert aria-hidden="true" className="size-3.5 text-red-300" /> : <Cpu aria-hidden="true" className="size-3.5 text-cyan-300" />}
        <span>{value.staleArtifact ? `STALE_ARTIFACT · ${summary}` : summary}</span>
        <ChevronDown aria-hidden="true" className="size-3.5 text-slate-500 transition group-open:rotate-180" />
      </summary>
      <dl className="mt-3 grid gap-x-5 gap-y-2 border-t border-white/10 pt-3 sm:grid-cols-2">
        <Datum label="Run ID" value={value.runId} />
        <Datum label="Artifact generation" value={value.artifactGenerationId} />
        <Datum label="Worker instance" value={value.workerInstanceId} />
        <Datum label="Pose schema" value={value.poseSchema} />
        <Datum label="Profil żądany" value={value.requestedQualityProfile} />
        <Datum label="Profil wykonany" value={value.effectiveQualityProfile} />
        {value.qualityProfileDegraded && <Datum label="Zmiana profilu" value={value.degradationReason ?? "jawnie oznaczona degradacja"} />}
        <Datum label="RTMW" value={value.primaryPoseModel ?? (assigned ? "ACTIVE" : null)} />
        <Datum label="TAR" value={expertLabel("temporal_pose_expert", value.temporalPoseExpert, value)} />
        <Datum label="TAP" value={expertLabel("trajectory_expert", value.trajectoryExpert, value)} />
        <Datum label="SAM2" value={modelExpertLabel("silhouette_expert", value)} />
        <Datum label="3D" value={modelExpertLabel("mesh_referee", value)} />
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

function expertLabel(kind: "temporal_pose_expert" | "trajectory_expert", name: string | null, value: PoseProvenance) {
  if (!name) return null;
  const usage = recordOrNull(value.modelUsage?.[kind]);
  const enabled = typeof usage?.enabled === "boolean" ? usage.enabled : value.temporalExpertsEnabled;
  const used = typeof usage?.used === "boolean" ? usage.used : value.temporalExpertsActuallyUsed;
  const frames = typeof usage?.frames === "number" ? usage.frames : value.temporalExpertFramesCount;
  const skipReason = typeof usage?.skip_reason === "string" ? usage.skip_reason : null;
  if (used) return `${name}: użyty${frames !== null ? ` · ${frames} kl.` : ""}`;
  if (skipReason) return `${name}: pominięty · ${skipReason}`;
  if (enabled) return `${name}: dostępny / oczekuje`;
  return `${name}: wyłączony`;
}

function modelExpertLabel(kind: "silhouette_expert" | "mesh_referee", value: PoseProvenance) {
  const usage = recordOrNull(value.modelUsage?.[kind]);
  if (!usage) return null;
  const name = typeof usage.model_name === "string"
    ? usage.model_name
    : typeof usage.name === "string"
      ? usage.name
      : kind === "silhouette_expert" ? "SAM 2.1" : "SAM 3D Body";
  const used = usage.used === true;
  const framesValue = kind === "silhouette_expert" ? usage.sam2_used_frames : usage.frames;
  const frames = typeof framesValue === "number" ? framesValue : null;
  const skipReason = typeof usage.skip_reason === "string" ? usage.skip_reason : null;
  if (used) return `${name}: użyty${frames !== null ? ` · ${frames} kl.` : ""}`;
  if (skipReason) return `${name}: N/A · ${skipReason}`;
  if (usage.available === true) return `${name}: dostępny / nieużyty`;
  return `${name}: N/A`;
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function formatDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("pl-PL", { dateStyle: "short", timeStyle: "medium" }).format(date);
}
