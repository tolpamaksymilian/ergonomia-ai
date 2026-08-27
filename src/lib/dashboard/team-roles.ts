export const PREDEFINED_TEAM_ROLES = [
  "Manager",
  "Lider zespołu",
  "Specjalista BHP",
  "Ergonomista",
  "Inżynier procesu",
  "HR",
  "Operator",
  "Koordynator",
] as const;

export const CUSTOM_TEAM_ROLE_VALUE = "__custom__";

export type PredefinedTeamRole = (typeof PREDEFINED_TEAM_ROLES)[number];

export function isPredefinedTeamRole(value: string | null | undefined): value is PredefinedTeamRole {
  return PREDEFINED_TEAM_ROLES.includes(value as PredefinedTeamRole);
}

export function resolveTeamRole(choice: FormDataEntryValue | null, custom: FormDataEntryValue | null) {
  const selected = typeof choice === "string" ? choice.trim() : "";
  const customValue = typeof custom === "string" ? custom.trim().slice(0, 120) : "";

  if (selected === CUSTOM_TEAM_ROLE_VALUE) return customValue || null;
  return isPredefinedTeamRole(selected) ? selected : null;
}

export function teamRoleChoice(value: string | null | undefined) {
  if (!value) return "";
  return isPredefinedTeamRole(value) ? value : CUSTOM_TEAM_ROLE_VALUE;
}
