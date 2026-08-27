import Link from "next/link";
import { Search, UserRound, UsersRound } from "lucide-react";

import { requireAdmin } from "@/lib/auth/access";
import { accountStatusLabel, companyRoleLabel, relationName } from "@/lib/dashboard/presentation";

export const dynamic = "force-dynamic";

export default async function UsersPage({ searchParams }: { searchParams: Promise<{ q?: string; company?: string; role?: string; team?: string; status?: string }> }) {
  const raw = await searchParams;
  const q = clean(raw.q);
  const { supabase } = await requireAdmin();
  const { data: companies } = await supabase.from("companies").select("id,name").order("name");
  let query = supabase.from("profiles").select("id,full_name,email,role,company_id,company_role,team_role,job_title,account_status,created_at,last_seen_at,company:companies(id,name),position:company_positions(name)").order("created_at", { ascending: false });
  if (q) query = query.or(`full_name.ilike.%${q}%,email.ilike.%${q}%`);
  if (uuid(raw.company)) query = query.eq("company_id", raw.company!);
  if (["admin", "member", "reviewer"].includes(raw.role ?? "")) query = query.eq("company_role", raw.role!);
  if (raw.team) query = query.eq("team_role", clean(raw.team));
  if (["active", "inactive", "pending"].includes(raw.status ?? "")) query = query.eq("account_status", raw.status!);
  const { data, error } = await query;
  const teamRoles = Array.from(new Set((data ?? []).map((item) => item.team_role).filter(Boolean) as string[])).sort();

  return <div className="dashboard-page">
    <header><p className="dashboard-eyebrow">Dostęp</p><h1 className="dashboard-title mt-2">Użytkownicy</h1><p className="dashboard-muted mt-2">Przegląd kont z wyraźnym rozdzieleniem uprawnień, funkcji zespołowej i stanowiska.</p></header>
    <form className="dashboard-card grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto]"><label className="relative"><span className="sr-only">Szukaj użytkownika</span><Search className="absolute left-3 top-3.5 size-4 text-muted-foreground" /><input name="q" defaultValue={q} placeholder="Szukaj po imieniu lub e-mailu" className="ui-input pl-10" /></label><Filter name="company" value={raw.company} options={[["", "Wszystkie firmy"], ...(companies ?? []).map((item) => [item.id, item.name] as const)]} /><Filter name="role" value={raw.role} options={[["", "Rola systemowa"], ["admin", "Administrator firmy"], ["reviewer", "Reviewer"], ["member", "Użytkownik"]]} /><Filter name="team" value={raw.team} options={[["", "Rola w zespole"], ...teamRoles.map((item) => [item, item] as const)]} /><Filter name="status" value={raw.status} options={[["", "Wszystkie statusy"], ["active", "Aktywny"], ["inactive", "Nieaktywny"], ["pending", "Oczekujący"]]} /><button className="ui-button-primary">Filtruj</button></form>
    {error ? <p className="dashboard-feedback dashboard-feedback-error">Nie udało się pobrać użytkowników.</p> : data?.length ? <>
      <div className="dashboard-table-wrap hidden md:block"><table className="dashboard-table"><thead><tr><th>Użytkownik</th><th>Firma</th><th>Rola systemowa</th><th>Rola w zespole</th><th>Stanowisko</th><th>Status</th><th>Aktywność</th></tr></thead><tbody>{data.map((item) => <tr key={item.id}><td><Person name={item.full_name} email={item.email} /></td><td>{item.company_id ? <Link href={`/admin/firmy/${item.company_id}`} className="font-semibold text-violet-300 hover:text-violet-200">{relationName(item.company) || "Firma"}</Link> : "Bez firmy"}</td><td>{item.role === "admin" ? "Superadministrator" : companyRoleLabel(item.company_role)}</td><td>{item.team_role || "—"}</td><td>{relationName(item.position) || item.job_title || "—"}</td><td><span className={`dashboard-status ${item.account_status === "active" ? "dashboard-status-success" : item.account_status === "pending" ? "dashboard-status-warning" : "dashboard-status-neutral"}`}>{accountStatusLabel(item.account_status)}</span></td><td className="text-xs text-muted-foreground">{item.last_seen_at ? formatDate(item.last_seen_at) : `Dodano ${formatDate(item.created_at)}`}</td></tr>)}</tbody></table></div>
      <div className="grid gap-3 md:hidden">{data.map((item) => <article key={item.id} className="dashboard-card p-4"><Person name={item.full_name} email={item.email} /><dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 text-xs"><Detail label="Rola systemowa" value={item.role === "admin" ? "Superadministrator" : companyRoleLabel(item.company_role)} /><Detail label="Rola w zespole" value={item.team_role || "—"} /><Detail label="Firma" value={relationName(item.company) || "Bez firmy"} /><Detail label="Stanowisko" value={relationName(item.position) || item.job_title || "—"} /></dl></article>)}</div>
    </> : <div className="dashboard-empty"><UsersRound className="size-10" /><h3>Brak użytkowników</h3><p>Zmień filtry lub dodaj osobę z poziomu wybranej firmy.</p></div>}
    <p className="text-xs text-muted-foreground">Edycja uprawnień i organizacji jest dostępna w centrum wybranej firmy.</p>
  </div>;
}

function Filter({ name, value, options }: { name: string; value?: string; options: ReadonlyArray<readonly [string, string]> }) { return <select name={name} defaultValue={value ?? ""} className="ui-input">{options.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>; }
function Person({ name, email }: { name: string | null; email: string | null }) { return <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-violet-500/12 text-violet-300"><UserRound className="size-4" /></span><div className="min-w-0"><p className="font-bold">{name || "Bez nazwy"}</p><p className="max-w-56 truncate text-xs text-muted-foreground">{email || "Brak adresu e-mail"}</p></div></div>; }
function Detail({ label, value }: { label: string; value: string }) { return <div><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>; }
function clean(value?: string) { return (value ?? "").trim().slice(0, 100).replace(/[,%()]/g, " "); }
function uuid(value?: string): value is string { return Boolean(value && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value)); }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium" }).format(new Date(value)); }
