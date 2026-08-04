import { CheckCircle2, Clock3, Gauge } from "lucide-react";

const stages = [
  { title: "Pozycja", status: "Gotowe", icon: CheckCircle2, active: false },
  { title: "Metryki", status: "Oczekuje", icon: Gauge, active: true },
  { title: "Ocena ryzyka", status: "W przygotowaniu", icon: Clock3, active: false },
] as const;

export function AnalysisAvailability() {
  return (
    <section className="rounded-[26px] border border-emerald-400/20 bg-emerald-400/[0.055] p-5 sm:p-6" aria-labelledby="analysis-availability-title">
      <div className="flex items-start gap-4">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
          <CheckCircle2 className="size-5 text-emerald-300" aria-hidden="true" />
        </div>
        <div>
          <h2 id="analysis-availability-title" className="text-lg font-semibold text-emerald-100">Pozycja została wykryta</h2>
          <p className="mt-1.5 text-sm text-slate-400">Czekamy na obliczenie metryk.</p>
        </div>
      </div>
      <ol className="mt-5 grid gap-2 sm:grid-cols-3">
        {stages.map((stage) => {
          const Icon = stage.icon;
          return (
            <li key={stage.title} className="flex min-w-0 items-center gap-3 rounded-xl border border-white/[0.07] bg-slate-950/30 p-3">
              <Icon className={`size-4 shrink-0 ${stage.active ? "text-cyan-300" : "text-slate-500"}`} aria-hidden="true" />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-200">{stage.title}</p>
                <p className="text-xs text-slate-500">{stage.status}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
