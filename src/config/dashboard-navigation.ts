export type DashboardIconName =
  | "dashboard"
  | "admin-dashboard"
  | "analyses"
  | "reports"
  | "positions"
  | "profile"
  | "settings"
  | "companies"
  | "users"
  | "invitations";

export type DashboardNavItem = {
  href: string;
  label: string;
  description: string;
  icon: DashboardIconName;
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
      { href: "/panel", label: "Dashboard", description: "Podsumowanie pracy", icon: "dashboard", exact: true },
      { href: "/panel/analizy", label: "Analizy", description: "Historia i nowe analizy", icon: "analyses" },
      { href: "/panel/raporty", label: "Raporty", description: "Gotowe wyniki", icon: "reports" },
      { href: "/panel/stanowiska", label: "Stanowiska", description: "Obszary i stanowiska pracy", icon: "positions" },
    ],
  },
  {
    label: "Konto",
    items: [
      { href: "/panel/profil", label: "Profil", description: "Dane i uprawnienia", icon: "profile" },
      { href: "/panel/ustawienia", label: "Ustawienia", description: "Preferencje i słowniki", icon: "settings" },
    ],
  },
];

export const companyAdminNavigation: DashboardNavGroup = {
  label: "Organizacja",
  items: [
    { href: "/panel/firma", label: "Moja firma", description: "Zespół, role i zaproszenia", icon: "companies" },
  ],
};

export const adminDashboardNavigation: readonly DashboardNavGroup[] = [
  {
    label: "Zarządzanie",
    items: [
      { href: "/admin", label: "Dashboard", description: "Widok administracyjny", icon: "admin-dashboard", exact: true },
      { href: "/admin/firmy", label: "Firmy", description: "Organizacje i zespoły", icon: "companies" },
      { href: "/admin/uzytkownicy", label: "Użytkownicy", description: "Konta i role", icon: "users" },
      { href: "/admin/zaproszenia", label: "Zaproszenia", description: "Dostęp przez e-mail", icon: "invitations" },
      { href: "/admin/stanowiska", label: "Stanowiska", description: "Funkcje w firmach", icon: "positions" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/panel/analizy", label: "Wszystkie analizy", description: "Analizy dostępne administratorowi", icon: "analyses" },
      { href: "/admin/rozwoj", label: "Rozwój systemu", description: "Wersje i roadmapa", icon: "dashboard" },
      { href: "/panel/profil", label: "Mój profil", description: "Dane administratora", icon: "profile" },
    ],
  },
];
