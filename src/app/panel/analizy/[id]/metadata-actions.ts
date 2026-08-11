"use server";

import { revalidatePath } from "next/cache";

import { requireUser } from "@/lib/auth/access";
import { normalizeAnalysisContext } from "@/types/analysis-context";

export async function saveAnalysisMetadata(formData: FormData): Promise<void> {
  const analysisId = required(formData, "analysis_id", 36);
  const { supabase } = await requireUser();
  const workstationId = optional(formData, "workstation_id", 36);
  const context = normalizeAnalysisContext({
    process_name: optional(formData, "process_name", 120),
    activity_description: optional(formData, "activity_description", 2000),
    department: optional(formData, "department", 120),
    area: optional(formData, "area", 120),
    line_machine: optional(formData, "line_machine", 120),
    notes: optional(formData, "notes", 4000),
    author_name: optional(formData, "author_name", 120),
  });
  const title = required(formData, "title", 120);
  if (title.length < 3) throw new Error("Nazwa analizy musi mieć co najmniej 3 znaki.");
  const { data: analysis, error } = await supabase.from("analyses").update({
    title,
    description: optional(formData, "description", 2000),
    workstation_id: workstationId,
    analysis_date: optional(formData, "analysis_date", 10),
    analysis_context: context,
  }).eq("id", analysisId).select("id").maybeSingle();
  if (error || !analysis) throw new Error("Nie udało się zapisać informacji o analizie.");

  const categoryIds = formData.getAll("category_id").filter((value): value is string => typeof value === "string" && /^[0-9a-f-]{36}$/i.test(value));
  const { error: linkError } = await supabase.rpc("set_analysis_categories", { p_analysis_id: analysisId, p_category_ids: categoryIds });
  if (linkError) throw new Error("Nie udało się atomowo przypisać wybranych kategorii.");
  revalidatePath(`/panel/analizy/${analysisId}`);
  revalidatePath("/panel/analizy");
}

export async function createWorkstation(formData: FormData): Promise<void> {
  const analysisId = required(formData, "analysis_id", 36);
  const { supabase, user } = await requireUser();
  const { error } = await supabase.from("workstations").insert({ user_id: user.id, name: required(formData, "name", 120), code: optional(formData, "code", 80), department: optional(formData, "department", 120), area: optional(formData, "area", 120) });
  if (error) throw new Error(error.code === "23505" ? "Takie stanowisko już istnieje." : "Nie udało się utworzyć stanowiska.");
  revalidatePath(`/panel/analizy/${analysisId}`);
}

function required(data: FormData, name: string, max: number) { const value = optional(data, name, max); if (!value) throw new Error(`Pole ${name} jest wymagane.`); return value; }
function optional(data: FormData, name: string, max: number) { const value = data.get(name); return typeof value === "string" && value.trim() ? value.trim().slice(0, max) : null; }
