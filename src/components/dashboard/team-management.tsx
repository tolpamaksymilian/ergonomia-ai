"use client";

import { MoreHorizontal, RotateCcw, Search, UserPlus, UsersRound, X, XCircle } from "lucide-react";
import { useActionState, useMemo, useState } from "react";

import {
  cancelInvitation,
  resendInvitation,
  updateCompanyMember,
  type MemberActionState,
} from "@/app/admin/actions";
import { InviteUserForm } from "@/components/dashboard/invite-user-form";
import {
  CUSTOM_TEAM_ROLE_VALUE,
  PREDEFINED_TEAM_ROLES,
  teamRoleChoice,
} from "@/lib/dashboard/team-roles";

export type TeamMember = {
  id: string;
  fullName: string | null;
  email: string | null;
  appRole: string;
  companyRole: string | null;
  teamRole: string | null;
  positionId: string | null;
  positionName: string | null;
  accountStatus: string | null;
  lastSeenAt: string | null;
  createdAt: string;
};

export type TeamPosition = { id: string; company_id: string; name: string };

export type TeamInvitation = {
  id: string;
  email: string;
  fullName: string | null;
  systemRole: string;
  teamRole: string | null;
  positionName: string | null;
  status: string;
  expiresAt: string;
};

const initialState: MemberActionState = { status: "idle", message: "" };

