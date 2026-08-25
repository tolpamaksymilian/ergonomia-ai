import Link from "next/link";
import { Activity, ArrowRight, Building2, MailPlus, ShieldCheck, UsersRound, Video } from "lucide-react";

import { requireAdmin } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const { supabase } = await requireAdmin();
  const [{ count: companies }, { count: users }, { count: invitations }, { count: analyses }, { data: recent }] = await Promise.all([
    supabase.from("companies").select("id", { count: "exact", head: true }),
    supabase.from("profiles").select("id", { count: "exact", head: true }),
    supabase.from("company_invitations").select("id", { count: "exact", head: true }).eq("status", "pending"),
    supabase.from("analyses").select("id", { count: "exact", head: true }),
    supabase.from("profiles").select("id,full_name,role,account_status,created_at,company:companies(name)").order("created_at", { ascending: false }).limit(6),
  ]);
  return <div className="dashboard-page">
    <section className="flex flex-col justify-between gap-5 rounded-3xl bg-gradient-to-br from-[#171a31] via-[#1d2040] to-violet-950 p-7 text-white shadow-xl lg:flex-row lg:items-center"><div><span className="inline-flex items-center gap-2 rounded-full bg-white/8 px-3 py-1.5 text-xs font-bold text-violet-200"><ShieldCheck className="size-4" />Centrum administracyjne</span><h1 className="mt-4 text-3xl font-bold sm:text-4xl">Kontrola organizacji i dostępu</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">Firmy, konta, zaproszenia i stan systemu są dostępne z jednej, uporządkowanej przestrzeni.</p></div><Link href="/admin/zaproszenia" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-violet-500 px-5 font-bold hover:bg-violet-400"><MailPlus className="size-5" />Zaproś użytkownika</Link></section>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><AdminMetric icon={Building2} label="Firmy" value={companies} href="/admin/firmy" /><AdminMetric icon={UsersRound} label="Użytkownicy" value={users} href="/admin/uzytkownicy" /><AdminMetric icon={MailPlus} label="Oczekujące zaproszenia" value={invitations} href="/admin/zaproszenia" /><AdminMetric icon={Video} label="Analizy" value={analyses} href="/panel/analizy" /></section>
    <section className="grid gap-6 xl:grid-cols-[1.4fr_0.6fr]"><div className="dashboard-card overflow-hidden"><div className="border-b border-border p-5"><p className="dashboard-eyebrow">Ostatnio dodani</p><h2 className="mt-1 text-xl font-bold">Nowe konta</h2></div><div className="divide-y divide-border">{recent?.map((item) => <div key={item.id} className="flex items-center gap-4 p-4"><span className="grid size-10 place-items-center rounded-xl bg-violet-500/10 font-bold text-violet-600">{(item.full_name || "U")[0]}</span><span className="min-w-0 flex-1"><span className="block truncate font-bold">{item.full_name || "Użytkownik bez nazwy"}</span><span className="block truncate text-xs text-muted-foreground">{companyName(item.company)}</span></span><span className="dashboard-status border-border bg-surface-muted text-muted-foreground">{item.role === "admin" ? "Super admin" : item.account_status ?? "Aktywny"}</span></div>)}</div></div>
      <aside className="dashboard-card p-5"><p className="dashboard-eyebrow">System</p><h2 className="mt-1 text-xl font-bold">Skróty administratora</h2><div className="mt-5 space-y-3"><AdminLink href="/admin/firmy" icon={Building2} title="Dodaj firmę" /><AdminLink href="/admin/uzytkownicy" icon={UsersRound} title="Zarządzaj rolami" /><AdminLink href="/admin/rozwoj" icon={Activity} title="Stan i roadmapa" /></div></aside></section>
  </div>;
}
function AdminMetric({ icon: Icon, label, value, href }: { icon: typeof Building2; label: string; value: number | null; href: string }) { return <Link href={href} className="dashboard-card group p-5 transition hover:-translate-y-0.5 hover:border-violet-400"><div className="flex items-center justify-between"><span className="grid size-11 place-items-center rounded-xl bg-violet-500/10 text-violet-600"><Icon className="size-5" /></span><ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-1" /></div><p className="mt-5 text-3xl font-bold">{value ?? "—"}</p><p className="mt-1 text-sm text-muted-foreground">{label}</p></Link>; }
function AdminLink({ href, icon: Icon, title }: { href: string; icon: typeof Building2; title: string }) { return <Link href={href} className="flex items-center gap-3 rounded-xl border border-border p-3 font-semibold transition hover:border-violet-400 hover:bg-violet-500/5"><Icon className="size-4 text-violet-600" /><span className="flex-1">{title}</span><ArrowRight className="size-4 text-muted-foreground" /></Link>; }
function companyName(value: unknown) { if (Array.isArray(value)) return (value[0] as { name?: string } | undefined)?.name ?? "Bez firmy"; return (value as { name?: string } | null)?.name ?? "Bez firmy"; }
