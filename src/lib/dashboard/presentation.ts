export type CompanyRole = "admin" | "member" | "reviewer";
export type AccountStatus = "active" | "inactive" | "pending";

export function isDashboardPathActive(pathname: string, href: string, exact = false) {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function companyRoleLabel(role: CompanyRole | null | undefined) {
  if (role === "admin") return "Administrator firmy";
  if (role === "reviewer") return "Reviewer";
  return "Użytkownik";
}

export function accountStatusLabel(status: AccountStatus | null | undefined) {
  if (status === "inactive") return "Nieaktywne";
  if (status === "pending") return "Oczekujące";
  return "Aktywne";
}

export function relationName(value: unknown): string | null {
  if (Array.isArray(value)) {
    const first = value[0] as { name?: unknown } | undefined;
    return typeof first?.name === "string" ? first.name : null;
  }
  if (value && typeof value === "object" && "name" in value) {
    const name = (value as { name?: unknown }).name;
    return typeof name === "string" ? name : null;
  }
  return null;
}
