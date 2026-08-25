import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { companyAdminNavigation, userDashboardNavigation } from "@/config/dashboard-navigation";
import { requireUser } from "@/lib/auth/access";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const { user, profile } = await requireUser();
  const groups = profile?.company_role === "admin"
    ? [userDashboardNavigation[0], companyAdminNavigation, userDashboardNavigation[1]]
    : userDashboardNavigation;
  const roleLabel = profile?.role === "admin"
    ? "Super administrator"
    : profile?.company_role === "admin" ? "Administrator firmy" : "Użytkownik";
  return <DashboardShell groups={groups} workspaceLabel="Panel użytkownika" fullName={profile?.full_name ?? ""} email={user.email ?? ""} roleLabel={roleLabel}>{children}</DashboardShell>;
}
