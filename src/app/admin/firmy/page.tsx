import Link from "next/link";
import { Building2, MapPin, Plus, Search, UsersRound } from "lucide-react";

import { requireAdmin } from "@/lib/auth/access";
import { createCompany } from "../actions";

export const dynamic = "force-dynamic";
export default async function CompaniesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const q = (await searchParams).q?.trim().slice(0, 100) ?? "";
  const { supabase } = await requireAdmin();
  let query = supabase.from("companies").select("id,name,legal_name,city,status,created_at,profiles(count),company_positions(count)").order("name");
  if (q) query = query.or(`name.ilike.%${safe(q)}%,legal_name.ilike.%${safe(q)}%,city.ilike.%${safe(q)}%`);
  const { data, error } = await query;
  return <div className="dashboard-page"><PageHeader eyebrow="Organizacje" title="Firmy" description="Centralne miejsce zarządzania zespołami, stanowiskami i dostępem." />
    <section className="grid gap-6 xl:grid-cols-[0.65fr_1.35fr]">
      <form action={createCompany} className="dashboard-card grid content-start gap-4 p-5"><div><p className="dashboard-eyebrow">Nowa firma</p><h2 className="mt-1 text-xl font-bold">Dodaj organizację</h2></div><Field name="name" label="Nazwa firmy" required /><Field name="legal_name" label="Pełna nazwa prawna" /><div className="grid gap-4 sm:grid-cols-2"><Field name="tax_id" label="NIP / identyfikator" /><Field name="city" label="Miasto" /></div><Field name="address" label="Adres" /><button className="ui-button-primary"><Plus className="size-4" />Utwórz firmę</button></form>
      <div className="space-y-4"><form className="dashboard-card flex items-center gap-3 p-3"><Search className="ml-2 size-4 text-muted-foreground" /><input name="q" defaultValue={q} placeholder="Szukaj firmy, miasta lub nazwy prawnej" className="min-h-10 flex-1 bg-transparent outline-none" /><button className="ui-button-secondary min-h-10 py-2 text-sm">Szukaj</button></form>
        {error ? <ErrorState /> : data?.length ? <div className="grid gap-4 md:grid-cols-2">{data.map((company) => <Link key={company.id} href={`/admin/firmy/${company.id}`} className="dashboard-card group p-5 transition hover:-translate-y-0.5 hover:border-violet-400"><div className="flex items-start justify-between"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/10 text-violet-600"><Building2 className="size-5" /></span><span className="dashboard-status border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">{company.status === "active" ? "Aktywna" : "Nieaktywna"}</span></div><h2 className="mt-5 truncate text-lg font-bold group-hover:text-violet-600">{company.name}</h2><p className="mt-1 truncate text-sm text-muted-foreground">{company.legal_name || "Brak nazwy prawnej"}</p><div className="mt-5 flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground"><span className="flex items-center gap-1.5"><UsersRound className="size-4" />{relationCount(company.profiles)} użytkowników</span><span className="flex items-center gap-1.5"><MapPin className="size-4" />{company.city || "Brak miasta"}</span></div></Link>)}</div> : <EmptyState />}
      </div>
    </section>
  </div>;
}
function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) { return <header><p className="dashboard-eyebrow">{eyebrow}</p><h1 className="dashboard-title mt-2">{title}</h1><p className="dashboard-muted mt-2">{description}</p></header>; }
function Field({ name, label, required = false }: { name: string; label: string; required?: boolean }) { return <label className="dashboard-field">{label}<input name={name} required={required} /></label>; }
function relationCount(value: unknown) { return Array.isArray(value) ? Number((value[0] as { count?: number } | undefined)?.count ?? 0) : 0; }
function safe(value: string) { return value.replace(/[,%()]/g, " "); }
function ErrorState() { return <div className="dashboard-card border-red-200 p-8 text-center text-red-700">Nie udało się pobrać firm. Sprawdź, czy wdrożono migrację dashboardu.</div>; }
function EmptyState() { return <div className="dashboard-card p-12 text-center"><Building2 className="mx-auto size-10 text-muted-foreground" /><h2 className="mt-4 font-bold">Brak firm</h2><p className="dashboard-muted mt-2">Utwórz pierwszą organizację formularzem obok.</p></div>; }
