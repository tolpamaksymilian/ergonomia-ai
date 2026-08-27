import Link from "next/link";
import { ArrowRight, BriefcaseBusiness, CheckCircle2, Clock3, FileText, MailPlus, Plus, UsersRound, Video } from "lucide-react";

import { getAnalysisStatusDefinition } from "@/config/analysis-status";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function UserPanelPage() {
  const { supabase, profile } = await requireUser();
  const isCompanyAdmin = profile?.company_role === "admin" && profile.account_status === "active" && Boolean(profile.company_id);
  const companyId = profile?.company_id ?? "";
  const companyStatsPromise = isCompanyAdmin
    ? Promise.all([
      supabase.from("profiles").select("id", { count: "exact", head: true }).eq("company_id", companyId),
      supabase.from("company_invitations").select("id", { count: "exact", head: true }).eq("company_id", companyId).eq("status", "pending"),
    ])
    : Promise.resolve([{ count: 0 }, { count: 0 }]);
  const [{ count: analysesCount }, { count: completedCount }, { count: workstationCount }, { data: latest }, [teamResult, invitationResult]] = await Promise.all([
    supabase.from("analyses").select("id", { count: "exact", head: true }),
    supabase.from("analyses").select("id", { count: "exact", head: true }).eq("status", "completed"),
    supabase.from("workstations").select("id", { count: "exact", head: true }).eq("is_active", true),
    supabase.from("analyses").select("id,title,status,processing_stage,progress,analysis_type,created_at,report_path").order("created_at", { ascending: false }).limit(5),
    companyStatsPromise,
  ]);

  return <div className="dashboard-page">
    <section className="flex flex-col justify-between gap-5 rounded-3xl border border-violet-400/15 bg-gradient-to-br from-[#171a31] via-[#1d2040] to-violet-950 p-6 text-white shadow-xl sm:p-8 lg:flex-row lg:items-end"><div><p className="text-xs font-bold uppercase tracking-[0.2em] text-violet-300">Centrum pracy</p><h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">Dzień dobry, {firstName(profile?.full_name)}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">Analizy, zespół i stanowiska są dostępne z jednej uporządkowanej przestrzeni.</p></div><Link href="/panel/analizy/nowa" className="ui-button-primary min-h-12 px-5"><Plus className="size-5" />Nowa analiza</Link></section>

    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {isCompanyAdmin ? <>
        <MetricCard icon={UsersRound} label="Zespół" value={teamResult.count ?? 0} hint="Członkowie Twojej firmy" color="violet" />
        <MetricCard icon={Video} label="Analizy" value={analysesCount ?? 0} hint="Dostępne analizy" color="sky" />
        <MetricCard icon={BriefcaseBusiness} label="Stanowiska" value={workstationCount ?? 0} hint="Aktywne stanowiska pracy" color="emerald" />
        <MetricCard icon={MailPlus} label="Oczekujące zaproszenia" value={invitationResult.count ?? 0} hint="Osoby przed aktywacją" color="amber" />
      </> : <>
        <MetricCard icon={Video} label="Analizy" value={analysesCount ?? 0} hint="Wideo i projekty zdjęciowe" color="violet" />
        <MetricCard icon={CheckCircle2} label="Zakończone" value={completedCount ?? 0} hint="Gotowe wyniki" color="emerald" />
        <MetricCard icon={BriefcaseBusiness} label="Stanowiska" value={workstationCount ?? 0} hint="Aktywne stanowiska pracy" color="sky" />
        <MetricCard icon={Clock3} label="Ostatnia analiza" value={latest?.[0] ? formatShortDate(latest[0].created_at) : "—"} hint={latest?.[0]?.title ?? "Brak analiz"} color="amber" />
      </>}
    </section>

    <section className="grid gap-6 xl:grid-cols-[1.5fr_0.7fr]">
      <div className="dashboard-card overflow-hidden"><div className="flex items-center justify-between gap-4 border-b border-border p-5"><div><p className="dashboard-eyebrow">Ostatnia aktywność</p><h2 className="mt-1 text-xl font-bold">Najnowsze analizy</h2></div><Link href="/panel/analizy" className="text-sm font-bold text-violet-300 hover:text-violet-200">Pokaż wszystkie</Link></div><div className="divide-y divide-border">{latest?.length ? latest.map((item) => { const definition = getAnalysisStatusDefinition(item.status, item.processing_stage); return <Link key={item.id} href={(item.analysis_type ?? "VIDEO") === "PHOTO_SCENE" ? `/panel/analizy/${item.id}/scena` : `/panel/analizy/${item.id}`} className="flex items-center gap-4 p-4 transition hover:bg-surface-muted"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-500/12 text-violet-300">{item.report_path ? <FileText className="size-5" /> : <Video className="size-5" />}</span><span className="min-w-0 flex-1"><span className="block truncate font-bold">{item.title}</span><span className="mt-1 block text-xs text-muted-foreground">{formatDate(item.created_at)} · {item.progress}%</span></span><span className="dashboard-status dashboard-status-neutral">{definition.shortLabel}</span><ArrowRight className="size-4 text-muted-foreground" /></Link>; }) : <div className="dashboard-empty m-4 min-h-52"><Video className="size-9" /><h3>Nie masz jeszcze analiz</h3><p>Utwórz pierwszą analizę filmu lub zdjęcia stanowiska.</p><Link href="/panel/analizy/nowa" className="ui-button-primary"><Plus className="size-4" />Nowa analiza</Link></div>}</div></div>
      <aside className="dashboard-card p-5"><p className="dashboard-eyebrow">Szybkie akcje</p><h2 className="mt-1 text-xl font-bold">Co chcesz zrobić?</h2><div className="mt-5 grid gap-3"><QuickLink href="/panel/analizy/nowa" title="Nowa analiza" description="Film lub projekt ze zdjęcia" />{isCompanyAdmin && <><QuickLink href="/panel/firma#zespol" title="Dodaj członka" description="Zaproś osobę do firmy" /><QuickLink href="/panel/firma#stanowiska" title="Dodaj stanowisko" description="Rozbuduj strukturę zespołu" /></>}<QuickLink href="/panel/raporty" title="Przejrzyj raporty" description="Gotowe wyniki i podsumowania" /><QuickLink href="/panel/stanowiska" title="Stanowiska pracy" description="Miejsca i procesy analizowane" /></div></aside>
    </section>
  </div>;
}

function MetricCard({ icon: Icon, label, value, hint, color }: { icon: typeof Video; label: string; value: number | string; hint: string; color: "violet" | "emerald" | "amber" | "sky" }) { const styles = { violet: "bg-violet-500/12 text-violet-300", emerald: "bg-emerald-500/12 text-emerald-300", amber: "bg-amber-500/12 text-amber-200", sky: "bg-sky-500/12 text-sky-300" }; return <article className="dashboard-card p-5"><div className="flex items-start justify-between gap-4"><span className={`grid size-11 place-items-center rounded-xl ${styles[color]}`}><Icon className="size-5" /></span><span className="truncate text-3xl font-bold">{value}</span></div><p className="mt-5 font-bold">{label}</p><p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p></article>; }
function QuickLink({ href, title, description }: { href: string; title: string; description: string }) { return <Link href={href} className="group flex items-center justify-between rounded-xl border border-border p-4 transition hover:border-violet-400 hover:bg-violet-500/6"><span><span className="block text-sm font-bold">{title}</span><span className="mt-1 block text-xs text-muted-foreground">{description}</span></span><ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-1 group-hover:text-violet-300" /></Link>; }
function firstName(value: string | null | undefined) { return value?.trim().split(/\s+/)[0] || "Użytkowniku"; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function formatShortDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { day: "2-digit", month: "short" }).format(new Date(value)); }
