"use client";

import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";

export function AnalysesAutoRefresh({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!enabled) return;
    const intervalId = window.setInterval(() => router.refresh(), 5000);
    return () => window.clearInterval(intervalId);
  }, [enabled, router]);

  return (
    <button
      type="button"
      onClick={() => router.refresh()}
      className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-300 transition hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
    >
      <RefreshCw className="size-3.5" />
      Odśwież
    </button>
  );
}
