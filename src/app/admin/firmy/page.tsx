import Link from "next/link";
import { ArrowRight, Building2, Plus, Search } from "lucide-react";

import { requireAdmin } from "@/lib/auth/access";
import { createCompany } from "../actions";

export const dynamic = "force-dynamic";

export default async function CompaniesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const q = (await searchParams).q?.trim().slice(0, 100) ?? "";
  const { supabase } = await requireAdmin();
  let query = supabase.from("companies").select("id,name,legal_name,city,status,created_at,profiles(id,full_name,company_role,analyses(count)),company_positions(count)").order("name");
  if (q) query = query.or(`name.ilike.%${safe(q)}%,legal_name.ilike.%${safe(q)}%,city.ilike.%${safe(q)}%`);
  const { data, error } = await query;

  return <div className="dashboard-page">
    <header><p className="dashboard-eyebrow">Organizacje</p><h1 className="dashboard-title mt-2">Firmy</h1><p className="dashboard-muted mt-2">Centralny przegląd administratorów, zespołów, stanowisk i analiz.</p></header>
    <section className="grid gap-6 xl:grid-cols-[0.55fr_1.45fr]">
      <form action={createCompany} className="dashboard-card grid content-start gap-4 p-5"><div><p className="dashboard-eyebrow">Nowa firma</p><h2 className="mt-1 text-xl font-bold">Dodaj organizację</h2></div><Field name="name" label="Nazwa firmy" required /><Field name="legal_name" label="Pełna nazwa prawna" /><div className="grid gap-4 sm:grid-cols-2"><Field name="tax_id" label="NIP / identyfikator" /><Field name="city" label="Miasto" /></div><Field name="address" label="Adres" /><button className="ui-button-primary"><Plus className="size-4" />Utwórz firmę</button></form>
      <div className="space-y-4"><form className="dashboard-card flex items-center gap-3 p-3"><Search className="ml-2 size-4 text-muted-foreground" /><input name="q" defaultValue={q} placeholder="Szukaj firmy, miasta lub nazwy prawnej" className="min-h-10 flex-1 bg-transparent outline-none" /><button className="ui-button-secondary min-h-10 py-2 text-sm">Szukaj</button></form>
        {error ? <p className="dashboard-feedback dashboard-feedback-error">Nie udało się pobrać firm. Sprawdź wdrożenie migracji dashboardu.</p> : data?.length ? <>
          <div className="dashboard-table-wrap hidden md:block"><table className="dashboard-table"><thead><tr><th>Firma</th><th>Administrator</th><th>Użytkownicy</th><th>Stanowiska</th><th>Analizy</th><th>Status</th><th><span className="sr-only">Akcje</span></th></tr></thead><tbody>{data.map((company) => <tr key={company.id}><td><Link href={`/admin/firmy/${company.id}`} className="font-bold text-violet-300 hover:text-violet-200">{company.name}</Link><p className="text-xs text-muted-foreground">{company.city || company.legal_name || "Brak lokalizacji"}</p></td><td>{companyAdmin(company.profiles)}</td><td>{company.profiles?.length ?? 0}</td><td>{relationCount(company.company_positions)}</td><td>{analysisCount(company.profiles)}</td><td><span className={`dashboard-status ${company.status === "active" ? "dashboard-status-success" : "dashboard-status-neutral"}`}>{company.status === "active" ? "Aktywna" : "Nieaktywna"}</span></td><td><Link href={`/admin/firmy/${company.id}`} className="ui-icon-button" aria-label={`Otwórz ${company.name}`}><ArrowRight className="size-4" /></Link></td></tr>)}</tbody></table></div>
          <div className="grid gap-4 md:hidden">{data.map((company) => <Link key={company.id} href={`/admin/firmy/${company.id}`} className="dashboard-card p-5"><div className="flex items-start justify-between"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><Building2 className="size-5" /></span><span className={`dashboard-status ${company.status === "active" ? "dashboard-status-success" : "dashboard-status-neutral"}`}>{company.status === "active" ? "Aktywna" : "Nieaktywna"}</span></div><h2 className="mt-4 text-lg font-bold">{company.name}</h2><p className="text-xs text-muted-foreground">Administrator: {companyAdmin(company.profiles)}</p><div className="mt-4 grid grid-cols-3 gap-2 border-t border-border pt-4 text-center text-xs"><Stat label="Osoby" value={company.profiles?.length ?? 0} /><Stat label="Stanowiska" value={relationCount(company.company_positions)} /><Stat label="Analizy" value={analysisCount(company.profiles)} /></div></Link>)}</div>
        </> : <div className="dashboard-empty"><Building2 className="size-10" /><h3>Brak firm</h3><p>Utwórz pierwszą organizację formularzem obok.</p></div>}
      </div>
    </section>
  </div>;
}

function Field({ name, label, required = false }: { name: string; label: string; required?: boolean }) { return <label className="dashboard-field">{label}<input name={name} required={required} /></label>; }
function relationCount(value: unknown) { return Array.isArray(value) ? Number((value[0] as { count?: number } | undefined)?.count ?? 0) : 0; }
function companyAdmin(value: unknown) { if (!Array.isArray(value)) return "Nie przypisano"; const admin = (value as Array<{ full_name?: string | null; company_role?: string | null }>).find((item) => item.company_role === "admin"); return admin?.full_name || "Nie przypisano"; }
function analysisCount(value: unknown) { if (!Array.isArray(value)) return 0; return (value as Array<{ analyses?: unknown }>).reduce((total, profile) => total + relationCount(profile.analyses), 0); }
function Stat({ label, value }: { label: string; value: number }) { return <span><strong className="block text-base text-foreground">{value}</strong><span className="text-muted-foreground">{label}</span></span>; }
function safe(value: string) { return value.replace(/[,%()]/g, " "); }
