import { ScanLine } from "lucide-react";

const fallbackLandmarks = [
  "left-[91px] top-[48px]",
  "left-[58px] top-[79px]",
  "right-[58px] top-[79px]",
  "left-[38px] top-[160px]",
  "right-[38px] top-[160px]",
  "left-[67px] top-[213px]",
  "right-[67px] top-[213px]",
  "left-[67px] top-[299px]",
  "right-[67px] top-[299px]",
] as const;

export function ModelFallback({
  label = "Ładowanie wizualizacji",
}: {
  label?: string;
}) {
  return (
    <div
      className="relative flex h-[420px] w-full items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_50%_42%,rgba(8,145,178,0.13),transparent_58%)] sm:h-[540px]"
      role="img"
      aria-label="Uproszczony techniczny manekin z punktami analizy pozy"
    >
      <div className="absolute inset-x-[18%] bottom-8 h-px bg-gradient-to-r from-transparent via-cyan-300/30 to-transparent sm:bottom-12" />
      <div className="absolute bottom-7 h-14 w-44 rounded-[50%] border border-cyan-300/15 bg-cyan-400/[0.025] [transform:rotateX(68deg)] sm:bottom-10" />

      <div className="relative h-[370px] w-[190px] scale-[0.9] opacity-90 sm:scale-100">
        <span className="absolute left-1/2 top-0 h-[54px] w-[42px] -translate-x-1/2 rounded-[46%_46%_42%_42%] border border-cyan-200/40 bg-gradient-to-b from-slate-800 to-cyan-950 shadow-[0_0_24px_rgba(34,211,238,0.13)]" />
        <span className="absolute left-1/2 top-[51px] h-[28px] w-[19px] -translate-x-1/2 rounded-[7px_7px_5px_5px] border-x border-cyan-200/30 bg-cyan-950/90" />

        <span className="absolute left-1/2 top-[72px] h-[94px] w-[82px] -translate-x-1/2 border border-cyan-200/35 bg-gradient-to-b from-cyan-900/75 to-cyan-950/85 [clip-path:polygon(11%_0,89%_0,78%_100%,22%_100%)]" />
        <span className="absolute left-1/2 top-[157px] h-[58px] w-[52px] -translate-x-1/2 border-x border-cyan-200/25 bg-gradient-to-b from-cyan-950/85 to-slate-900 [clip-path:polygon(12%_0,88%_0,82%_100%,18%_100%)]" />
        <span className="absolute left-1/2 top-[205px] h-[52px] w-[70px] -translate-x-1/2 rounded-[45%_45%_32%_32%] border border-cyan-200/30 bg-slate-900" />

        <span className="absolute left-[39px] top-[77px] h-[91px] w-[21px] origin-top rotate-[9deg] rounded-[45%_45%_35%_35%] border border-cyan-200/30 bg-gradient-to-b from-cyan-900/70 to-cyan-950/85" />
        <span className="absolute right-[39px] top-[77px] h-[91px] w-[21px] origin-top -rotate-[9deg] rounded-[45%_45%_35%_35%] border border-cyan-200/30 bg-gradient-to-b from-cyan-900/70 to-cyan-950/85" />
        <span className="absolute left-[30px] top-[160px] h-[82px] w-[17px] origin-top -rotate-[6deg] rounded-[42%_42%_35%_35%] border border-cyan-200/28 bg-cyan-950/85" />
        <span className="absolute right-[30px] top-[160px] h-[82px] w-[17px] origin-top rotate-[6deg] rounded-[42%_42%_35%_35%] border border-cyan-200/28 bg-cyan-950/85" />
        <span className="absolute left-[25px] top-[235px] h-[31px] w-[18px] -rotate-[4deg] rounded-[45%_45%_38%_38%] border border-cyan-200/25 bg-slate-900" />
        <span className="absolute right-[25px] top-[235px] h-[31px] w-[18px] rotate-[4deg] rounded-[45%_45%_38%_38%] border border-cyan-200/25 bg-slate-900" />

        <span className="absolute left-[61px] top-[244px] h-[91px] w-[26px] origin-top rotate-[2deg] rounded-[38%_38%_32%_32%] border border-cyan-200/28 bg-gradient-to-b from-cyan-950/90 to-slate-900" />
        <span className="absolute right-[61px] top-[244px] h-[91px] w-[26px] origin-top -rotate-[2deg] rounded-[38%_38%_32%_32%] border border-cyan-200/28 bg-gradient-to-b from-cyan-950/90 to-slate-900" />
        <span className="absolute left-[64px] top-[326px] h-[38px] w-[20px] rounded-[38%_38%_30%_30%] border border-cyan-200/25 bg-slate-900" />
        <span className="absolute right-[64px] top-[326px] h-[38px] w-[20px] rounded-[38%_38%_30%_30%] border border-cyan-200/25 bg-slate-900" />
        <span className="absolute left-[59px] top-[357px] h-[12px] w-[34px] rounded-[45%_70%_55%_35%] border border-cyan-200/28 bg-cyan-950" />
        <span className="absolute right-[59px] top-[357px] h-[12px] w-[34px] rounded-[70%_45%_35%_55%] border border-cyan-200/28 bg-cyan-950" />

        <span className="absolute left-1/2 top-[13px] h-[29px] w-px -translate-x-1/2 bg-cyan-200/45" />
        <span className="absolute left-[54px] top-[79px] h-px w-[82px] bg-cyan-200/35" />
        <span className="absolute left-1/2 top-[76px] h-[181px] w-px -translate-x-1/2 border-l border-dashed border-emerald-300/30" />

        {fallbackLandmarks.map((position) => (
          <span
            key={position}
            className={`absolute size-1.5 rounded-full bg-cyan-100 shadow-[0_0_8px_rgba(103,232,249,0.75)] ${position}`}
          />
        ))}
      </div>

      <div className="absolute right-4 top-4 flex items-center gap-2 rounded-full border border-cyan-300/15 bg-slate-950/70 px-3 py-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-cyan-200 backdrop-blur sm:right-5 sm:top-5 sm:text-[10px]">
        <ScanLine
          className="size-3.5 motion-safe:animate-pulse"
          aria-hidden="true"
        />
        {label}
      </div>
    </div>
  );
}
