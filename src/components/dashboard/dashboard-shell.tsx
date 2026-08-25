import type { ReactNode } from "react";

import { DashboardSidebar } from "@/components/dashboard/dashboard-sidebar";
import { DashboardTopbar } from "@/components/dashboard/dashboard-topbar";
import type { DashboardNavGroup } from "@/config/dashboard-navigation";

export function DashboardShell({ children, groups, workspaceLabel, fullName, email, roleLabel }: { children: ReactNode; groups: readonly DashboardNavGroup[]; workspaceLabel: string; fullName: string; email: string; roleLabel: string }) {
  return <div className="dashboard-shell flex min-h-screen bg-background text-foreground">
    <DashboardSidebar groups={groups} workspaceLabel={workspaceLabel} />
    <div className="min-w-0 flex-1"><DashboardTopbar fullName={fullName} email={email} roleLabel={roleLabel} /><main className="min-w-0 p-4 sm:p-6 xl:p-8">{children}</main></div>
  </div>;
}
