"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Clock3, LoaderCircle, XCircle } from "lucide-react";

import { getAnalysisStatusDefinition } from "@/config/analysis-status";

type LiveState = {
  status: string;
  progress: number;
  processing_stage: string | null;
  report_path: string | null;
  updated_at?: string;
};

type AnalysisLiveStatusProps = {
  analysisId: string;
  initialState: LiveState;
};

export function AnalysisLiveStatus({ analysisId, initialState }: AnalysisLiveStatusProps) {
  const router = useRouter();
  const [state, setState] = useState(initialState);
  const transitionRef = useRef(
    `${initialState.status}:${initialState.processing_stage ?? ""}:${Boolean(initialState.report_path)}`,
  );
  const definition = getAnalysisStatusDefinition(state.status, state.processing_stage);

  useEffect(() => {
    if (!definition.active) return;
    let cancelled = false;
    const refreshStatus = async () => {
      try {
        const response = await fetch(`/api/analyses/${analysisId}/status`, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (!response.ok || cancelled) return;
        const next = (await response.json()) as LiveState;
        if (cancelled) return;
        setState(next);
        const transition = `${next.status}:${next.processing_stage ?? ""}:${Boolean(next.report_path)}`;
        if (transition !== transitionRef.current) {
          transitionRef.current = transition;
          router.refresh();
        }
      } catch {
        // A temporary polling failure must not replace the current safe UI state.
      }
    };
    const intervalId = window.setInterval(refreshStatus, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [analysisId, definition.active, router]);

  const visual = {
    neutral: { icon: Clock3, box: "border-white/10 bg-white/[0.035]", iconClass: "bg-white/[0.06] text-slate-400", text: "text-slate-300" },
    queued: { icon: Clock3, box: "border-amber-300/20 bg-amber-400/[0.06]", iconClass: "bg-amber-400/10 text-amber-300", text: "text-amber-300" },
    active: { icon: LoaderCircle, box: "border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950/25", iconClass: "bg-brand-soft text-primary", text: "text-accent-foreground" },
    success: { icon: CheckCircle2, box: "border-emerald-400/20 bg-emerald-400/[0.06]", iconClass: "bg-emerald-400/10 text-emerald-300", text: "text-emerald-300" },
    error: { icon: XCircle, box: "border-red-400/20 bg-red-400/[0.06]", iconClass: "bg-red-400/10 text-red-300", text: "text-red-300" },
  }[definition.visualType];
  const Icon = visual.icon;
  const progress = Math.max(0, Math.min(100, Number(state.progress) || 0));

  return (
    <aside className={`rounded-[30px] border p-7 ${visual.box}`} aria-live="polite">
      <div className={`flex size-12 items-center justify-center rounded-2xl ${visual.iconClass}`}>
        <Icon className={`size-6 ${definition.visualType === "active" ? "animate-spin motion-reduce:animate-none" : ""}`} />
      </div>
      <p className="mt-6 text-xs uppercase tracking-[0.18em] text-slate-500">Aktualny status</p>
      <p className={`mt-2 text-2xl font-bold ${visual.text}`}>{definition.label}</p>
      <p className="mt-3 text-sm leading-6 text-slate-400">{definition.description}</p>
      <div className="mt-6 flex items-center justify-between text-xs">
        <span className="text-slate-500">Postęp pipeline’u</span>
        <span className={`font-semibold ${visual.text}`}>{progress}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
      </div>
      {definition.active && <p className="mt-4 text-xs text-slate-600">Status odświeża się automatycznie.</p>}
    </aside>
  );
}
