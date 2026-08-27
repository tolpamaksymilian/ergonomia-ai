"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";

import { requireAdmin, requireCompanyManager, requireUser } from "@/lib/auth/access";
import { resolveTeamRole } from "@/lib/dashboard/team-roles";
import { createAdminClient } from "@/lib/supabase/admin";

export type InvitationActionState = { status: "idle" | "success" | "error"; message: string };
export type MemberActionState = InvitationActionState;

export async function createCompany(formData: FormData) {
  const { supabase } = await requireAdmin();
  const { error } = await supabase.from("companies").insert({ name: required(formData, "name", 160), legal_name: optional(formData, "legal_name", 200), tax_id: optional(formData, "tax_id", 32), city: optional(formData, "city", 120), address: optional(formData, "address", 500) });
  if (error) throw new Error("Nie udało się utworzyć firmy.");
  revalidatePath("/admin/firmy");
}

export async function createPosition(formData: FormData) {
  const companyId = uuid(formData, "company_id");
  const { supabase } = await requireCompanyManager(companyId);
  const { error } = await supabase.from("company_positions").insert({ company_id: companyId, name: required(formData, "name", 120), description: optional(formData, "description", 500) });
  if (error) throw new Error("Nie udało się utworzyć stanowiska.");
  revalidatePath("/admin/stanowiska"); revalidatePath(`/admin/firmy/${companyId}`); revalidatePath("/panel/firma");
}

export async function inviteCompanyUser(_state: InvitationActionState, formData: FormData): Promise<InvitationActionState> {
  const companyId = uuid(formData, "company_id");
  const { supabase, user } = await requireCompanyManager(companyId);
  const email = required(formData, "email", 320).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return { status: "error", message: "Podaj poprawny adres e-mail." };
  const fullName = optional(formData, "full_name", 160);
  const role = enumValue(formData, "company_role", ["admin", "member", "reviewer"] as const, "member");
  const teamRole = resolveTeamRole(formData.get("team_role_choice"), formData.get("team_role_custom"));
  const positionId = optionalUuid(formData, "position_id");
  if (positionId) {
    const { data: position } = await supabase.from("company_positions").select("id").eq("id", positionId).eq("company_id", companyId).maybeSingle();
    if (!position) return { status: "error", message: "Wybrane stanowisko nie należy do wskazanej firmy." };
  }
  const { data: invitation, error: insertError } = await supabase.from("company_invitations").insert({ company_id: companyId, email, full_name: fullName, company_role: role, team_role: teamRole, position_id: positionId, invited_by: user.id }).select("id").single();
  if (insertError) return { status: "error", message: insertError.code === "23505" ? "Aktywne zaproszenie dla tego adresu już istnieje." : "Nie udało się zapisać zaproszenia." };
  const admin = createAdminClient();
  if (!admin) {
    await supabase.from("company_invitations").delete().eq("id", invitation.id);
    return { status: "error", message: "Wysyłka wymaga serwerowej zmiennej SUPABASE_SECRET_KEY." };
  }
  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin") ?? process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const { error: inviteError } = await admin.auth.admin.inviteUserByEmail(email, { redirectTo: `${origin.replace(/\/$/, "")}/auth/callback?next=/panel`, data: { full_name: fullName ?? "" } });
  if (inviteError) {
    await supabase.from("company_invitations").delete().eq("id", invitation.id);
    return { status: "error", message: "Supabase Auth nie wysłał zaproszenia. Sprawdź konfigurację SMTP i adres." };
  }
  revalidatePath("/admin/zaproszenia"); revalidatePath(`/admin/firmy/${companyId}`); revalidatePath("/panel/firma");
  return { status: "success", message: `Zaproszenie wysłano na ${email}.` };
}

