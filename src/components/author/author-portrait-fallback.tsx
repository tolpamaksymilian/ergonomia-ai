export function AuthorPortraitFallback({ label = "Techniczny awatar autora" }: { label?: string }) {
  return (
    <div className="relative flex h-[360px] w-full items-center justify-center overflow-hidden rounded-[28px] bg-[radial-gradient(circle_at_50%_35%,rgba(34,211,238,0.14),transparent_48%)] sm:h-[460px]">
      <svg
        viewBox="0 0 360 420"
        role="img"
        aria-label={label}
        className="h-[88%] w-auto max-w-full"
      >
        <defs>
          <linearGradient id="bustFill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#173743" />
            <stop offset="1" stopColor="#081923" />
          </linearGradient>
          <linearGradient id="bustLine" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#6ee7d1" />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <path d="M126 179c-8-25-10-59-2-88 8-31 29-51 57-51 29 0 51 22 57 55 6 31 1 65-10 88-9 19-28 34-48 34-21 0-45-17-54-38Z" fill="url(#bustFill)" stroke="url(#bustLine)" strokeWidth="2" />
        <path d="M151 207v39c-42 11-73 40-86 91h231c-13-51-44-80-87-91v-42" fill="url(#bustFill)" stroke="#22d3ee" strokeOpacity=".65" strokeWidth="2" />
        <path d="M142 109c23-20 54-28 85-17M139 137h85M153 170c18 9 36 9 54 0M180 47v166" fill="none" stroke="#67e8f9" strokeOpacity=".35" strokeWidth="1.5" />
        <g fill="#a7f3d0">
          <circle cx="142" cy="137" r="4" /><circle cx="218" cy="137" r="4" />
          <circle cx="180" cy="93" r="4" /><circle cx="180" cy="170" r="4" />
          <circle cx="151" cy="247" r="4" /><circle cx="209" cy="247" r="4" />
        </g>
        <path d="M55 337h250" stroke="#22d3ee" strokeOpacity=".25" />
      </svg>
      <span className="absolute bottom-5 rounded-full border border-cyan-300/15 bg-slate-950/70 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-200/70">
        Wizualizacja uproszczona
      </span>
    </div>
  );
}
