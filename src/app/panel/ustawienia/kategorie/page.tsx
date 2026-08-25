import { Tags } from "lucide-react";
import { requireUser } from "@/lib/auth/access";
import { createCategory, updateCategory } from "./actions";

export const dynamic = "force-dynamic";
export default async function CategoriesPage({ searchParams }: { searchParams: Promise<{q?:string}> }) {
  const q=(await searchParams).q?.trim()??""; const {supabase}=await requireUser();
  let query=supabase.from("analysis_categories").select("id,name,group_name,description,is_active").order("group_name").order("name");
  if(q)query=query.or(`name.ilike.%${q.replace(/[,%()]/g," ")}%,group_name.ilike.%${q.replace(/[,%()]/g," ")}%`);
  const {data,error}=await query;
  return <div className="dashboard-page"><header className="flex items-center gap-3"><Tags className="size-7 text-violet-600"/><div><p className="dashboard-eyebrow">Słowniki</p><h1 className="dashboard-title mt-1">Kategorie analiz</h1><p className="dashboard-muted mt-1">Grupuj analizy bez usuwania historycznych powiązań.</p></div></header>
    <form className="dashboard-card p-4"><input name="q" defaultValue={q} placeholder="Szukaj nazwy lub grupy" className="ui-input"/></form>
    <form action={createCategory} className="dashboard-card grid gap-3 p-5 sm:grid-cols-2"><h2 className="font-bold sm:col-span-2">Nowa kategoria</h2><Field name="group_name" label="Grupa"/><Field name="name" label="Nazwa"/><Field name="description" label="Opis (opcjonalny)"/><button className="ui-button-primary">Dodaj kategorię</button></form>
    {error&&<p className="rounded-xl bg-red-50 p-4 text-red-800">Nie udało się pobrać kategorii.</p>}
    <section className="space-y-3">{(data??[]).map((item)=><form key={item.id} action={updateCategory} className="dashboard-card grid gap-3 p-4 sm:grid-cols-[1fr_1fr_2fr_auto]"><input type="hidden" name="id" value={item.id}/><input type="hidden" name="current_active" value={String(item.is_active)}/><Field name="group_name" label="Grupa" defaultValue={item.group_name}/><Field name="name" label="Nazwa" defaultValue={item.name}/><Field name="description" label="Opis" defaultValue={item.description??""}/><div className="flex items-end gap-2"><button name="intent" value="save" className="ui-button-secondary">Zapisz</button><button name="intent" value="toggle" className="ui-button-secondary text-sm">{item.is_active?"Dezaktywuj":"Aktywuj"}</button></div></form>)}</section>
  </div>;
}
function Field({name,label,defaultValue=""}:{name:string;label:string;defaultValue?:string}){return <label className="dashboard-field">{label}<input name={name} defaultValue={defaultValue} required={name!=="description"}/></label>;}
