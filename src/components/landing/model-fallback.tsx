import { ScanLine } from "lucide-react";

export function ModelFallback({
  label = "Ładowanie wizualizacji",
}: {
  label?: string;
}) {
  return (
    <div
      className="relative flex h-[430px] w-full items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_50%_40%,rgba(8,145,178,0.16),transparent_58%)] sm:h-[540px]"
      role="img"
      aria-label="Uproszczony podgląd sylwetki z punktami analizy pozy"
    >
      <div className="absolute inset-x-[12%] bottom-12 h-px bg-gradient-to-r from-transparent via-cyan-300/35 to-transparent" />
      <div className="absolute bottom-10 h-20 w-56 rounded-[50%] border border-cyan-300/15 bg-cyan-400/[0.04] [transform:rotateX(68deg)]" />

      <div className="relative h-[330px] w-48 opacity-90 sm:h-[390px]">
        <span className="absolute left-1/2 top-2 size-14 -translate-x-1/2 rounded-[48%] border border-cyan-200/45 bg-cyan-300/10 shadow-[0_0_30px_rgba(34,211,238,0.16)]" />
        <span className="absolute left-1/2 top-[64px] h-32 w-[86px] -translate-x-1/2 rounded-[42%_42%_36%_36%] border border-cyan-200/35 bg-gradient-to-b from-cyan-300/15 to-emerald-400/10" />
        <span className="absolute left-[38px] top-[79px] h-32 w-7 origin-top -rotate-[17deg] rounded-full border border-cyan-200/30 bg-cyan-300/10" />
        <span className="absolute right-[37px] top-[78px] h-32 w-7 origin-top rotate-[23deg] rounded-full border border-cyan-200/30 bg-cyan-300/10" />
        <span className="absolute left-[61px] top-[180px] h-40 w-8 origin-top rotate-[4deg] rounded-full border border-cyan-200/30 bg-cyan-300/10" />
        <span className="absolute right-[60px] top-[180px] h-40 w-8 origin-top -rotate-[5deg] rounded-full border border-cyan-200/30 bg-cyan-300/10" />

        {["left-[91px] top-[59px]", "left-[50px] top-[83px]", "right-[48px] top-[83px]", "left-[35px] top-[173px]", "right-[31px] top-[171px]", "left-[63px] top-[181px]", "right-[62px] top-[181px]", "left-[58px] bottom-[31px]", "right-[57px] bottom-[31px]"].map((position) => (
          <span
            key={position}
            className={`absolute size-2 rounded-full bg-cyan-200 shadow-[0_0_12px_rgba(103,232,249,0.9)] ${position}`}
          />
        ))}
      </div>

      <div className="absolute left-5 top-5 flex items-center gap-2 rounded-full border border-cyan-300/15 bg-slate-950/65 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-200 backdrop-blur">
        <ScanLine className="size-3.5 motion-safe:animate-pulse" aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}
