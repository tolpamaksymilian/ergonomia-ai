import { ShieldCheck } from "lucide-react";

import { AnalysisTypeSelector } from "@/components/analyses/analysis-type-selector";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function NewAnalysisPage() {
  const { user, supabase } = await requireUser();
  const [{ data: workstations }, { data: categories }] = await Promise.all([
    supabase.from("workstations").select("id,name,code").eq("is_active", true).order("name"),
    supabase.from("analysis_categories").select("id,name,group_name").eq("is_active", true).order("group_name").order("name"),
  ]);
  return <div className="dashboard-page max-w-6xl">
    <section className="rounded-3xl bg-gradient-to-br from-[#171a31] via-[#1d2040] to-violet-950 p-7 text-white shadow-xl sm:p-9"><span className="inline-flex items-center gap-2 rounded-full bg-white/8 px-3 py-1.5 text-xs font-bold text-violet-200"><ShieldCheck className="size-4" />Prywatne dane</span><h1 className="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">Utwórz nową analizę</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">Wybierz analizę ruchu z filmu albo zbuduj interaktywny projekt stanowiska na podstawie prywatnego zdjęcia.</p></section>
    <AnalysisTypeSelector userId={user.id} workstations={workstations ?? []} categories={categories ?? []} />
  </div>;
}
