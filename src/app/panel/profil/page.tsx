import { BriefcaseBusiness, Building2, KeyRound, ShieldCheck, UserRound, UsersRound } from "lucide-react";

import { requireUser } from "@/lib/auth/access";
import { relationName } from "@/lib/dashboard/presentation";
import { updateProfile } from "../actions";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  const { supabase, user } = await requireUser();
  const { data: profile } = await supabase.from("profiles").select("id,full_name,avatar_url,role,company_role,team_role,job_title,account_status,created_at,company:companies(name),position:company_positions(name)").eq("id", user.id).maybeSingle();
  const name = String(profile?.full_name || "Użytkownik");
  const initials = name.split(/\s+/).slice(0, 2).map((part: string) => part[0]).join("").toUpperCase();

  return <div className="dashboard-page">
    <header><p className="dashboard-eyebrow">Konto</p><h1 className="dashboard-title mt-2">Profil użytkownika</h1><p className="dashboard-muted mt-2">Dane konta, miejsce w organizacji i zakres uprawnień.</p></header>
    <section className="grid gap-6 xl:grid-cols-[0.65fr_1.35fr]">
      <aside className="dashboard-card p-6 text-center"><span className="mx-auto grid size-24 place-items-center rounded-3xl bg-gradient-to-br from-violet-500 to-indigo-600 text-2xl font-bold text-white shadow-xl">{initials || "EA"}</span><h2 className="mt-5 text-xl font-bold">{name}</h2><p className="mt-1 break-all text-sm text-muted-foreground">{user.email}</p><span className="dashboard-status dashboard-status-neutral mt-4">{profile?.role === "admin" ? "Superadministrator" : roleLabel(profile?.company_role)}</span></aside>
      <div className="space-y-6">
        <form action={updateProfile} className="dashboard-card grid gap-4 p-5"><div className="flex items-center gap-3"><UserRound className="size-5 text-violet-300" /><h2 className="text-xl font-bold">Konto</h2></div><label className="dashboard-field">Imię i nazwisko<input name="full_name" defaultValue={name} required /></label><label className="dashboard-field">E-mail<input value={user.email ?? ""} disabled /><span>Adres jest zarządzany przez Supabase Auth.</span></label><button className="ui-button-primary justify-self-start">Zapisz profil</button></form>
        <section className="dashboard-card p-5"><h2 className="text-xl font-bold">Organizacja</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><Info icon={Building2} label="Firma" value={relationName(profile?.company) || "Nie przypisano"} /><Info icon={BriefcaseBusiness} label="Stanowisko" value={relationName(profile?.position) || profile?.job_title || "Nie przypisano"} /><Info icon={UsersRound} label="Rola w zespole" value={profile?.team_role || "Nie przypisano"} /></div></section>
        <section className="dashboard-card p-5"><h2 className="text-xl font-bold">Uprawnienia</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><Info icon={ShieldCheck} label="Rola systemowa" value={profile?.role === "admin" ? "Superadministrator" : roleLabel(profile?.company_role)} /><Info icon={KeyRound} label="Status konta" value={statusLabel(profile?.account_status)} /></div></section>
      </div>
    </section>
  </div>;
}

function Info({ icon: Icon, label, value }: { icon: typeof Building2; label: string; value: string }) { return <div className="rounded-xl border border-border bg-surface-muted p-4"><Icon className="size-4 text-violet-300" /><p className="mt-3 text-xs text-muted-foreground">{label}</p><p className="mt-1 font-bold">{value}</p></div>; }
function roleLabel(value: string | null | undefined) { return value === "admin" ? "Administrator firmy" : value === "reviewer" ? "Reviewer" : "Użytkownik"; }
function statusLabel(value: string | null | undefined) { return value === "inactive" ? "Nieaktywne" : value === "pending" ? "Oczekujące" : "Aktywne"; }
