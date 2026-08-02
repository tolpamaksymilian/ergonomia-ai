import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function TestBazyPage() {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("system_status")
    .select("app_name, status, version, updated_at")
    .eq("id", 1)
    .single();

  if (error) {
    return (
      <main className="min-h-screen bg-slate-950 p-8 text-white">
        <div className="mx-auto max-w-3xl rounded-2xl border border-red-500/30 bg-red-500/10 p-8">
          <p className="text-sm font-semibold uppercase tracking-widest text-red-300">
            Błąd połączenia
          </p>

          <h1 className="mt-3 text-3xl font-bold">
            Nie udało się pobrać danych z Supabase
          </h1>

          <pre className="mt-6 overflow-auto rounded-xl bg-black/40 p-4 text-sm text-red-200">
            {error.message}
          </pre>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 p-8 text-white">
      <div className="mx-auto max-w-3xl rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-8">
        <p className="text-sm font-semibold uppercase tracking-widest text-emerald-300">
          Połączenie aktywne
        </p>

        <h1 className="mt-3 text-4xl font-bold">{data.app_name}</h1>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-black/30 p-4">
            <p className="text-sm text-slate-400">Status</p>
            <p className="mt-1 font-semibold text-emerald-300">
              {data.status}
            </p>
          </div>

          <div className="rounded-xl bg-black/30 p-4">
            <p className="text-sm text-slate-400">Wersja</p>
            <p className="mt-1 font-semibold">{data.version}</p>
          </div>

          <div className="rounded-xl bg-black/30 p-4">
            <p className="text-sm text-slate-400">Baza danych</p>
            <p className="mt-1 font-semibold">Supabase PostgreSQL</p>
          </div>
        </div>
      </div>
    </main>
  );
}