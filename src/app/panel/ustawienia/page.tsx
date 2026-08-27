import Link from "next/link";
import { ArrowRight, Bell, Building2, Settings2, Tags, UsersRound } from "lucide-react";

export default function SettingsPage() {
  return <div className="dashboard-page">
    <header><p className="dashboard-eyebrow">Konfiguracja</p><h1 className="dashboard-title mt-2">Ustawienia</h1><p className="dashboard-muted mt-2">Dane konta i słowniki wykorzystywane podczas codziennej pracy.</p></header>
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Setting href="/panel/profil" icon={UsersRound} title="Konto i profil" description="Dane osobowe, firma, stanowisko i role." />
      <Setting href="/panel/ustawienia/kategorie" icon={Tags} title="Kategorie analiz" description="Grupy i etykiety używane do filtrowania." />
      <Setting href="/panel/stanowiska" icon={Building2} title="Stanowiska pracy" description="Słownik miejsc i procesów analizowanych." />
      <Setting icon={Bell} title="Powiadomienia" description="Centrum powiadomień jest przygotowane do przyszłej konfiguracji." planned />
      <Setting icon={Settings2} title="Integracje" description="Brak aktywnych integracji zewnętrznych." planned />
    </section>
  </div>;
}

function Setting({ href, icon: Icon, title, description, planned = false }: { href?: string; icon: typeof Settings2; title: string; description: string; planned?: boolean }) {
  const content = <><div className="flex items-start justify-between"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><Icon className="size-5" /></span>{planned ? <span className="ui-chip">Planowane</span> : href ? <ArrowRight className="size-4 text-muted-foreground" /> : null}</div><h2 className="mt-5 font-bold">{title}</h2><p className="dashboard-muted mt-2">{description}</p></>;
  return href ? <Link href={href} className="dashboard-card group p-5 transition hover:-translate-y-0.5 hover:border-violet-400">{content}</Link> : <article className="dashboard-card p-5 opacity-75">{content}</article>;
}
