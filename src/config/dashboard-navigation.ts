import {
  BarChart3,
  BriefcaseBusiness,
  Building2,
  FileText,
  LayoutDashboard,
  MailPlus,
  Settings2,
  UserRound,
  UsersRound,
  Video,
  type LucideIcon,
} from "lucide-react";

export type DashboardNavItem = {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  exact?: boolean;
};

export type DashboardNavGroup = {
  label: string;
  items: readonly DashboardNavItem[];
};

export const userDashboardNavigation: readonly DashboardNavGroup[] = [
  {
    label: "Główne",
    items: [
      { href: "/panel", label: "Dashboard", description: "Podsumowanie pracy", icon: LayoutDashboard, exact: true },
      { href: "/panel/analizy", label: "Analizy", description: "Historia i nowe analizy", icon: Video },
      { href: "/panel/raporty", label: "Raporty", description: "Gotowe wyniki", icon: FileText },
      { href: "/panel/stanowiska", label: "Stanowiska", description: "Obszary i stanowiska pracy", icon: BriefcaseBusiness },
    ],
  },
  {
    label: "Konto",
    items: [
      { href: "/panel/profil", label: "Profil", description: "Dane i uprawnienia", icon: UserRound },
      { href: "/panel/ustawienia", label: "Ustawienia", description: "Preferencje i słowniki", icon: Settings2 },
    ],
  },
];

export const companyAdminNavigation: DashboardNavGroup = {
  label: "Organizacja",
  items: [
    { href: "/panel/firma", label: "Moja firma", description: "Zespół, role i zaproszenia", icon: Building2 },
  ],
};

export const adminDashboardNavigation: readonly DashboardNavGroup[] = [
  {
    label: "Zarządzanie",
    items: [
      { href: "/admin", label: "Dashboard", description: "Widok administracyjny", icon: BarChart3, exact: true },
      { href: "/admin/firmy", label: "Firmy", description: "Organizacje i zespoły", icon: Building2 },
      { href: "/admin/uzytkownicy", label: "Użytkownicy", description: "Konta i role", icon: UsersRound },
      { href: "/admin/zaproszenia", label: "Zaproszenia", description: "Dostęp przez e-mail", icon: MailPlus },
      { href: "/admin/stanowiska", label: "Stanowiska", description: "Funkcje w firmach", icon: BriefcaseBusiness },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/panel/analizy", label: "Wszystkie analizy", description: "Analizy dostępne administratorowi", icon: Video },
      { href: "/admin/rozwoj", label: "Rozwój systemu", description: "Wersje i roadmapa", icon: LayoutDashboard },
      { href: "/panel/profil", label: "Mój profil", description: "Dane administratora", icon: UserRound },
    ],
  },
];
