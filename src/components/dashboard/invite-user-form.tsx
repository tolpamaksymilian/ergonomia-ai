"use client";

import { MailPlus, X } from "lucide-react";
import { useActionState, useEffect, useMemo, useState } from "react";

import { inviteCompanyUser, type InvitationActionState } from "@/app/admin/actions";
import {
  CUSTOM_TEAM_ROLE_VALUE,
  PREDEFINED_TEAM_ROLES,
} from "@/lib/dashboard/team-roles";

const initialState: InvitationActionState = { status: "idle", message: "" };

type CompanyOption = { id: string; name: string };
type PositionOption = { id: string; company_id: string; name: string };

export function InviteUserForm({
  companies,
  positions,
  lockCompany = false,
  compact = false,
}: {
  companies: CompanyOption[];
  positions: PositionOption[];
  lockCompany?: boolean;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [state, action, pending] = useActionState(inviteCompanyUser, initialState);
  const [companyId, setCompanyId] = useState(companies.length === 1 ? companies[0].id : "");
  const [teamRoleChoice, setTeamRoleChoice] = useState("");
  const availablePositions = useMemo(
    () => positions.filter((position) => position.company_id === companyId),
    [companyId, positions],
  );

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  return <>
    <button type="button" className={compact ? "ui-button-secondary" : "ui-button-primary"} onClick={() => setOpen(true)}>
      <MailPlus className="size-4" />Dodaj członka
    </button>
    {open && <div className="fixed inset-0 z-[80] flex justify-end bg-black/65 backdrop-blur-sm" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setOpen(false); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="invite-title" className="h-full w-full max-w-xl overflow-y-auto border-l border-border bg-card p-5 shadow-2xl sm:p-7">
        <div className="flex items-start justify-between gap-4 border-b border-border pb-5">
          <div><p className="dashboard-eyebrow">Nowy dostęp</p><h2 id="invite-title" className="mt-2 text-2xl font-bold">Dodaj członka zespołu</h2><p className="dashboard-muted mt-2">Zaproszona osoba otrzyma bezpieczny link aktywacyjny.</p></div>
          <button type="button" className="ui-icon-button shrink-0" onClick={() => setOpen(false)} aria-label="Zamknij"><X className="size-4" /></button>
        </div>
        <form action={action} className="mt-6 grid gap-5">
          <fieldset className="grid gap-4"><legend className="mb-3 font-bold">Dane użytkownika</legend>
            <label className="dashboard-field">E-mail<input name="email" type="email" required placeholder="imie@firma.pl" autoFocus /></label>
            <label className="dashboard-field">Imię i nazwisko<input name="full_name" placeholder="Opcjonalnie" /></label>
          </fieldset>
          <fieldset className="grid gap-4 border-t border-border pt-5"><legend className="mb-3 font-bold">Organizacja i uprawnienia</legend>
            {lockCompany && companies.length === 1
              ? <input type="hidden" name="company_id" value={companies[0].id} />
              : <label className="dashboard-field">Firma<select name="company_id" required value={companyId} onChange={(event) => setCompanyId(event.target.value)}><option value="">Wybierz firmę</option>{companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
            {lockCompany && companies[0] && <p className="rounded-xl border border-border bg-surface-muted p-3 text-sm"><span className="text-muted-foreground">Firma:</span> <strong>{companies[0].name}</strong></p>}
            <label className="dashboard-field">Rola systemowa<select name="company_role" defaultValue="member"><option value="member">Użytkownik</option><option value="reviewer">Reviewer</option><option value="admin">Administrator firmy</option></select><span>Ta rola określa uprawnienia w aplikacji.</span></label>
            <label className="dashboard-field">Rola w zespole<select name="team_role_choice" value={teamRoleChoice} onChange={(event) => setTeamRoleChoice(event.target.value)}><option value="">Bez roli zespołowej</option>{PREDEFINED_TEAM_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}<option value={CUSTOM_TEAM_ROLE_VALUE}>Inna…</option></select></label>
            {teamRoleChoice === CUSTOM_TEAM_ROLE_VALUE && <label className="dashboard-field">Własna rola w zespole<input name="team_role_custom" required maxLength={120} placeholder="np. Koordynator zmiany" /></label>}
            <label className="dashboard-field">Stanowisko<select name="position_id" disabled={!companyId}><option value="">Bez stanowiska</option>{availablePositions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><span>Stanowisko opisuje miejsce osoby w strukturze firmy.</span></label>
          </fieldset>
          {state.message && <p role="status" className={`dashboard-toast ${state.status === "success" ? "dashboard-feedback-success" : "dashboard-feedback-error"}`}>{state.message}</p>}
          <div className="sticky bottom-0 -mx-5 mt-2 flex justify-end gap-3 border-t border-border bg-card px-5 pt-5 sm:-mx-7 sm:px-7">
            <button type="button" className="ui-button-secondary" onClick={() => setOpen(false)}>Anuluj</button>
            <button disabled={pending || !companies.length} className="ui-button-primary"><MailPlus className="size-4" />{pending ? "Wysyłanie…" : "Wyślij zaproszenie"}</button>
          </div>
        </form>
      </section>
    </div>}
    {state.status === "success" && !open && <p role="status" className="dashboard-toast dashboard-feedback-success">{state.message}</p>}
  </>;
}
