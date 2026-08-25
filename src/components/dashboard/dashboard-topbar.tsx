"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, ChevronRight, Home, LogOut } from "lucide-react";

import { signOutAction } from "@/actions/auth";
import { ThemeToggle } from "@/components/layout/theme-toggle";

const labels: Record<string, string> = { panel: "Panel", admin: "Administracja", analizy: "Analizy", raporty: "Raporty", stanowiska: "Stanowiska", profil: "Profil", ustawienia: "Ustawienia", firmy: "Firmy", uzytkownicy: "Użytkownicy", zaproszenia: "Zaproszenia", rozwoj: "Rozwój systemu", nowa: "Nowa analiza", kategorie: "Kategorie" };

export function DashboardTopbar({ fullName, email, roleLabel }: { fullName: string; email: string; roleLabel: string }) {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean).filter((segment) => !/^[0-9a-f-]{36}$/i.test(segment));
  const initials = (fullName || email).split(/[\s@]+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
  return <header data-print-hidden className="sticky top-0 z-30 flex min-h-20 items-center justify-between gap-4 border-b border-border/70 bg-background/88 px-5 backdrop-blur-xl sm:px-8">
    <nav className="ml-12 flex min-w-0 items-center gap-2 text-xs text-muted-foreground lg:ml-0" aria-label="Okruszki">
      <Home className="size-4 shrink-0" />
      {segments.map((segment, index) => <span key={`${segment}-${index}`} className="flex min-w-0 items-center gap-2"><ChevronRight className="size-3 shrink-0" /><span className={index === segments.length - 1 ? "truncate font-semibold text-foreground" : "truncate"}>{labels[segment] ?? "Szczegóły"}</span></span>)}
    </nav>
    <div className="flex shrink-0 items-center gap-2">
      <button type="button" className="ui-icon-button hidden sm:inline-flex" aria-label="Powiadomienia" title="Brak nowych powiadomień"><Bell className="size-4" /></button>
      <ThemeToggle />
      <Link href="/panel/profil" className="flex items-center gap-3 rounded-xl border border-border bg-surface px-2 py-1.5 shadow-sm transition hover:bg-secondary">
        <span className="grid size-9 place-items-center rounded-lg bg-violet-500 text-xs font-bold text-white">{initials || "EA"}</span>
        <span className="hidden min-w-0 text-left md:block"><span className="block max-w-36 truncate text-xs font-bold">{fullName || email}</span><span className="block text-[10px] text-muted-foreground">{roleLabel}</span></span>
      </Link>
      <form action={signOutAction}><button type="submit" className="ui-icon-button" aria-label="Wyloguj się" title="Wyloguj się"><LogOut className="size-4" /></button></form>
    </div>
  </header>;
}
