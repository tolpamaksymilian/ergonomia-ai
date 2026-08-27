import { Clock3, MailCheck, MailPlus } from "lucide-react";

import { InviteUserForm } from "@/components/dashboard/invite-user-form";
import { InvitationActions } from "@/components/dashboard/team-management";
import { requireAdmin } from "@/lib/auth/access";
import { companyRoleLabel, relationName } from "@/lib/dashboard/presentation";

export const dynamic = "force-dynamic";

export default async function InvitationsPage() {
  const { supabase } = await requireAdmin();
  const [{ data: companies }, { data: positions }, { data: invitations, error }] = await Promise.all([
    supabase.from("companies").select("id,name").eq("status", "active").order("name"),
    supabase.from("company_positions").select("id,company_id,name").eq("is_active", true).order("name"),
    supabase.from("company_invitations").select("id,email,full_name,company_role,team_role,status,created_at,expires_at,company:companies(name),position:company_positions(name)").order("created_at", { ascending: false }),
  ]);

  return <div className="dashboard-page">
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="dashboard-eyebrow">Onboarding</p><h1 className="dashboard-title mt-2">Zaproszenia</h1><p className="dashboard-muted mt-2">Dodawaj osoby i kontroluj stan aktywacji kont bez mieszania ról organizacyjnych z uprawnieniami.</p></div><InviteUserForm companies={companies ?? []} positions={positions ?? []} /></header>
    {error ? <p className="dashboard-feedback dashboard-feedback-error">Nie udało się pobrać zaproszeń.</p> : invitations?.length ? <div className="dashboard-table-wrap"><table className="dashboard-table"><thead><tr><th>Osoba</th><th>Firma</th><th>Rola systemowa</th><th>Rola w zespole</th><th>Stanowisko</th><th>Wysłano / wygasa</th><th>Status</th><th>Akcje</th></tr></thead><tbody>{invitations.map((item) => <tr key={item.id}><td><p className="font-bold">{item.full_name || item.email}</p><p className="text-xs text-muted-foreground">{item.email}</p></td><td>{relationName(item.company) || "—"}</td><td>{companyRoleLabel(item.company_role)}</td><td>{item.team_role || "—"}</td><td>{relationName(item.position) || "—"}</td><td className="text-xs"><p>{formatDate(item.created_at)}</p><p className="text-muted-foreground">do {formatDate(item.expires_at)}</p></td><td><InvitationStatus value={item.status} expired={new Date(item.expires_at) < new Date()} /></td><td>{item.status === "pending" && <InvitationActions invitationId={item.id} />}</td></tr>)}</tbody></table></div> : <div className="dashboard-empty"><MailPlus className="size-10" /><h3>Brak zaproszeń</h3><p>Dodaj pierwszą osobę, aby rozpocząć pracę zespołową.</p><InviteUserForm companies={companies ?? []} positions={positions ?? []} compact /></div>}
  </div>;
}

function InvitationStatus({ value, expired }: { value: string; expired: boolean }) { if (value === "accepted") return <span className="dashboard-status dashboard-status-success"><MailCheck className="size-3" />Zaakceptowane</span>; if (value === "cancelled") return <span className="dashboard-status dashboard-status-neutral">Anulowane</span>; if (expired) return <span className="dashboard-status dashboard-status-danger">Wygasło</span>; return <span className="dashboard-status dashboard-status-warning"><Clock3 className="size-3" />Oczekuje</span>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium" }).format(new Date(value)); }
