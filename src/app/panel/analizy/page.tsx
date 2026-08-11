import Link from "next/link";
import { ArrowLeft, CalendarDays, FileVideo, Plus, Search, SlidersHorizontal } from "lucide-react";

import { getAnalysisStatusDefinition } from "@/config/analysis-status";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { requireUser } from "@/lib/auth/access";

export const dynamic = "force-dynamic";
const PAGE_SIZE = 24;
const statuses = ["uploading", "queued", "processing", "completed", "failed", "cancelled"] as const;

type Params = { q?: string; status?: string; workstation?: string; category?: string | string[]; category_mode?: string; group?: string; from?: string; to?: string; sort?: string; page?: string };
type HistoryRow = { id: string; title: string; description: string | null; status: string; progress: number; processing_stage: string | null; source_file_name: string; created_at: string; analysis_date: string | null; report_path: string | null; workstation: { id: string; name: string; code: string | null } | null; analysis_category_links: Array<{ category: { id: string; name: string; group_name: string } | null }> };

export default async function AnalysesPage({ searchParams }: { searchParams: Promise<Params> }) {
  const raw = await searchParams;
  const { supabase } = await requireUser();
  const q = clean(raw.q, 100);
  const status = statuses.includes(raw.status as typeof statuses[number]) ? raw.status! : "";
  const workstation = uuid(raw.workstation) ? raw.workstation! : "";
  const categoryIds = values(raw.category).filter(uuid);
  const mode = raw.category_mode === "or" ? "or" : "and";
  const group = clean(raw.group, 80);
  const page = Math.max(1, Number.parseInt(raw.page ?? "1", 10) || 1);
  const sort = ["oldest", "name-asc", "name-desc"].includes(raw.sort ?? "") ? raw.sort! : "newest";

  const [{ data: workstations }, { data: categories }] = await Promise.all([
    supabase.from("workstations").select("id,name,code").eq("is_active", true).order("name"),
    supabase.from("analysis_categories").select("id,name,group_name").eq("is_active", true).order("group_name").order("name"),
  ]);

  let matchingIds: string[] | null = null;
  if (categoryIds.length) {
    const { data: links } = await supabase.from("analysis_category_links").select("analysis_id,category_id").in("category_id", categoryIds);
    const grouped = new Map<string, Set<string>>();
    for (const link of links ?? []) { const set = grouped.get(link.analysis_id) ?? new Set<string>(); set.add(link.category_id); grouped.set(link.analysis_id, set); }
    matchingIds = [...grouped].filter(([, found]) => mode === "or" ? found.size > 0 : categoryIds.every((id) => found.has(id))).map(([id]) => id);
  }
  if (group && !categoryIds.length) {
    const groupedCategoryIds = (categories ?? []).filter((item) => item.group_name === group).map((item) => item.id);
    const { data: groupLinks } = groupedCategoryIds.length ? await supabase.from("analysis_category_links").select("analysis_id").in("category_id", groupedCategoryIds) : { data: [] };
    matchingIds = [...new Set((groupLinks ?? []).map((item) => item.analysis_id))];
  }

  let query = supabase.from("analyses").select("id,title,description,status,progress,processing_stage,source_file_name,created_at,analysis_date,report_path,workstation:workstations(id,name,code),analysis_category_links(category:analysis_categories(id,name,group_name))", { count: "exact" });
  if (status) query = query.eq("status", status);
  if (workstation) query = query.eq("workstation_id", workstation);
  if (raw.from && /^\d{4}-\d{2}-\d{2}$/.test(raw.from)) query = query.gte("created_at", `${raw.from}T00:00:00`);
  if (raw.to && /^\d{4}-\d{2}-\d{2}$/.test(raw.to)) query = query.lte("created_at", `${raw.to}T23:59:59.999`);
  if (matchingIds) query = matchingIds.length ? query.in("id", matchingIds) : query.eq("id", "00000000-0000-0000-0000-000000000000");
  if (q) {
    const lowered = q.toLocaleLowerCase("pl");
    const workstationIds = (workstations ?? []).filter((item) => item.name.toLocaleLowerCase("pl").includes(lowered) || item.code?.toLocaleLowerCase("pl").includes(lowered)).map((item) => item.id);
    const matchedCategoryIds = (categories ?? []).filter((item) => item.name.toLocaleLowerCase("pl").includes(lowered)).map((item) => item.id);
    const { data: categorySearchLinks } = matchedCategoryIds.length ? await supabase.from("analysis_category_links").select("analysis_id").in("category_id", matchedCategoryIds) : { data: [] };
    const categoryAnalysisIds = [...new Set((categorySearchLinks ?? []).map((item) => item.analysis_id))];
    const filters = [`title.ilike.%${q}%`, `source_file_name.ilike.%${q}%`, `analysis_context->>process_name.ilike.%${q}%`];
    if (workstationIds.length) filters.push(`workstation_id.in.(${workstationIds.join(",")})`);
    if (categoryAnalysisIds.length) filters.push(`id.in.(${categoryAnalysisIds.join(",")})`);
    query = query.or(filters.join(","));
  }
  query = sort === "oldest" ? query.order("created_at", { ascending: true }) : sort === "name-asc" ? query.order("title", { ascending: true }) : sort === "name-desc" ? query.order("title", { ascending: false }) : query.order("created_at", { ascending: false });
  const { data, error, count } = await query.range((page - 1) * PAGE_SIZE, page * PAGE_SIZE - 1);
  const analyses = (data ?? []) as unknown as HistoryRow[];
  const pages = Math.max(1, Math.ceil((count ?? 0) / PAGE_SIZE));
  const active = Boolean(q || status || workstation || categoryIds.length || raw.from || raw.to || raw.group);

  return <main className="ui-page px-4 py-6 sm:px-8">
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="ui-surface flex flex-wrap items-center justify-between gap-4 p-5"><div><Link href="/panel" className="inline-flex items-center gap-2 text-sm text-muted-foreground"><ArrowLeft className="size-4" />Panel</Link><h1 className="mt-3 text-3xl font-bold tracking-tight">Historia analiz</h1><p className="mt-1 text-sm text-muted-foreground">Wyszukuj analizy według stanowiska, procesu, kategorii i daty.</p></div><div className="flex flex-wrap items-center gap-2"><ThemeToggle /><Link href="/panel/ustawienia/kategorie" className="ui-button-secondary text-sm">Kategorie</Link><Link href="/panel/analizy/nowa" className="ui-button-primary text-sm"><Plus className="size-4" />Nowa analiza</Link></div></header>
      <form className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"><div className="grid gap-4 lg:grid-cols-4"><label className="lg:col-span-2 text-sm font-medium">Szukaj analiz…<span className="relative mt-1 block"><Search className="absolute left-3 top-3.5 size-4 text-slate-400" /><input name="q" defaultValue={q} className="min-h-11 w-full rounded-xl border border-slate-300 pl-10 pr-3" placeholder="Nazwa, plik lub proces" /></span></label><Select name="status" label="Status" value={status} options={[["", "Wszystkie"], ...statuses.map((item) => [item, getAnalysisStatusDefinition(item, null).shortLabel] as const)]} /><Select name="workstation" label="Stanowisko" value={workstation} options={[["", "Wszystkie"], ...(workstations ?? []).map((item) => [item.id, item.name] as const)]} /><label className="text-sm font-medium">Data od<input type="date" name="from" defaultValue={raw.from ?? ""} className="mt-1 min-h-11 w-full rounded-xl border border-slate-300 px-3" /></label><label className="text-sm font-medium">Data do<input type="date" name="to" defaultValue={raw.to ?? ""} className="mt-1 min-h-11 w-full rounded-xl border border-slate-300 px-3" /></label><Select name="sort" label="Sortowanie" value={sort} options={[["newest","Najnowsze"],["oldest","Najstarsze"],["name-asc","Nazwa A–Z"],["name-desc","Nazwa Z–A"]]} /><Select name="group" label="Grupa kategorii" value={group} options={[["","Wszystkie"], ...[...new Set((categories ?? []).map((item) => item.group_name))].map((item) => [item,item] as const)]} /><Select name="category_mode" label="Dopasuj kategorie" value={mode} options={[["and","Wszystkie (AND)"],["or","Dowolną (OR)"]]} /></div><details className="mt-4"><summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold"><SlidersHorizontal className="size-4" />Kategorie</summary><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{(categories ?? []).map((item) => <label key={item.id} className="flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm"><input type="checkbox" name="category" value={item.id} defaultChecked={categoryIds.includes(item.id)} />{item.group_name}: {item.name}</label>)}</div></details><div className="mt-5 flex flex-wrap gap-2"><button className="min-h-11 rounded-xl bg-slate-900 px-5 font-semibold text-white">Zastosuj filtry</button>{active && <Link href="/panel/analizy" className="min-h-11 rounded-xl border border-slate-300 px-5 py-3 font-semibold">Wyczyść filtry</Link>}</div></form>
      {active && <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-semibold text-slate-500">Aktywne filtry:</span>{q && <span className="rounded-full bg-white px-3 py-1 text-xs shadow-sm">Szukaj: {q}</span>}{status && <span className="rounded-full bg-white px-3 py-1 text-xs shadow-sm">Status: {getAnalysisStatusDefinition(status,null).shortLabel}</span>}{workstation && <span className="rounded-full bg-white px-3 py-1 text-xs shadow-sm">Stanowisko: {(workstations??[]).find((item)=>item.id===workstation)?.name}</span>}{group && <span className="rounded-full bg-white px-3 py-1 text-xs shadow-sm">Grupa: {group}</span>}{categoryIds.map((id)=><span key={id} className="rounded-full bg-white px-3 py-1 text-xs shadow-sm">Kategoria: {(categories??[]).find((item)=>item.id===id)?.name}</span>)}</div>}
      {error && <p className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800">Nie udało się pobrać historii analiz.</p>}
      {!error && !analyses.length && <section className="rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center"><FileVideo className="mx-auto size-9 text-slate-400" /><h2 className="mt-4 text-xl font-bold">Nie znaleziono analiz spełniających wybrane kryteria.</h2>{active && <Link href="/panel/analizy" className="mt-4 inline-block font-semibold text-emerald-700">Pokaż wszystkie</Link>}</section>}
      {!!analyses.length && <><div className="flex justify-between text-sm text-slate-500"><span>Znaleziono {count ?? analyses.length} analiz</span><span>Strona {page} z {pages}</span></div><section className="grid gap-4 lg:grid-cols-2">{analyses.map((analysis) => { const statusDef = getAnalysisStatusDefinition(analysis.status, analysis.processing_stage); const chips = analysis.analysis_category_links.map((link) => link.category).filter((item): item is NonNullable<typeof item> => Boolean(item)); return <article key={analysis.id} className="min-w-0 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="truncate text-lg font-bold"><Link href={`/panel/analizy/${analysis.id}`}>{analysis.title}</Link></h2><p className="mt-1 text-sm text-slate-500">{analysis.workstation?.name ?? "Bez stanowiska"}{analysis.workstation?.code ? ` · ${analysis.workstation.code}` : ""}</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold">{statusDef.shortLabel}</span></div><div className="mt-4 flex flex-wrap gap-2">{chips.slice(0,3).map((item) => <span key={item.id} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">{item.name}</span>)}{chips.length > 3 && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs">+{chips.length - 3}</span>}</div><div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4"><span className="flex items-center gap-2 text-xs text-slate-500"><CalendarDays className="size-4" />{formatDate(analysis.analysis_date ?? analysis.created_at)}</span><div className="flex gap-2"><Link href={`/panel/analizy/${analysis.id}`} className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold">Otwórz</Link>{analysis.report_path && <Link href={`/panel/analizy/${analysis.id}/raport`} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">Raport</Link>}</div></div></article>; })}</section><nav className="flex justify-center gap-3">{page > 1 && <Link href={pageHref(raw, page - 1)} className="rounded-xl border border-slate-300 bg-white px-4 py-2">Poprzednia</Link>}{page < pages && <Link href={pageHref(raw, page + 1)} className="rounded-xl border border-slate-300 bg-white px-4 py-2">Następna</Link>}</nav></>}
    </div>
  </main>;
}

function Select({ name, label, value, options }: { name: string; label: string; value: string; options: ReadonlyArray<readonly [string,string]> }) { return <label className="text-sm font-medium">{label}<select name={name} defaultValue={value} className="mt-1 min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3">{options.map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>; }
function values(value: string | string[] | undefined) { return Array.isArray(value) ? value : value ? [value] : []; }
function uuid(value: string | undefined): value is string { return Boolean(value && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value)); }
function clean(value: string | undefined, max: number) { return (value ?? "").trim().slice(0,max).replace(/[,%()]/g, " "); }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "medium" }).format(new Date(value)); }
function pageHref(raw: Params, page: number) { const params = new URLSearchParams(); for (const [key,value] of Object.entries(raw)) for (const item of values(value)) if (item) params.append(key,item); params.set("page",String(page)); return `/panel/analizy?${params}`; }
