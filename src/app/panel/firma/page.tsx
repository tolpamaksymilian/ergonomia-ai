import { redirect } from "next/navigation";
import { BriefcaseBusiness, Building2, MailPlus, UsersRound } from "lucide-react";

import { createPosition, updateCompanyMember } from "@/app/admin/actions";
import { InviteUserForm } from "@/components/dashboard/invite-user-form";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function CompanyWorkspacePage() {
  const { supabase, profile } = await requireUser();
  if (profile?.company_role !== "admin" || profile.account_status !== "active" || !profile.company_id) {
    redirect("/panel");
  }

  const companyId = profile.company_id;
  const [{ data: company }, { data: members }, { data: positions }, { data: invitations }] = await Promise.all([
    supabase.from("companies").select("id,name,legal_name,city,address,status").eq("id", companyId).maybeSingle(),
    supabase.from("profiles").select("id,full_name,email,company_role,position_id,job_title,account_status,position:company_positions(name)").eq("company_id", companyId).order("full_name"),
    supabase.from("company_positions").select("id,company_id,name,description,is_active").eq("company_id", companyId).order("name"),
    supabase.from("company_invitations").select("id,email,status,expires_at").eq("company_id", companyId).order("created_at", { ascending: false }),
  ]);

  if (!company) redirect("/panel");

  return <div className="dashboard-page">
    <section className="dashboard-card overflow-hidden">
      <div className="h-24 bg-gradient-to-r from-violet-600 via-indigo-600 to-sky-500" />
      <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-end">
        <span className="-mt-14 grid size-20 shrink-0 place-items-center rounded-2xl border-4 border-card bg-[#171a31] text-white shadow-xl"><Building2 className="size-8" /></span>
        <div className="min-w-0 flex-1"><p className="dashboard-eyebrow">Centrum organizacji</p><h1 className="mt-1 truncate text-3xl font-bold">{company.name}</h1><p className="dashboard-muted mt-1">Zarządzaj zespołem, rolami, stanowiskami i zaproszeniami wyłącznie w swojej firmie.</p></div>
        <span className="dashboard-status border-violet-200 bg-violet-50 text-violet-700">Administrator firmy</span>
      </div>
    </section>

    <section className="grid gap-4 sm:grid-cols-3">
      <Summary icon={UsersRound} label="Osoby" value={members?.length ?? 0} />
      <Summary icon={BriefcaseBusiness} label="Stanowiska" value={positions?.length ?? 0} />
      <Summary icon={MailPlus} label="Oczekujące zaproszenia" value={invitations?.filter((item) => item.status === "pending" && new Date(item.expires_at) > new Date()).length ?? 0} />
    </section>

    <section className="dashboard-table-wrap">
      <div className="border-b border-border p-5"><p className="dashboard-eyebrow">Zespół</p><h2 className="mt-1 text-xl font-bold">Użytkownicy firmy</h2></div>
      <table className="dashboard-table"><thead><tr><th>Osoba</th><th>Rola, stanowisko i status</th></tr></thead><tbody>{members?.map((member) => <tr key={member.id}>
        <td><p className="font-bold">{member.full_name || "Bez nazwy"}</p><p className="text-xs text-muted-foreground">{member.email || "Brak adresu e-mail"}</p></td>
        <td><form action={updateCompanyMember} className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_auto]"><input type="hidden" name="user_id" value={member.id} /><input type="hidden" name="company_id" value={companyId} /><select name="company_role" defaultValue={member.company_role ?? "member"} className="ui-input min-h-9 py-1 text-xs"><option value="admin">Admin firmy</option><option value="reviewer">Reviewer</option><option value="member">Użytkownik</option></select><select name="position_id" defaultValue={member.position_id ?? ""} className="ui-input min-h-9 py-1 text-xs"><option value="">Bez stanowiska</option>{positions?.map((position) => <option key={position.id} value={position.id}>{position.name}</option>)}</select><select name="account_status" defaultValue={member.account_status ?? "active"} className="ui-input min-h-9 py-1 text-xs"><option value="active">Aktywny</option><option value="inactive">Nieaktywny</option><option value="pending">Oczekujący</option></select><button className="ui-button-secondary min-h-9 px-3 py-1 text-xs">Zapisz</button></form></td>
      </tr>)}</tbody></table>
      {!members?.length && <p className="p-10 text-center text-sm text-muted-foreground">Firma nie ma jeszcze użytkowników.</p>}
    </section>

    <section className="grid gap-6 xl:grid-cols-[0.7fr_1.3fr]">
      <form action={createPosition} className="dashboard-card grid content-start gap-4 p-5"><div><p className="dashboard-eyebrow">Struktura zespołu</p><h2 className="mt-1 text-xl font-bold">Dodaj stanowisko</h2></div><input type="hidden" name="company_id" value={companyId} /><label className="dashboard-field">Nazwa<input name="name" required placeholder="np. Operator" /></label><label className="dashboard-field">Opis<textarea name="description" rows={3} /></label><button className="ui-button-primary">Dodaj stanowisko</button></form>
      <InviteUserForm companies={[{ id: company.id, name: company.name }]} positions={positions ?? []} />
    </section>
  </div>;
}

function Summary({ icon: Icon, label, value }: { icon: typeof UsersRound; label: string; value: number }) {
  return <article className="dashboard-card flex items-center gap-4 p-5"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/10 text-violet-600"><Icon className="size-5" /></span><span><span className="block text-2xl font-bold">{value}</span><span className="text-xs text-muted-foreground">{label}</span></span></article>;
}
