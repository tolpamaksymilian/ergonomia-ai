import { Clock3, MailCheck, MailPlus, RotateCcw, XCircle } from "lucide-react";

import { InviteUserForm } from "@/components/dashboard/invite-user-form";
import { requireAdmin } from "@/lib/auth/access";
import { cancelInvitation, resendInvitation } from "../actions";

export const dynamic = "force-dynamic";
export default async function InvitationsPage() {
  const { supabase } = await requireAdmin();
  const [{ data: companies }, { data: positions }, { data: invitations, error }] = await Promise.all([
    supabase.from("companies").select("id,name").eq("status","active").order("name"),
    supabase.from("company_positions").select("id,company_id,name").eq("is_active",true).order("name"),
    supabase.from("company_invitations").select("id,email,full_name,company_role,status,created_at,expires_at,company:companies(name),position:company_positions(name)").order("created_at", { ascending: false }),
  ]);
  return <div className="dashboard-page"><header><p className="dashboard-eyebrow">Onboarding</p><h1 className="dashboard-title mt-2">Zaproszenia</h1><p className="dashboard-muted mt-2">Dodawaj osoby przez e-mail i kontroluj stan aktywacji kont.</p></header>
    <InviteUserForm companies={companies ?? []} positions={positions ?? []} />
    {error ? <p className="dashboard-card border-red-200 p-6 text-red-700">Nie udało się pobrać zaproszeń.</p> : <div className="dashboard-table-wrap"><table className="dashboard-table"><thead><tr><th>Osoba</th><th>Firma</th><th>Rola</th><th>Stanowisko</th><th>Wysłano / wygasa</th><th>Status</th><th>Akcja</th></tr></thead><tbody>{invitations?.map((item) => <tr key={item.id}><td><p className="font-bold">{item.full_name || item.email}</p><p className="text-xs text-muted-foreground">{item.email}</p></td><td>{relationName(item.company) || "—"}</td><td>{item.company_role === "admin" ? "Admin firmy" : item.company_role === "reviewer" ? "Reviewer" : "Użytkownik"}</td><td>{relationName(item.position) || "—"}</td><td className="text-xs"><p>{formatDate(item.created_at)}</p><p className="text-muted-foreground">do {formatDate(item.expires_at)}</p></td><td><InvitationStatus value={item.status} expired={new Date(item.expires_at) < new Date()} /></td><td>{item.status === "pending" && <div className="flex gap-2"><form action={resendInvitation}><input type="hidden" name="invitation_id" value={item.id} /><button className="ui-button-secondary min-h-9 px-3 py-1 text-xs"><RotateCcw className="size-3" />Ponów</button></form><form action={cancelInvitation}><input type="hidden" name="invitation_id" value={item.id} /><button className="ui-button-secondary min-h-9 px-3 py-1 text-xs"><XCircle className="size-3" />Anuluj</button></form></div>}</td></tr>)}</tbody></table>{!invitations?.length && <div className="p-10 text-center"><MailPlus className="mx-auto size-9 text-muted-foreground" /><p className="mt-3 font-bold">Brak zaproszeń</p></div>}</div>}
    <p className="text-xs text-muted-foreground"><RotateCcw className="mr-1 inline size-3" />Ponowienie odświeża ważność zaproszenia i zleca ponowną wysyłkę przez Supabase Auth.</p>
  </div>;
}
function InvitationStatus({ value, expired }: { value: string; expired: boolean }) { if (value === "accepted") return <span className="dashboard-status border-emerald-200 bg-emerald-50 text-emerald-700"><MailCheck className="size-3" />Zaakceptowane</span>; if (value === "cancelled") return <span className="dashboard-status border-border bg-surface-muted text-muted-foreground">Anulowane</span>; if (expired) return <span className="dashboard-status border-red-200 bg-red-50 text-red-700">Wygasłe</span>; return <span className="dashboard-status border-amber-200 bg-amber-50 text-amber-700"><Clock3 className="size-3" />Oczekuje</span>; }
function relationName(value: unknown) { return Array.isArray(value) ? (value[0] as {name?:string}|undefined)?.name : (value as {name?:string}|null)?.name; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium" }).format(new Date(value)); }
