import { notFound } from "next/navigation";
import { BriefcaseBusiness, Building2, CalendarDays, MailPlus, UsersRound } from "lucide-react";

import { TeamManagement, type TeamInvitation, type TeamMember } from "@/components/dashboard/team-management";
import { requireAdmin } from "@/lib/auth/access";
import { relationName } from "@/lib/dashboard/presentation";

export const dynamic = "force-dynamic";

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) notFound();
  const { supabase } = await requireAdmin();
  const [{ data: company }, { data: rawMembers }, { data: positions }, { data: rawInvitations }] = await Promise.all([
    supabase.from("companies").select("id,name,legal_name,tax_id,city,address,status,created_at").eq("id", id).maybeSingle(),
    supabase.from("profiles").select("id,full_name,email,role,company_role,team_role,position_id,job_title,account_status,last_seen_at,created_at,position:company_positions(name)").eq("company_id", id).order("full_name"),
    supabase.from("company_positions").select("id,company_id,name,is_active").eq("company_id", id).order("name"),
    supabase.from("company_invitations").select("id,email,full_name,company_role,team_role,status,created_at,expires_at,position:company_positions(name)").eq("company_id", id).order("created_at", { ascending: false }),
  ]);
  if (!company) notFound();

  const memberIds = (rawMembers ?? []).map((member) => member.id);
  const analyses = memberIds.length ? (await supabase.from("analyses").select("id", { count: "exact", head: true }).in("user_id", memberIds)).count ?? 0 : 0;
  const members = (rawMembers ?? []).map(toTeamMember);
  const teamPositions = (positions ?? []).map((item) => ({ id: item.id, company_id: item.company_id, name: item.name }));
  const invitations = (rawInvitations ?? []).map(toTeamInvitation);
  const pending = invitations.filter((item) => item.status === "pending" && new Date(item.expiresAt) > new Date()).length;

  return <div className="dashboard-page">
    <section className="dashboard-card overflow-hidden"><div className="h-24 bg-gradient-to-r from-violet-700 via-indigo-700 to-sky-700" /><div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-end"><span className="-mt-14 grid size-20 shrink-0 place-items-center rounded-2xl border-4 border-card bg-[#171c26] text-white shadow-xl"><Building2 className="size-8" /></span><div className="min-w-0 flex-1"><p className="dashboard-eyebrow">Centrum firmy</p><h1 className="mt-1 truncate text-3xl font-bold">{company.name}</h1><p className="dashboard-muted mt-1">{company.legal_name || "Organizacja bez uzupełnionej nazwy prawnej"}</p></div><span className={`dashboard-status ${company.status === "active" ? "dashboard-status-success" : "dashboard-status-neutral"}`}>{company.status === "active" ? "Aktywna" : "Nieaktywna"}</span></div></section>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Stat icon={UsersRound} label="Członkowie" value={members.length} /><Stat icon={BriefcaseBusiness} label="Stanowiska" value={positions?.length ?? 0} /><Stat icon={MailPlus} label="Oczekujące zaproszenia" value={pending} /><Stat icon={CalendarDays} label="Analizy" value={analyses} /></section>
    <section><div className="mb-4"><p className="dashboard-eyebrow">Zespół</p><h2 className="mt-1 text-2xl font-bold">Osoby i dostęp</h2><p className="dashboard-muted mt-1">Ten sam uporządkowany widok, z którego korzysta administrator firmy.</p></div><TeamManagement company={{ id: company.id, name: company.name }} members={members} positions={teamPositions} invitations={invitations} /></section>
    <section className="dashboard-card p-5"><p className="dashboard-eyebrow">Dane firmy</p><dl className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Detail label="NIP / identyfikator" value={company.tax_id} /><Detail label="Miasto" value={company.city} /><Detail label="Adres" value={company.address} /><Detail label="Utworzono" value={formatDate(company.created_at)} /></dl></section>
  </div>;
}

function toTeamMember(member: Record<string, unknown>): TeamMember { return { id: String(member.id), fullName: asString(member.full_name), email: asString(member.email), appRole: asString(member.role) ?? "user", companyRole: asString(member.company_role), teamRole: asString(member.team_role), positionId: asString(member.position_id), positionName: relationName(member.position), accountStatus: asString(member.account_status), lastSeenAt: asString(member.last_seen_at), createdAt: asString(member.created_at) ?? new Date(0).toISOString() }; }
function toTeamInvitation(item: Record<string, unknown>): TeamInvitation { return { id: String(item.id), email: String(item.email), fullName: asString(item.full_name), systemRole: asString(item.company_role) ?? "member", teamRole: asString(item.team_role), positionName: relationName(item.position), status: asString(item.status) ?? "pending", expiresAt: asString(item.expires_at) ?? new Date(0).toISOString() }; }
function asString(value: unknown) { return typeof value === "string" ? value : null; }
function Stat({ icon: Icon, label, value }: { icon: typeof UsersRound; label: string; value: number }) { return <article className="dashboard-card flex items-center gap-4 p-5"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><Icon className="size-5" /></span><span><span className="block text-2xl font-bold">{value}</span><span className="text-xs text-muted-foreground">{label}</span></span></article>; }
function Detail({ label, value }: { label: string; value: string | null }) { return <div className="rounded-xl border border-border bg-surface-muted p-4"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value || "Nie uzupełniono"}</dd></div>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium" }).format(new Date(value)); }
