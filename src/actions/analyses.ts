"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireUser } from "@/lib/auth/access";

type DeleteAnalysisState = {
  status: "idle" | "error";
  message: string;
};

const DELETABLE_STATUSES = new Set([
  "draft",
  "queued",
  "completed",
  "failed",
  "cancelled",
]);

function isUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

export async function deleteAnalysisAction(
  _previousState: DeleteAnalysisState,
  formData: FormData,
): Promise<DeleteAnalysisState> {
  const rawAnalysisId = formData.get("analysisId");

  const analysisId =
    typeof rawAnalysisId === "string"
      ? rawAnalysisId.trim()
      : "";

  if (!isUuid(analysisId)) {
    return {
      status: "error",
      message: "Nieprawidłowy identyfikator analizy.",
    };
  }

  const {
    supabase,
    user,
    profile,
  } = await requireUser();

  const { data: analysis, error: analysisError } =
    await supabase
      .from("analyses")
      .select(`
        id,
        user_id,
        status,
        source_video_path
      `)
      .eq("id", analysisId)
      .maybeSingle();

  if (analysisError) {
    return {
      status: "error",
      message:
        `Nie udało się pobrać analizy: ${analysisError.message}`,
    };
  }

  if (!analysis) {
    return {
      status: "error",
      message:
        "Analiza nie istnieje albo nie masz do niej dostępu.",
    };
  }

  const isOwner =
    analysis.user_id === user.id;

  const isAdmin =
    profile?.role === "admin";

  if (!isOwner && !isAdmin) {
    return {
      status: "error",
      message:
        "Nie masz uprawnień do usunięcia tej analizy.",
    };
  }

  if (
    !DELETABLE_STATUSES.has(
      analysis.status,
    )
  ) {
    return {
      status: "error",
      message:
        analysis.status === "processing"
          ? "Nie można usunąć analizy podczas pracy workera."
          : "Nie można usunąć analizy podczas przesyłania filmu.",
    };
  }

  /*
   * Najpierw usuwamy fizyczny plik przez Storage API.
   */
  const { error: storageError } =
    await supabase.storage
      .from("analysis-videos")
      .remove([
        analysis.source_video_path,
      ]);

  if (storageError) {
    return {
      status: "error",
      message:
        `Nie udało się usunąć filmu: ${storageError.message}`,
    };
  }

  /*
   * Dopiero po usunięciu filmu usuwamy rekord analizy.
   */
  const { error: deleteError } =
    await supabase
      .from("analyses")
      .delete()
      .eq("id", analysisId)
      .eq("user_id", analysis.user_id);

  if (deleteError) {
    return {
      status: "error",
      message:
        `Film został usunięty, ale nie udało się usunąć rekordu analizy: ${deleteError.message}`,
    };
  }

  revalidatePath("/panel");
  revalidatePath("/panel/analizy");
  revalidatePath(
    `/panel/analizy/${analysisId}`,
  );

  redirect("/panel/analizy");
}