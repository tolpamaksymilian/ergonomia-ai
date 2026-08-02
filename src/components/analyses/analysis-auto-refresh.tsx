"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

type AnalysisAutoRefreshProps = {
  enabled: boolean;
};

export function AnalysisAutoRefresh({
  enabled,
}: AnalysisAutoRefreshProps) {
  const router = useRouter();

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = window.setInterval(() => {
      router.refresh();
    }, 5000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, router]);

  return null;
}