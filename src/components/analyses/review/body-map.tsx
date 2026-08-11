"use client";

import type { ReviewMetricName } from "@/lib/analysis-review/schemas";

const AREAS: Array<{ id: string; label: string; metric: ReviewMetricName }> = [
  { id: "neck", label: "Szyja", metric: "neck_flexion_deg" },
  { id: "trunk", label: "Tułów", metric: "trunk_inclination_deg" },
  { id: "left_arm", label: "Lewe ramię", metric: "left_upper_arm_elevation_deg" },
  { id: "right_arm", label: "Prawe ramię", metric: "right_upper_arm_elevation_deg" },
  { id: "left_elbow", label: "Lewy łokieć", metric: "left_elbow_flexion_deg" },
  { id: "right_elbow", label: "Prawy łokieć", metric: "right_elbow_flexion_deg" },
  { id: "left_wrist", label: "Lewy nadgarstek", metric: "left_wrist_flexion_deg" },
  { id: "right_wrist", label: "Prawy nadgarstek", metric: "right_wrist_flexion_deg" },
];

export function BodyMap({ selected, onSelect }: { selected: ReviewMetricName; onSelect: (metric: ReviewMetricName) => void }) {
  const activeArea = AREAS.find((area) => area.metric === selected)?.id;
  return (
    <section className="review-panel min-w-0" aria-labelledby="body-map-title">
      <p className="review-eyebrow">Wybór obszaru</p>
      <h2 id="body-map-title" className="mt-2 text-xl font-semibold">Mapa ciała</h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">Wybierz obszar, aby przejść do powiązanej metryki.</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-[9rem_1fr] lg:grid-cols-1 xl:grid-cols-[9rem_1fr]">
        <svg viewBox="0 0 160 330" className="mx-auto h-72 max-w-full" role="img" aria-label="Schemat sylwetki z aktywnym obszarem">
          <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="80" cy="30" rx="24" ry="27" className="text-slate-600" strokeWidth="8" />
            <path d="M80 58v20M51 84c17-10 41-10 58 0l-7 93c-14 8-30 8-44 0z" className={activeArea === "trunk" ? "text-primary" : "text-slate-600"} strokeWidth="12" />
            <path d="M80 58v22" className={activeArea === "neck" ? "text-primary" : "text-slate-600"} strokeWidth="12" />
            <path d="M52 90L25 146 18 214" className={activeArea === "left_arm" || activeArea === "left_elbow" || activeArea === "left_wrist" ? "text-primary" : "text-slate-600"} strokeWidth="12" />
            <path d="M108 90l27 56 7 68" className={activeArea === "right_arm" || activeArea === "right_elbow" || activeArea === "right_wrist" ? "text-primary" : "text-slate-600"} strokeWidth="12" />
            <path d="M62 179l-8 70-6 66M98 179l8 70 6 66" className="text-slate-700" strokeWidth="14" />
          </g>
          {AREAS.map((area) => {
            const coordinates: Record<string, [number, number]> = { neck: [80, 67], trunk: [80, 125], left_arm: [38, 115], right_arm: [122, 115], left_elbow: [25, 146], right_elbow: [135, 146], left_wrist: [18, 214], right_wrist: [142, 214] };
            const [cx, cy] = coordinates[area.id] ?? [80, 125];
            return <circle key={area.id} cx={cx} cy={cy} r="7" className={activeArea === area.id ? "fill-primary stroke-orange-200" : "fill-slate-800 stroke-slate-500"} strokeWidth="3" />;
          })}
        </svg>
        <div className="grid content-start grid-cols-2 gap-2 sm:grid-cols-1 lg:grid-cols-2 xl:grid-cols-1">
          {AREAS.map((area) => (
            <button key={area.id} type="button" aria-pressed={selected === area.metric} onClick={() => onSelect(area.metric)} className={`min-w-0 rounded-lg border px-3 py-2.5 text-left text-xs font-semibold transition ${selected === area.metric ? "border-primary/40 bg-brand-soft text-accent-foreground" : "border-border bg-surface-muted text-muted-foreground hover:text-foreground"}`}>{area.label}</button>
          ))}
        </div>
      </div>
    </section>
  );
}
