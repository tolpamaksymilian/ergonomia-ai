import { CheckCircle2, CircleDashed, FileClock, Gauge } from "lucide-react";

const stages = [
  {
    title: "Dane pozy",
    status: "Gotowe",
    description: "Pose Pipeline V3.0 zakończył analizę i zapisał zatwierdzone punkty.",
    icon: CheckCircle2,
    className: "border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-200",
  },
  {
    title: "Metryki ergonomiczne",
    status: "Oczekują",
    description: "Osobny Ergonomics Worker V1 automatycznie przejmie dane pozy z kolejki.",
    icon: Gauge,
    className: "border-cyan-400/20 bg-cyan-400/[0.07] text-cyan-200",
  },
  {
    title: "Ocena i raport",
    status: "Niedostępne",
    description: "Końcowa ocena ryzyka, wykresy i raport są etapami planowanymi.",
    icon: FileClock,
    className: "border-white/10 bg-white/[0.035] text-slate-400",
  },
] as const;

export function AnalysisAvailability() {
  return (
    <section
      className="rounded-[26px] border border-white/10 bg-slate-950/35 p-5 sm:p-6"
      aria-labelledby="analysis-availability-title"
    >
      <div className="flex items-start gap-4">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10">
          <CheckCircle2 className="size-5 text-emerald-300" aria-hidden="true" />
        </div>
        <div>
          <h2 id="analysis-availability-title" className="text-lg font-semibold text-emerald-100">
            Analiza pozy została zakończona
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Dane oczekują na osobny Ergonomics Worker. Wyniki pozy pozostają
            zachowane niezależnie od powodzenia kolejnego etapu.
          </p>
        </div>
      </div>

      <ol className="mt-5 grid gap-3 lg:grid-cols-3">
        {stages.map((stage, index) => {
          const Icon = stage.icon;

          return (
            <li key={stage.title} className={`min-w-0 rounded-2xl border p-4 ${stage.className}`}>
              <div className="flex items-start justify-between gap-3">
                <Icon className="size-5 shrink-0" aria-hidden="true" />
                <span className="rounded-full border border-current/15 bg-black/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]">
                  {stage.status}
                </span>
              </div>
              <p className="mt-4 font-semibold text-slate-100">
                <span className="mr-2 font-mono text-xs opacity-55">0{index + 1}</span>
                {stage.title}
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-400">{stage.description}</p>
            </li>
          );
        })}
      </ol>

      <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-slate-500">
        <CircleDashed className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        Ten widok nie przedstawia wyniku RULA, REBA ani końcowego poziomu ryzyka.
      </p>
    </section>
  );
}
