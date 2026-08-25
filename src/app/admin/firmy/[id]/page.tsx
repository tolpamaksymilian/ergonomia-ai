import { notFound } from "next/navigation";
import { Building2, BriefcaseBusiness, CalendarDays, MailPlus, UsersRound } from "lucide-react";

import { InviteUserForm } from "@/components/dashboard/invite-user-form";
import { requireAdmin } from "@/lib/auth/access";
import { updateCompanyMember } from "../../actions";

export const dynamic = "force-dynamic";
export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params; if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) notFound();
  const { supabase } = await requireAdmin();
  const [{ data: company }, { data: members }, { data: positions }, { data: invitations }] = await Promise.all([
    supabase.from("companies").select("id,name,legal_name,tax_id,city,address,status,created_at").eq("id", id).maybeSingle(),
    supabase.from("profiles").select("id,full_name,email,role,company_role,position_id,job_title,account_status,created_at,position:company_positions(name)").eq("company_id", id).order("created_at"),
    supabase.from("company_positions").select("id,company_id,name,is_active").eq("company_id", id).order("name"),
    supabase.from("company_invitations").select("id,email,status,created_at,expires_at").eq("company_id", id).order("created_at", { ascending: false }).limit(5),
  ]);
  if (!company) notFound();
  const memberIds = (members ?? []).map((member) => member.id);
  const analyses = memberIds.length
    ? (await supabase.from("analyses").select("id", { count: "exact", head: true }).in("user_id", memberIds)).count
    : 0;
  return <div className="dashboard-page"><section className="dashboard-card overflow-hidden"><div className="h-28 bg-gradient-to-r from-violet-600 via-indigo-600 to-sky-500" /><div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-end"><span className="-mt-14 grid size-20 shrink-0 place-items-center rounded-2xl border-4 border-card bg-[#171a31] text-white shadow-xl"><Building2 className="size-8" /></span><div className="min-w-0 flex-1"><p className="dashboard-eyebrow">Profil firmy</p><h1 className="mt-1 truncate text-3xl font-bold">{company.name}</h1><p className="dashboard-muted mt-1">{company.legal_name || "Organizacja bez uzupełnionej nazwy prawnej"}</p></div><span className="dashboard-status border-emerald-200 bg-emerald-50 text-emerald-700">{company.status === "active" ? "Aktywna" : "Nieaktywna"}</span></div></section>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Stat icon={UsersRound} label="Użytkownicy" value={members?.length ?? 0} /><Stat icon={BriefcaseBusiness} label="Stanowiska" value={positions?.length ?? 0} /><Stat icon={MailPlus} label="Zaproszenia" value={invitations?.filter((item) => item.status === "pending").length ?? 0} /><Stat icon={CalendarDays} label="Analizy" value={analyses ?? 0} /></section>
    <section className="grid gap-6 xl:grid-cols-[1.4fr_0.6fr]"><div className="dashboard-table-wrap"><div className="border-b border-border p-5"><p className="dashboard-eyebrow">Zespół</p><h2 className="mt-1 text-xl font-bold">Użytkownicy firmy</h2></div><table className="dashboard-table"><thead><tr><th>Osoba</th><th>Rola</th><th>Stanowisko</th><th>Status</th><th>Akcja</th></tr></thead><tbody>{members?.map((member) => <tr key={member.id}><td><p className="font-bold">{member.full_name || "Bez nazwy"}</p><p className="max-w-52 truncate text-xs text-muted-foreground">{member.email || member.job_title || "Brak adresu e-mail"}</p></td><td colSpan={4}><form action={updateCompanyMember} className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2"><input type="hidden" name="user_id" value={member.id} /><input type="hidden" name="company_id" value={id} /><select name="company_role" defaultValue={member.company_role ?? "member"} className="ui-input min-h-9 py-1 text-xs"><option value="admin">Admin firmy</option><option value="reviewer">Reviewer</option><option value="member">Użytkownik</option></select><select name="position_id" defaultValue={member.position_id ?? ""} className="ui-input min-h-9 py-1 text-xs"><option value="">Bez stanowiska</option>{positions?.map((position) => <option key={position.id} value={position.id}>{position.name}</option>)}</select><select name="account_status" defaultValue={member.account_status ?? "active"} className="ui-input min-h-9 py-1 text-xs"><option value="active">Aktywny</option><option value="inactive">Nieaktywny</option><option value="pending">Oczekujący</option></select><button className="ui-button-secondary min-h-9 px-3 py-1 text-xs">Zapisz</button></form></td></tr>)}</tbody></table>{!members?.length && <p className="p-8 text-center text-sm text-muted-foreground">Firma nie ma jeszcze użytkowników.</p>}</div>
      <aside className="dashboard-card p-5"><p className="dashboard-eyebrow">Dane firmy</p><dl className="mt-5 space-y-4 text-sm"><Detail label="NIP / identyfikator" value={company.tax_id} /><Detail label="Miasto" value={company.city} /><Detail label="Adres" value={company.address} /><Detail label="Utworzono" value={formatDate(company.created_at)} /></dl></aside></section>
    <InviteUserForm companies={[{ id: company.id, name: company.name }]} positions={(positions ?? []).map((item) => ({ id: item.id, company_id: item.company_id, name: item.name }))} />
  </div>;
}
function Stat({ icon: Icon, label, value }: { icon: typeof UsersRound; label: string; value: number }) { return <article className="dashboard-card flex items-center gap-4 p-5"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/10 text-violet-600"><Icon className="size-5" /></span><span><span className="block text-2xl font-bold">{value}</span><span className="text-xs text-muted-foreground">{label}</span></span></article>; }
function Detail({ label, value }: { label: string; value: string | null }) { return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value || "Nie uzupełniono"}</dd></div>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium" }).format(new Date(value)); }
