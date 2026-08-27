import { redirect } from "next/navigation";
import { BarChart3, BriefcaseBusiness, Building2, MailPlus, Plus, UsersRound } from "lucide-react";

import { createPosition } from "@/app/admin/actions";
import { TeamManagement, type TeamInvitation, type TeamMember } from "@/components/dashboard/team-management";
import { requireUser } from "@/lib/auth/access";
import { relationName } from "@/lib/dashboard/presentation";

export const dynamic = "force-dynamic";

export default async function CompanyWorkspacePage() {
  const { supabase, profile } = await requireUser();
  if (profile?.company_role !== "admin" || profile.account_status !== "active" || !profile.company_id) redirect("/panel");

  const companyId = profile.company_id;
  const [{ data: company }, { data: rawMembers }, { data: positions }, { data: rawInvitations }] = await Promise.all([
    supabase.from("companies").select("id,name,legal_name,city,address,status").eq("id", companyId).maybeSingle(),
    supabase.from("profiles").select("id,full_name,email,role,company_role,team_role,position_id,job_title,account_status,last_seen_at,created_at,position:company_positions(name)").eq("company_id", companyId).order("full_name"),
    supabase.from("company_positions").select("id,company_id,name,description,is_active").eq("company_id", companyId).order("name"),
    supabase.from("company_invitations").select("id,email,full_name,company_role,team_role,status,expires_at,position:company_positions(name)").eq("company_id", companyId).order("created_at", { ascending: false }),
  ]);
  if (!company) redirect("/panel");

  const memberIds = (rawMembers ?? []).map((member) => member.id);
  const analysesCount = memberIds.length ? (await supabase.from("analyses").select("id", { count: "exact", head: true }).in("user_id", memberIds)).count ?? 0 : 0;
  const members = (rawMembers ?? []).map(toTeamMember);
  const teamPositions = (positions ?? []).map((item) => ({ id: item.id, company_id: item.company_id, name: item.name }));
  const invitations = (rawInvitations ?? []).map(toTeamInvitation);
  const pendingInvitations = invitations.filter((item) => item.status === "pending" && new Date(item.expiresAt) > new Date()).length;

  return <div className="dashboard-page">
    <section className="dashboard-card overflow-hidden">
      <div className="h-24 bg-gradient-to-r from-violet-700 via-indigo-700 to-sky-700" />
      <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-end"><span className="-mt-14 grid size-20 shrink-0 place-items-center rounded-2xl border-4 border-card bg-[#171c26] text-white shadow-xl"><Building2 className="size-8" /></span><div className="min-w-0 flex-1"><p className="dashboard-eyebrow">Centrum organizacji</p><h1 className="mt-1 truncate text-3xl font-bold">{company.name}</h1><p className="dashboard-muted mt-1">Zespół, funkcje organizacyjne i dostęp w jednym miejscu.</p></div><span className="dashboard-status dashboard-status-success">Firma aktywna</span></div>
      <nav className="flex gap-1 overflow-x-auto border-t border-border px-5 py-3 text-sm" aria-label="Sekcje firmy"><a href="#zespol" className="ui-button-secondary min-h-9 whitespace-nowrap px-3 py-1">Zespół</a><a href="#stanowiska" className="ui-button-secondary min-h-9 whitespace-nowrap px-3 py-1">Stanowiska</a><a href="#dane-firmy" className="ui-button-secondary min-h-9 whitespace-nowrap px-3 py-1">Dane firmy</a></nav>
    </section>

    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Summary icon={UsersRound} label="Członkowie" value={members.length} /><Summary icon={BriefcaseBusiness} label="Stanowiska" value={positions?.length ?? 0} /><Summary icon={BarChart3} label="Analizy" value={analysesCount} /><Summary icon={MailPlus} label="Oczekujące zaproszenia" value={pendingInvitations} /></section>

    <div id="zespol" className="scroll-mt-28"><div className="mb-4"><p className="dashboard-eyebrow">Zespół</p><h2 className="mt-1 text-2xl font-bold">Osoby i uprawnienia</h2><p className="dashboard-muted mt-1">Rola systemowa, rola w zespole i stanowisko są zarządzane niezależnie.</p></div><TeamManagement company={{ id: company.id, name: company.name }} members={members} positions={teamPositions} invitations={invitations} /></div>

    <section id="stanowiska" className="grid scroll-mt-28 gap-6 xl:grid-cols-[0.65fr_1.35fr]">
      <form action={createPosition} className="dashboard-card grid content-start gap-4 p-5"><div><p className="dashboard-eyebrow">Struktura</p><h2 className="mt-1 text-xl font-bold">Dodaj stanowisko</h2></div><input type="hidden" name="company_id" value={companyId} /><label className="dashboard-field">Nazwa<input name="name" required placeholder="np. Operator linii" /></label><label className="dashboard-field">Opis<textarea name="description" rows={3} /></label><button className="ui-button-primary"><Plus className="size-4" />Dodaj stanowisko</button></form>
      <div className="dashboard-card overflow-hidden"><div className="border-b border-border p-5"><p className="dashboard-eyebrow">Stanowiska</p><h2 className="mt-1 text-xl font-bold">Struktura firmy</h2></div>{positions?.length ? <div className="divide-y divide-border">{positions.map((position) => <div key={position.id} className="flex items-center gap-4 p-4"><span className="grid size-10 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><BriefcaseBusiness className="size-4" /></span><div className="min-w-0 flex-1"><p className="font-bold">{position.name}</p><p className="text-xs text-muted-foreground">{position.description || "Bez opisu"}</p></div><span className={`dashboard-status ${position.is_active ? "dashboard-status-success" : "dashboard-status-neutral"}`}>{position.is_active ? "Aktywne" : "Nieaktywne"}</span></div>)}</div> : <div className="dashboard-empty m-4 min-h-48"><BriefcaseBusiness className="size-9" /><h3>Brak stanowisk</h3><p>Dodaj pierwsze stanowisko organizacyjne formularzem obok.</p></div>}</div>
    </section>

    <section id="dane-firmy" className="dashboard-card scroll-mt-28 p-5"><p className="dashboard-eyebrow">Dane firmy</p><h2 className="mt-1 text-xl font-bold">Informacje organizacyjne</h2><dl className="mt-5 grid gap-4 sm:grid-cols-3"><Detail label="Nazwa prawna" value={company.legal_name} /><Detail label="Miasto" value={company.city} /><Detail label="Adres" value={company.address} /></dl></section>
  </div>;
}

function toTeamMember(member: Record<string, unknown>): TeamMember { return { id: String(member.id), fullName: asString(member.full_name), email: asString(member.email), appRole: asString(member.role) ?? "user", companyRole: asString(member.company_role), teamRole: asString(member.team_role), positionId: asString(member.position_id), positionName: relationName(member.position), accountStatus: asString(member.account_status), lastSeenAt: asString(member.last_seen_at), createdAt: asString(member.created_at) ?? new Date(0).toISOString() }; }
function toTeamInvitation(item: Record<string, unknown>): TeamInvitation { return { id: String(item.id), email: String(item.email), fullName: asString(item.full_name), systemRole: asString(item.company_role) ?? "member", teamRole: asString(item.team_role), positionName: relationName(item.position), status: asString(item.status) ?? "pending", expiresAt: asString(item.expires_at) ?? new Date(0).toISOString() }; }
function asString(value: unknown) { return typeof value === "string" ? value : null; }
function Summary({ icon: Icon, label, value }: { icon: typeof UsersRound; label: string; value: number }) { return <article className="dashboard-card flex items-center gap-4 p-5"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><Icon className="size-5" /></span><span><span className="block text-2xl font-bold">{value}</span><span className="text-xs text-muted-foreground">{label}</span></span></article>; }
function Detail({ label, value }: { label: string; value: string | null }) { return <div className="rounded-xl border border-border bg-surface-muted p-4"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value || "Nie uzupełniono"}</dd></div>; }
