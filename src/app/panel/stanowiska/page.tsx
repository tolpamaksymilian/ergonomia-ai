import { BriefcaseBusiness, MapPin, Plus } from "lucide-react";

import { WorkstationStatusAction } from "@/components/dashboard/workstation-status-action";
import { requireUser } from "@/lib/auth/access";
import { createWorkstation } from "../actions";

export const dynamic = "force-dynamic";

export default async function WorkstationsPage() {
  const { supabase } = await requireUser();
  const { data, error } = await supabase.from("workstations").select("id,name,code,description,department,area,is_active,created_at,analyses(count)").order("is_active", { ascending: false }).order("name");
  return <div className="dashboard-page">
    <header><p className="dashboard-eyebrow">Organizacja analiz</p><h1 className="dashboard-title mt-2">Stanowiska pracy</h1><p className="dashboard-muted mt-2">Miejsca i procesy poddawane analizie. Funkcje pracowników są zarządzane osobno przez administratora firmy.</p></header>
    <section className="grid gap-6 xl:grid-cols-[0.65fr_1.35fr]">
      <form action={createWorkstation} className="dashboard-card grid content-start gap-4 p-5"><h2 className="text-xl font-bold">Nowe stanowisko pracy</h2><label className="dashboard-field">Nazwa<input name="name" required placeholder="np. Linia montażowa 1" /></label><div className="grid gap-4 sm:grid-cols-2"><label className="dashboard-field">Kod<input name="code" /></label><label className="dashboard-field">Dział<input name="department" /></label></div><label className="dashboard-field">Obszar<input name="area" placeholder="np. Hala A" /></label><label className="dashboard-field">Opis<textarea name="description" rows={3} /></label><button className="ui-button-primary"><Plus className="size-4" />Dodaj stanowisko</button></form>
      <div className="space-y-3">{error ? <p className="dashboard-feedback dashboard-feedback-error">Nie udało się pobrać stanowisk.</p> : data?.map((item) => <article key={item.id} className="dashboard-card flex flex-col gap-4 p-5 sm:flex-row sm:items-center"><span className="grid size-11 shrink-0 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><BriefcaseBusiness className="size-5" /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="truncate font-bold">{item.name}</h2>{item.code && <span className="ui-chip">{item.code}</span>}</div><p className="mt-1 text-xs text-muted-foreground">{item.department || "Bez działu"}{item.area ? ` · ${item.area}` : ""} · {relationCount(item.analyses)} analiz</p>{item.description && <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{item.description}</p>}</div><div className="flex items-center gap-3"><span className={`dashboard-status ${item.is_active ? "dashboard-status-success" : "dashboard-status-neutral"}`}><MapPin className="size-3" />{item.is_active ? "Aktywne" : "Nieaktywne"}</span><WorkstationStatusAction id={item.id} active={item.is_active} /></div></article>)}{!error && !data?.length && <div className="dashboard-empty"><BriefcaseBusiness className="size-10" /><h3>Brak stanowisk pracy</h3><p>Dodaj pierwsze stanowisko, aby porządkować analizy.</p></div>}</div>
    </section>
  </div>;
}

function relationCount(value: unknown) { return Array.isArray(value) ? Number((value[0] as { count?: number } | undefined)?.count ?? 0) : 0; }
