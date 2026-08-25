import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { adminDashboardNavigation } from "@/config/dashboard-navigation";
import { requireAdmin } from "@/lib/auth/access";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, profile } = await requireAdmin();
  return <DashboardShell groups={adminDashboardNavigation} workspaceLabel="Centrum administracyjne" fullName={profile?.full_name ?? ""} email={user.email ?? ""} roleLabel="Super administrator">{children}</DashboardShell>;
}
