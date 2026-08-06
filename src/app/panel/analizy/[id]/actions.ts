"use server";

import { revalidatePath } from "next/cache";

import { requireAdmin } from "@/lib/auth/access";

export async function retryFailedAnalysisStage(analysisId: string) {
  const { supabase } = await requireAdmin();
  const { data, error } = await supabase.rpc("retry_failed_analysis_stage", {
    p_analysis_id: analysisId,
  });
  if (error || data !== true) {
    throw new Error("Nie udało się bezpiecznie ponowić etapu analizy.");
  }
  revalidatePath(`/panel/analizy/${analysisId}`);
  revalidatePath("/panel/analizy");
  revalidatePath("/admin");
}
