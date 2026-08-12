"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, CircleDot, LoaderCircle, Play, RotateCcw } from "lucide-react";

import { pipelineAlerts, type PipelineWatchdogCode } from "@/config/pipeline-alerts";
import type { PipelineHealth } from "@/lib/pipeline-health";
import { classifyPipelineWatchdog } from "@/lib/pipeline-watchdog";

type AnalysisState = {
  id: string;
  status: string;
  progress: number;
  processing_stage: string | null;
  updated_at: string | null;
  heartbeat_at?: string | null;
  error_code?: string | null;
};

type HealthResponse = {
  health: PipelineHealth;
  analysis: AnalysisState | null;
  control_allowed: boolean;
};

export function PipelineSystemStatus({ initialAnalysis }: { initialAnalysis: AnalysisState }) {
  const [response, setResponse] = useState<HealthResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const result = await fetch(`/api/system/pipeline-health?analysisId=${encodeURIComponent(initialAnalysis.id)}`, {
      cache: "no-store", headers: { Accept: "application/json" },
    });
    if (result.status === 404) return;
    if (!result.ok) throw new Error("health_unavailable");
    setResponse(await result.json() as HealthResponse);
  }, [initialAnalysis.id]);

  useEffect(() => {
    let cancelled = false;
    const update = async () => { try { if (!cancelled) await refresh(); } catch { /* zachowaj ostatni bezpieczny stan */ } };
    void update();
    const interval = window.setInterval(update, 5000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, [refresh]);

  const analysis = response?.analysis ?? initialAnalysis;
  const watchdog = useMemo<PipelineWatchdogCode | null>(() => response
    ? classifyPipelineWatchdog(analysis, response.health)
    : null, [analysis, response]);
  if (!response || !watchdog) return null;
  const alert = pipelineAlerts[watchdog];
  const health = response.health;
  const isQuiet = watchdog === "PROCESSING" || watchdog === "QUEUE_OK" || watchdog === "COMPLETED";
  const canRestart = response.control_allowed && ["WORKER_OFFLINE", "CRASH_LOOP", "DEGRADED", "STALLED"].includes(watchdog);
  const tone = {
    neutral: "border-white/10 bg-white/[0.025]",
    info: "border-border bg-card",
    warning: "border-amber-300/20 bg-amber-300/[0.045]",
    error: "border-red-300/20 bg-red-300/[0.045]",
    success: "border-emerald-300/15 bg-emerald-300/[0.035]",
  }[alert.tone];
  const StatusIcon = watchdog === "PROCESSING" ? LoaderCircle : watchdog === "COMPLETED" ? CheckCircle2 : ["WORKER_OFFLINE", "CRASH_LOOP", "DEGRADED", "STALLED", "FAILED"].includes(watchdog) ? AlertTriangle : CircleDot;

  async function control(action: "start" | "restart") {
    setPending(true); setControlError(null);
    try {
      const result = await fetch("/api/system/pipeline-health", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) });
      if (!result.ok) throw new Error("Nie udało się uruchomić lokalnego Workera.");
      await refresh();
    } catch (error) {
      setControlError(error instanceof Error ? error.message : "Sterowanie Workerem nie powiodło się.");
    } finally { setPending(false); }
  }

  const cuda = health.preflight.find((item) => item.code === "CUDA");
  const ffmpeg = health.preflight.find((item) => item.code === "FFMPEG");
  return (
    <section className={`mt-4 rounded-2xl border p-4 ${tone}`} aria-labelledby="pipeline-system-status-title" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.06]">
            <StatusIcon className={`size-4 ${watchdog === "PROCESSING" ? "animate-spin motion-reduce:animate-none" : ""}`} aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Stan systemu analizy</p>
            <h2 id="pipeline-system-status-title" className="mt-1 font-semibold text-slate-100">{alert.title}</h2>
            <p className="mt-1 text-sm leading-5 text-slate-400">{alert.description}</p>
          </div>
        </div>
        {canRestart && <button type="button" disabled={pending} onClick={() => void control(watchdog === "WORKER_OFFLINE" && health.supervisor_pid === null ? "start" : "restart")} className="ui-button-secondary min-h-10 text-sm">
          {watchdog === "WORKER_OFFLINE" && health.supervisor_pid === null ? <Play className="size-4" /> : <RotateCcw className="size-4" />}
          {pending ? "Uruchamianie…" : watchdog === "WORKER_OFFLINE" && health.supervisor_pid === null ? "Uruchom Worker" : "Uruchom ponownie Worker"}
        </button>}
      </div>
      {!isQuiet && <details className="mt-4 border-t border-white/[0.07] pt-3 text-xs text-slate-500">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-muted-foreground">Szczegóły techniczne <ChevronDown className="size-3" /></summary>
        <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <SystemDatum label="Worker" value={health.status === "online" ? "Online" : health.status} />
          <SystemDatum label="Pipeline" value={health.state} />
          <SystemDatum label="Aktualny etap" value={analysis.processing_stage ?? "—"} />
          <SystemDatum label="Ostatnia aktywność" value={relativeTime(health.last_heartbeat_at)} />
          <SystemDatum label="GPU" value={cuda?.message ?? (health.preflight_status === "UNKNOWN" ? "Brak preflight" : "Niedostępne")} />
          <SystemDatum label="FFmpeg" value={ffmpeg?.status === "OK" ? "Dostępny" : "Niedostępny"} />
          <SystemDatum label="Kod" value={health.last_error?.code ?? analysis.error_code ?? watchdog} />
          <SystemDatum label="Restarty" value={String(health.restart_count)} />
        </dl>
        {health.preflight.some((item) => item.status === "ERROR") && <ul className="mt-3 space-y-1 rounded-lg bg-slate-950/25 p-3 text-slate-400">
          {health.preflight.filter((item) => item.status === "ERROR").map((item) => <li key={item.code}><span className="font-semibold text-slate-300">{item.code}:</span> {item.message}</li>)}
        </ul>}
      </details>}
      {controlError && <p className="mt-3 text-xs text-red-200">{controlError}</p>}
    </section>
  );
}

function SystemDatum({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-lg bg-slate-950/25 p-2.5"><dt>{label}</dt><dd className="mt-1 break-words font-medium text-slate-300">{value}</dd></div>;
}

function relativeTime(value: string | null) {
  if (!value) return "Brak heartbeat";
  const seconds = Math.max(0, Math.round((Date.now() - Date.parse(value)) / 1000));
  if (!Number.isFinite(seconds)) return "Nieznana";
  return seconds < 60 ? `${seconds} s temu` : `${Math.floor(seconds / 60)} min temu`;
}
