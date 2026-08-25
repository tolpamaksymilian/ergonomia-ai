import Link from "next/link";
import { ArrowRight, BriefcaseBusiness, CheckCircle2, Clock3, FileText, Plus, Video } from "lucide-react";

import { getAnalysisStatusDefinition } from "@/config/analysis-status";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";

export default async function UserPanelPage() {
  const { supabase, profile } = await requireUser();
  const [{ count: analysesCount }, { count: completedCount }, { count: workstationCount }, { data: latest }] = await Promise.all([
    supabase.from("analyses").select("id", { count: "exact", head: true }),
    supabase.from("analyses").select("id", { count: "exact", head: true }).eq("status", "completed"),
    supabase.from("workstations").select("id", { count: "exact", head: true }).eq("is_active", true),
    supabase.from("analyses").select("id,title,status,processing_stage,progress,analysis_type,created_at,report_path").order("created_at", { ascending: false }).limit(5),
  ]);
  const inProgress = (latest ?? []).filter((item) => !["completed", "failed", "cancelled"].includes(item.status)).length;
  return <div className="dashboard-page">
    <section className="flex flex-col justify-between gap-5 rounded-3xl bg-gradient-to-br from-[#171a31] via-[#1d2040] to-violet-950 p-6 text-white shadow-xl sm:p-8 lg:flex-row lg:items-end">
      <div><p className="text-xs font-bold uppercase tracking-[0.2em] text-violet-300">Centrum pracy</p><h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">Dzień dobry, {firstName(profile?.full_name)}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">Zarządzaj analizami stanowisk, śledź przetwarzanie i otwieraj gotowe raporty w jednym miejscu.</p></div>
      <Link href="/panel/analizy/nowa" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-violet-500 px-5 font-bold text-white shadow-lg shadow-violet-950/40 transition hover:bg-violet-400"><Plus className="size-5" />Nowa analiza</Link>
    </section>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard icon={Video} label="Wszystkie analizy" value={analysesCount ?? 0} hint="Wideo i projekty zdjęciowe" color="violet" />
      <MetricCard icon={CheckCircle2} label="Gotowe" value={completedCount ?? 0} hint="Zakończony pełny pipeline" color="emerald" />
      <MetricCard icon={Clock3} label="Ostatnio aktywne" value={inProgress} hint="Wśród ostatnich pięciu" color="amber" />
      <MetricCard icon={BriefcaseBusiness} label="Stanowiska" value={workstationCount ?? 0} hint="Aktywne stanowiska pracy" color="sky" />
    </section>
    <section className="grid gap-6 xl:grid-cols-[1.5fr_0.7fr]">
      <div className="dashboard-card overflow-hidden">
        <div className="flex items-center justify-between gap-4 border-b border-border p-5"><div><p className="dashboard-eyebrow">Ostatnia aktywność</p><h2 className="mt-1 text-xl font-bold">Najnowsze analizy</h2></div><Link href="/panel/analizy" className="text-sm font-bold text-violet-600 hover:text-violet-500">Pokaż wszystkie</Link></div>
        <div className="divide-y divide-border">{latest?.length ? latest.map((item) => { const definition = getAnalysisStatusDefinition(item.status, item.processing_stage); return <Link key={item.id} href={(item.analysis_type ?? "VIDEO") === "PHOTO_SCENE" ? `/panel/analizy/${item.id}/scena` : `/panel/analizy/${item.id}`} className="flex items-center gap-4 p-4 transition hover:bg-surface-muted">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-500/10 text-violet-600">{item.report_path ? <FileText className="size-5" /> : <Video className="size-5" />}</span><span className="min-w-0 flex-1"><span className="block truncate font-bold">{item.title}</span><span className="mt-1 block text-xs text-muted-foreground">{formatDate(item.created_at)} · {item.progress}%</span></span><span className="dashboard-status border-border bg-surface-muted text-muted-foreground">{definition.shortLabel}</span><ArrowRight className="size-4 text-muted-foreground" />
        </Link>; }) : <EmptyState text="Nie masz jeszcze żadnych analiz." />}</div>
      </div>
      <aside className="dashboard-card p-5"><p className="dashboard-eyebrow">Szybkie akcje</p><h2 className="mt-1 text-xl font-bold">Co chcesz zrobić?</h2><div className="mt-5 grid gap-3">
        <QuickLink href="/panel/analizy/nowa" title="Rozpocznij analizę" description="Film lub projekt ze zdjęcia" />
        <QuickLink href="/panel/raporty" title="Przejrzyj raporty" description="Gotowe wyniki i podsumowania" />
        <QuickLink href="/panel/stanowiska" title="Uporządkuj stanowiska" description="Nazwy, kody i obszary pracy" />
        <QuickLink href="/panel/profil" title="Sprawdź profil" description="Firma, rola i preferencje" />
      </div></aside>
    </section>
  </div>;
}

function MetricCard({ icon: Icon, label, value, hint, color }: { icon: typeof Video; label: string; value: number; hint: string; color: "violet" | "emerald" | "amber" | "sky" }) { const styles = { violet: "bg-violet-500/10 text-violet-600", emerald: "bg-emerald-500/10 text-emerald-600", amber: "bg-amber-500/10 text-amber-600", sky: "bg-sky-500/10 text-sky-600" }; return <article className="dashboard-card p-5"><div className="flex items-start justify-between"><span className={`grid size-11 place-items-center rounded-xl ${styles[color]}`}><Icon className="size-5" /></span><span className="text-3xl font-bold">{value}</span></div><p className="mt-5 font-bold">{label}</p><p className="mt-1 text-xs text-muted-foreground">{hint}</p></article>; }
function QuickLink({ href, title, description }: { href: string; title: string; description: string }) { return <Link href={href} className="group flex items-center justify-between rounded-xl border border-border p-4 transition hover:border-violet-400 hover:bg-violet-500/5"><span><span className="block text-sm font-bold">{title}</span><span className="mt-1 block text-xs text-muted-foreground">{description}</span></span><ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-1 group-hover:text-violet-600" /></Link>; }
function EmptyState({ text }: { text: string }) { return <div className="p-10 text-center text-sm text-muted-foreground">{text}</div>; }
function firstName(value: string | null | undefined) { return value?.trim().split(/\s+/)[0] || "Użytkowniku"; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
