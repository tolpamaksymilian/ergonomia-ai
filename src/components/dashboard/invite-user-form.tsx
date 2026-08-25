"use client";

import { useActionState, useState } from "react";
import { MailPlus } from "lucide-react";

import { inviteCompanyUser, type InvitationActionState } from "@/app/admin/actions";

const initialState: InvitationActionState = { status: "idle", message: "" };

export function InviteUserForm({ companies, positions }: { companies: Array<{ id: string; name: string }>; positions: Array<{ id: string; company_id: string; name: string }> }) {
  const [state, action, pending] = useActionState(inviteCompanyUser, initialState);
  const [companyId, setCompanyId] = useState(companies.length === 1 ? companies[0].id : "");
  const availablePositions = positions.filter((position) => position.company_id === companyId);
  return <form action={action} className="dashboard-card grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-3">
    <div className="sm:col-span-2 xl:col-span-3"><p className="dashboard-eyebrow">Nowe zaproszenie</p><h2 className="mt-2 text-xl font-bold">Dodaj osobę do firmy</h2><p className="dashboard-muted mt-1">Supabase Auth wyśle bezpieczny link aktywacyjny.</p></div>
    <label className="dashboard-field">E-mail<input name="email" type="email" required placeholder="imie@firma.pl" /></label>
    <label className="dashboard-field">Imię i nazwisko<input name="full_name" placeholder="Opcjonalnie" /></label>
    <label className="dashboard-field">Firma<select name="company_id" required value={companyId} onChange={(event) => setCompanyId(event.target.value)}><option value="">Wybierz firmę</option>{companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label className="dashboard-field">Rola<select name="company_role" defaultValue="member"><option value="member">Użytkownik</option><option value="reviewer">Reviewer</option><option value="admin">Administrator firmy</option></select></label>
    <label className="dashboard-field">Stanowisko<select name="position_id" disabled={!companyId}><option value="">Bez stanowiska</option>{availablePositions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><span className="text-xs font-normal text-muted-foreground">Lista obejmuje wyłącznie stanowiska wybranej firmy.</span></label>
    <div className="flex items-end"><button disabled={pending || !companies.length} className="ui-button-primary w-full"><MailPlus className="size-4" />{pending ? "Wysyłanie…" : "Wyślij zaproszenie"}</button></div>
    {state.message && <p role="status" className={`rounded-xl border p-3 text-sm sm:col-span-2 xl:col-span-3 ${state.status === "success" ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200" : "border-red-300 bg-red-50 text-red-800 dark:bg-red-950/30 dark:text-red-200"}`}>{state.message}</p>}
  </form>;
}
