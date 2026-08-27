"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  Building2,
  ChevronLeft,
  ChevronRight,
  FileText,
  LayoutDashboard,
  MailPlus,
  Menu,
  Settings2,
  UserRound,
  UsersRound,
  Video,
  X,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import type { DashboardIconName, DashboardNavGroup } from "@/config/dashboard-navigation";
import { isDashboardPathActive } from "@/lib/dashboard/presentation";

const DASHBOARD_ICONS = {
  dashboard: LayoutDashboard,
  "admin-dashboard": BarChart3,
  analyses: Video,
  reports: FileText,
  positions: BriefcaseBusiness,
  profile: UserRound,
  settings: Settings2,
  companies: Building2,
  users: UsersRound,
  invitations: MailPlus,
} satisfies Record<DashboardIconName, LucideIcon>;

export function DashboardSidebar({ groups, workspaceLabel, fullName, email, roleLabel }: { groups: readonly DashboardNavGroup[]; workspaceLabel: string; fullName: string; email: string; roleLabel: string }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const navigation = <>
    <div className="flex h-20 items-center gap-3 border-b border-border px-4">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-violet-300/25 bg-violet-500 text-white shadow-lg shadow-black/25"><Activity className="size-5" /></span>
      {!collapsed && <span className="min-w-0"><span className="block truncate font-bold text-white">Ergonomia AI</span><span className="block truncate text-[11px] text-slate-400">{workspaceLabel}</span></span>}
      <button type="button" className="ml-auto hidden size-8 place-items-center rounded-lg text-slate-400 hover:bg-white/8 hover:text-white lg:grid" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Rozwiń menu" : "Zwiń menu"}>{collapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}</button>
    </div>
    <nav className="flex-1 space-y-7 overflow-y-auto px-3 py-5" aria-label="Nawigacja panelu">
      {groups.map((group) => <div key={group.label}>
        {!collapsed && <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">{group.label}</p>}
        <div className="space-y-1">{group.items.map((item) => {
          const active = isDashboardPathActive(pathname, item.href, item.exact);
          const Icon = DASHBOARD_ICONS[item.icon];
          return <Link key={item.href} href={item.href} title={collapsed ? item.label : undefined} onClick={() => setMobileOpen(false)} className={`group relative flex min-h-11 items-center gap-3 rounded-xl border px-3 transition ${active ? "border-violet-400/35 bg-violet-500/18 text-white shadow-sm" : "border-transparent text-slate-400 hover:border-white/8 hover:bg-white/6 hover:text-white"}`}>
            {active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-violet-300" aria-hidden />}
            <Icon className="size-[18px] shrink-0" />
            {!collapsed && <span className="min-w-0"><span className="block truncate text-sm font-semibold">{item.label}</span><span className={`block truncate text-[10px] ${active ? "text-violet-200" : "text-slate-500 group-hover:text-slate-400"}`}>{item.description}</span></span>}
          </Link>;
        })}</div>
      </div>)}
    </nav>
    <Link href="/panel/profil" onClick={() => setMobileOpen(false)} className={`m-3 flex items-center gap-3 rounded-xl border border-border bg-white/[0.025] p-2.5 transition hover:bg-white/6 ${collapsed ? "justify-center" : ""}`} title={collapsed ? `${fullName || email} · ${roleLabel}` : undefined}>
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-violet-500/18 text-xs font-bold text-violet-200">{initials(fullName || email)}</span>
      {!collapsed && <span className="min-w-0"><span className="block truncate text-xs font-bold text-white">{fullName || email}</span><span className="block truncate text-[10px] text-slate-400">{roleLabel}</span></span>}
    </Link>
  </>;

  return <>
    <button type="button" data-print-hidden onClick={() => setMobileOpen(true)} className="fixed left-4 top-4 z-40 grid size-11 place-items-center rounded-xl bg-slate-950 text-white shadow-xl lg:hidden" aria-label="Otwórz menu"><Menu className="size-5" /></button>
    {mobileOpen && <button type="button" className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Zamknij menu" />}
    <aside data-print-hidden className={`fixed inset-y-0 left-0 z-50 flex border-r border-border bg-[#0c0f16] transition-[width,transform] duration-200 ${collapsed ? "w-[76px]" : "w-[264px]"} ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
      <div className="flex min-w-0 flex-1 flex-col">{navigation}</div>
      <button type="button" onClick={() => setMobileOpen(false)} className="absolute right-3 top-4 grid size-9 place-items-center rounded-lg text-slate-300 hover:bg-white/10 lg:hidden" aria-label="Zamknij menu"><X className="size-5" /></button>
    </aside>
    <div data-print-hidden aria-hidden className={`hidden shrink-0 transition-[width] duration-200 lg:block ${collapsed ? "w-[76px]" : "w-[264px]"}`} />
  </>;
}

function initials(value: string) { return value.split(/[\s@]+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "EA"; }