export async function updateCompanyMember(_state: MemberActionState, formData: FormData): Promise<MemberActionState> {
  const companyId = uuid(formData, "company_id");
  const { supabase } = await requireCompanyManager(companyId);
  const { data, error } = await supabase.rpc("manage_company_member_v2", {
    p_user_id: uuid(formData, "user_id"),
    p_company_id: companyId,
    p_company_role: enumValue(formData, "company_role", ["admin", "member", "reviewer"] as const, "member"),
    p_position_id: optionalUuid(formData, "position_id"),
    p_account_status: enumValue(formData, "account_status", ["active", "inactive", "pending"] as const, "active"),
    p_team_role: resolveTeamRole(formData.get("team_role_choice"), formData.get("team_role_custom")),
  });
  if (error || data !== true) return { status: "error", message: "Nie udało się zaktualizować członka zespołu." };
  revalidatePath(`/admin/firmy/${companyId}`); revalidatePath("/admin/uzytkownicy"); revalidatePath("/panel/firma");
  return { status: "success", message: "Zmiany członka zespołu zostały zapisane." };
}

export async function cancelInvitation(formData: FormData) {
  const invitationId = uuid(formData, "invitation_id");
  const account = await requireUserForInvitation(invitationId);
  const { supabase } = account;
  const { error } = await supabase.from("company_invitations").update({ status: "cancelled" }).eq("id", invitationId).eq("status", "pending");
  if (error) throw new Error("Nie udało się anulować zaproszenia.");
  revalidatePath("/admin/zaproszenia"); revalidatePath("/panel/firma");
}

export async function resendInvitation(formData: FormData) {
  const invitationId = uuid(formData, "invitation_id");
  const { supabase } = await requireUserForInvitation(invitationId);
  const { data: invitation } = await supabase.from("company_invitations").select("email,company_id,status").eq("id", invitationId).maybeSingle();
  if (!invitation || invitation.status !== "pending") throw new Error("Zaproszenie nie jest już aktywne.");
  const admin = createAdminClient();
  if (!admin) throw new Error("Wysyłka wymaga serwerowej zmiennej SUPABASE_SECRET_KEY.");
  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin") ?? process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const redirectTo = `${origin.replace(/\/$/, "")}/auth/callback?next=/panel`;
  const inviteResult = await admin.auth.admin.inviteUserByEmail(invitation.email, { redirectTo });
  if (inviteResult.error) {
    const resendResult = await admin.auth.resend({ type: "signup", email: invitation.email, options: { emailRedirectTo: redirectTo } });
    if (resendResult.error) throw new Error("Supabase Auth nie ponowił zaproszenia.");
  }
  const { error } = await supabase.from("company_invitations").update({ expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString() }).eq("id", invitationId).eq("status", "pending");
  if (error) throw new Error("Zaproszenie wysłano, ale nie udało się odświeżyć daty ważności.");
  revalidatePath("/admin/zaproszenia"); revalidatePath(`/admin/firmy/${invitation.company_id}`); revalidatePath("/panel/firma");
}

async function requireUserForInvitation(invitationId: string) {
  const { supabase } = await requireUser();
  const { data } = await supabase.from("company_invitations").select("company_id").eq("id", invitationId).maybeSingle();
  if (!data?.company_id) throw new Error("Zaproszenie nie istnieje.");
  return requireCompanyManager(data.company_id);
}

function required(data: FormData, key: string, max: number) { const value = optional(data, key, max); if (!value) throw new Error(`Pole ${key} jest wymagane.`); return value; }
function optional(data: FormData, key: string, max: number) { const value = data.get(key); return typeof value === "string" && value.trim() ? value.trim().slice(0, max) : null; }
function uuid(data: FormData, key: string) { const value = required(data, key, 36); if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value)) throw new Error(`Niepoprawne ${key}.`); return value; }
function optionalUuid(data: FormData, key: string) { const value = optional(data, key, 36); return value && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value) ? value : null; }
function enumValue<T extends string>(data: FormData, key: string, allowed: readonly T[], fallback: T): T { const value = optional(data, key, 40); return allowed.includes(value as T) ? value as T : fallback; }
