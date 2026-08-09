export default function AnalysisLoading() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] px-4 py-6 text-white sm:px-8" aria-busy="true" aria-label="Ładowanie danych analizy">
      <div className="mx-auto max-w-[1540px] animate-pulse space-y-6 motion-reduce:animate-none">
        <div className="h-48 rounded-[28px] border border-white/[0.06] bg-white/[0.035]" />
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
          <div className="aspect-video rounded-[28px] border border-white/[0.06] bg-slate-900/70" />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            {Array.from({ length: 5 }, (_, index) => <div key={index} className="h-24 rounded-2xl border border-white/[0.06] bg-white/[0.03]" />)}
          </div>
        </div>
        <div className="h-64 rounded-[28px] border border-white/[0.06] bg-white/[0.03]" />
      </div>
    </main>
  );
}