export function TeamManagement({
  company,
  members,
  positions,
  invitations,
  lockCompany = true,
}: {
  company: { id: string; name: string };
  members: TeamMember[];
  positions: TeamPosition[];
  invitations: TeamInvitation[];
  lockCompany?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [systemRole, setSystemRole] = useState("");
  const [teamRole, setTeamRole] = useState("");
  const [positionId, setPositionId] = useState("");
  const [status, setStatus] = useState("");
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null);

  const teamRoles = useMemo(() => Array.from(new Set(members.map((member) => member.teamRole).filter(Boolean) as string[])).sort(), [members]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("pl");
    return members.filter((member) => {
      const matchesQuery = !needle || `${member.fullName ?? ""} ${member.email ?? ""}`.toLocaleLowerCase("pl").includes(needle);
      const matchesSystem = !systemRole || effectiveSystemRole(member) === systemRole;
      return matchesQuery
        && matchesSystem
        && (!teamRole || member.teamRole === teamRole)
        && (!positionId || member.positionId === positionId)
        && (!status || member.accountStatus === status);
    });
  }, [members, positionId, query, status, systemRole, teamRole]);

  return <section className="space-y-5">
    <div className="dashboard-card p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
        <label className="relative min-w-0 flex-1"><span className="sr-only">Szukaj członka zespołu</span><Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-muted-foreground" /><input className="ui-input pl-10" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Szukaj po imieniu lub e-mailu" /></label>
        <div className="grid gap-2 sm:grid-cols-2 xl:flex">
          <CompactFilter label="Rola systemowa" value={systemRole} onChange={setSystemRole} options={[["admin", "Administrator firmy"], ["reviewer", "Reviewer"], ["member", "Użytkownik"], ["superadmin", "Superadministrator"]]} />
          <CompactFilter label="Rola w zespole" value={teamRole} onChange={setTeamRole} options={teamRoles.map((value) => [value, value])} />
          <CompactFilter label="Stanowisko" value={positionId} onChange={setPositionId} options={positions.map((item) => [item.id, item.name])} />
          <CompactFilter label="Status" value={status} onChange={setStatus} options={[["active", "Aktywny"], ["inactive", "Nieaktywny"], ["pending", "Oczekujący"]]} />
        </div>
        <InviteUserForm companies={[company]} positions={positions} lockCompany={lockCompany} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Wyświetlono {filtered.length} z {members.length} osób. Rola zespołowa nie zmienia uprawnień.</p>
    </div>

    {filtered.length ? <>
      <div className="dashboard-table-wrap hidden md:block">
        <table className="dashboard-table"><thead><tr><th>Osoba</th><th>Rola systemowa</th><th>Rola w zespole</th><th>Stanowisko</th><th>Status</th><th>Ostatnia aktywność</th><th><span className="sr-only">Akcje</span></th></tr></thead>
          <tbody>{filtered.map((member) => <tr key={member.id}><td><Person member={member} /></td><td>{systemRoleLabel(member)}</td><td>{member.teamRole || "—"}</td><td>{member.positionName || "—"}</td><td><MemberStatus value={member.accountStatus} /></td><td className="text-xs text-muted-foreground">{activityLabel(member)}</td><td><button type="button" className="ui-icon-button" onClick={() => setSelectedMember(member)} aria-label={`Edytuj ${member.fullName || member.email || "użytkownika"}`}><MoreHorizontal className="size-4" /></button></td></tr>)}</tbody>
        </table>
      </div>
      <div className="grid gap-3 md:hidden">{filtered.map((member) => <article key={member.id} className="dashboard-card p-4"><div className="flex items-start gap-3"><Person member={member} /><button type="button" className="ui-icon-button ml-auto shrink-0" onClick={() => setSelectedMember(member)} aria-label="Edytuj członka"><MoreHorizontal className="size-4" /></button></div><dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 text-xs"><MobileDetail label="Rola systemowa" value={systemRoleLabel(member)} /><MobileDetail label="Rola w zespole" value={member.teamRole || "—"} /><MobileDetail label="Stanowisko" value={member.positionName || "—"} /><MobileDetail label="Aktywność" value={activityLabel(member)} /></dl><MemberStatus value={member.accountStatus} /></article>)}</div>
    </> : <div className="dashboard-empty"><UsersRound className="size-10" /><h3>Nie znaleziono członków zespołu</h3><p>Zmień filtry albo zaproś pierwszą osobę do organizacji.</p><InviteUserForm companies={[company]} positions={positions} lockCompany={lockCompany} compact /></div>}

    <InvitationList invitations={invitations} />
    {selectedMember && <MemberEditor companyId={company.id} member={selectedMember} positions={positions} onClose={() => setSelectedMember(null)} />}
  </section>;
}

function MemberEditor({ companyId, member, positions, onClose }: { companyId: string; member: TeamMember; positions: TeamPosition[]; onClose: () => void }) {
  const [state, action, pending] = useActionState(updateCompanyMember, initialState);
  const [roleChoice, setRoleChoice] = useState(teamRoleChoice(member.teamRole));
  const [accountStatus, setAccountStatus] = useState(member.accountStatus ?? "active");
  const isSuperAdmin = member.appRole === "admin";

  return <div className="fixed inset-0 z-[80] flex justify-end bg-black/65 backdrop-blur-sm" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-labelledby="member-editor-title" className="h-full w-full max-w-xl overflow-y-auto border-l border-border bg-card p-5 shadow-2xl sm:p-7">
      <div className="flex items-start justify-between gap-4 border-b border-border pb-5"><div><p className="dashboard-eyebrow">Zespół</p><h2 id="member-editor-title" className="mt-2 text-2xl font-bold">Edytuj członka</h2></div><button type="button" className="ui-icon-button" onClick={onClose} aria-label="Zamknij"><X className="size-4" /></button></div>
      <div className="mt-6 rounded-2xl border border-border bg-surface-muted p-4"><Person member={member} /><p className="mt-3 text-xs text-muted-foreground">Dane konta i adres e-mail są zarządzane w profilu użytkownika i Supabase Auth.</p></div>
      <form action={action} className="mt-6 grid gap-5" onSubmit={(event) => { if (accountStatus === "inactive" && member.accountStatus !== "inactive" && !window.confirm("Dezaktywować konto tego członka? Utraci dostęp do panelu firmy.")) event.preventDefault(); }}>
        <input type="hidden" name="user_id" value={member.id} /><input type="hidden" name="company_id" value={companyId} />
        <fieldset className="grid gap-4"><legend className="mb-3 font-bold">Uprawnienia</legend>
          <label className="dashboard-field">Rola systemowa<select name="company_role" defaultValue={member.companyRole ?? "member"} disabled={isSuperAdmin}><option value="member">Użytkownik</option><option value="reviewer">Reviewer</option><option value="admin">Administrator firmy</option></select><span>{isSuperAdmin ? "Roli superadministratora nie zmienia się w panelu firmy." : "Rola systemowa steruje dostępem do funkcji."}</span></label>
          {isSuperAdmin && <input type="hidden" name="company_role" value={member.companyRole ?? "member"} />}
        </fieldset>
        <fieldset className="grid gap-4 border-t border-border pt-5"><legend className="mb-3 font-bold">Organizacja</legend>
          <label className="dashboard-field">Rola w zespole<select name="team_role_choice" value={roleChoice} onChange={(event) => setRoleChoice(event.target.value)}><option value="">Bez roli zespołowej</option>{PREDEFINED_TEAM_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}<option value={CUSTOM_TEAM_ROLE_VALUE}>Inna…</option></select><span>Informacja organizacyjna — nie wpływa na uprawnienia.</span></label>
          {roleChoice === CUSTOM_TEAM_ROLE_VALUE && <label className="dashboard-field">Własna rola w zespole<input name="team_role_custom" required maxLength={120} defaultValue={member.teamRole ?? ""} /></label>}
          <label className="dashboard-field">Stanowisko<select name="position_id" defaultValue={member.positionId ?? ""}><option value="">Bez stanowiska</option>{positions.map((position) => <option key={position.id} value={position.id}>{position.name}</option>)}</select></label>
        </fieldset>
        <fieldset className="grid gap-4 border-t border-border pt-5"><legend className="mb-3 font-bold">Status</legend><label className="dashboard-field">Status konta<select name="account_status" value={accountStatus} onChange={(event) => setAccountStatus(event.target.value)}><option value="active">Aktywny</option><option value="pending">Oczekujący</option><option value="inactive">Nieaktywny</option></select></label></fieldset>
        {state.message && <p role="status" className={`dashboard-toast ${state.status === "success" ? "dashboard-feedback-success" : "dashboard-feedback-error"}`}>{state.message}</p>}
        <div className="sticky bottom-0 -mx-5 flex justify-end gap-3 border-t border-border bg-card px-5 pt-5 sm:-mx-7 sm:px-7"><button type="button" className="ui-button-secondary" onClick={onClose}>Anuluj</button><button disabled={pending || isSuperAdmin} className="ui-button-primary">{pending ? "Zapisywanie…" : "Zapisz zmiany"}</button></div>
      </form>
    </section>
  </div>;
}

function InvitationList({ invitations }: { invitations: TeamInvitation[] }) {
  const active = invitations.filter((item) => item.status === "pending");
  if (!active.length) return null;
  return <div className="dashboard-card overflow-hidden"><div className="border-b border-border p-5"><p className="dashboard-eyebrow">Zaproszenia</p><h2 className="mt-1 text-xl font-bold">Oczekujące osoby</h2></div><div className="divide-y divide-border">{active.map((item) => <div key={item.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-amber-500/12 text-amber-300"><UserPlus className="size-4" /></span><div className="min-w-0 flex-1"><p className="truncate font-bold">{item.fullName || item.email}</p><p className="truncate text-xs text-muted-foreground">{item.email} · {plainSystemRoleLabel(item.systemRole)}{item.teamRole ? ` · ${item.teamRole}` : ""}{item.positionName ? ` · ${item.positionName}` : ""}</p></div><InvitationActions invitationId={item.id} /></div>)}</div></div>;
}

export function InvitationActions({ invitationId }: { invitationId: string }) {
  return <div className="flex gap-2"><form action={resendInvitation}><input type="hidden" name="invitation_id" value={invitationId} /><button className="ui-button-secondary min-h-9 px-3 py-1 text-xs"><RotateCcw className="size-3" />Ponów</button></form><form action={cancelInvitation} onSubmit={(event) => { if (!window.confirm("Anulować to zaproszenie? Link aktywacyjny przestanie być ważny.")) event.preventDefault(); }}><input type="hidden" name="invitation_id" value={invitationId} /><button className="ui-button-danger min-h-9 px-3 py-1 text-xs"><XCircle className="size-3" />Anuluj</button></form></div>;
}

function CompactFilter({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[][] }) { return <label><span className="sr-only">{label}</span><select className="ui-input min-w-36" value={value} onChange={(event) => onChange(event.target.value)}><option value="">{label}</option>{options.map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>; }
function Person({ member }: { member: TeamMember }) { const label = member.fullName || member.email || "Użytkownik"; const initials = label.split(/[\s@]+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join(""); return <div className="flex min-w-0 items-center gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl border border-violet-400/30 bg-violet-500/12 text-xs font-bold text-violet-200">{initials || "EA"}</span><span className="min-w-0"><span className="block truncate font-bold">{member.fullName || "Bez nazwy"}</span><span className="block max-w-60 truncate text-xs text-muted-foreground">{member.email || "Brak adresu e-mail"}</span></span></div>; }
function MobileDetail({ label, value }: { label: string; value: string }) { return <div><dt className="text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold text-foreground">{value}</dd></div>; }
function MemberStatus({ value }: { value: string | null }) { const normalized = value ?? "active"; const label = normalized === "inactive" ? "Nieaktywny" : normalized === "pending" ? "Oczekujący" : "Aktywny"; return <span className={`dashboard-status ${normalized === "active" ? "dashboard-status-success" : normalized === "pending" ? "dashboard-status-warning" : "dashboard-status-neutral"}`}>{label}</span>; }
function effectiveSystemRole(member: TeamMember) { return member.appRole === "admin" ? "superadmin" : member.companyRole ?? "member"; }
function systemRoleLabel(member: TeamMember) { return member.appRole === "admin" ? "Superadministrator" : plainSystemRoleLabel(member.companyRole); }
function plainSystemRoleLabel(value: string | null) { return value === "admin" ? "Administrator firmy" : value === "reviewer" ? "Reviewer" : "Użytkownik"; }
function activityLabel(member: TeamMember) { const value = member.lastSeenAt ?? member.createdAt; const prefix = member.lastSeenAt ? "" : "Dodano "; return `${prefix}${new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium", timeZone: "Europe/Warsaw" }).format(new Date(value))}`; }
