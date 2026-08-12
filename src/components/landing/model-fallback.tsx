import { ScanLine } from "lucide-react";

const landmarks = [[100, 67], [75, 92], [125, 92], [58, 160], [142, 160], [78, 228], [122, 228], [78, 326], [122, 326]] as const;

export function ModelFallback({ label = "Ładowanie wizualizacji" }: { label?: string }) {
  return (
    <div className="relative flex h-[420px] w-full items-center justify-center overflow-hidden bg-[#f7f7f7] dark:bg-[#111111] sm:h-[540px]" role="img" aria-label="Uproszczony techniczny manekin z punktami analizy pozy">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(115,115,115,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(115,115,115,.08)_1px,transparent_1px)] bg-[size:44px_44px]" />
      <svg viewBox="0 0 200 390" className="relative h-[88%] max-w-[46%]" aria-hidden="true">
        <g fill="#303030" stroke="#171717" strokeWidth="2" strokeLinejoin="round">
          <ellipse cx="100" cy="40" rx="23" ry="30" />
          <path d="M90 69h20l4 22H86z" />
          <path d="M70 88q30-18 60 0l-9 91q-21 13-42 0z" />
          <path d="M79 174h42l7 49q-28 18-56 0z" />
          <path d="M72 95 52 163l-8 65 14 2 12-61 18-68zM128 95l20 68 8 65-14 2-12-61-18-68z" />
          <path d="M78 219 67 320h18l15-92 15 92h18l-11-101z" />
          <path d="M65 317h23l4 45H59zM112 317h23l6 45h-33z" />
          <path d="M57 357h37l-3 14H50zM106 357h37l7 14h-41z" />
        </g>
        <path d="M100 82v145" stroke="#f97316" strokeWidth="3" strokeDasharray="7 7" opacity=".8" />
        <path d="M70 92h60" stroke="#a3a3a3" strokeWidth="2" />
        {landmarks.map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="4.5" fill="#f97316" stroke="#fff7ed" strokeWidth="2" />)}
      </svg>
      <div className="absolute bottom-8 h-12 w-44 rounded-[50%] border border-orange-300/40 bg-orange-50/60 [transform:rotateX(68deg)] dark:border-orange-500/25 dark:bg-orange-950/15" />
      <div className="absolute right-4 top-4 flex items-center gap-2 rounded-full border border-border bg-surface/90 px-3 py-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-muted-foreground backdrop-blur sm:right-5 sm:top-5 sm:text-[10px]">
        <ScanLine className="size-3.5 text-primary motion-safe:animate-pulse" aria-hidden="true" />{label}
      </div>
    </div>
  );
}
