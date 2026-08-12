export function AuthorModelFallback({
  label = "Stylizowane popiersie autora — widok uproszczony",
}: {
  label?: string;
}) {
  return (
    <div className="relative flex h-[390px] w-full items-center justify-center overflow-hidden sm:h-[500px] lg:h-[560px]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_34%,rgba(249,115,22,0.10),transparent_48%)]" />
      <svg viewBox="0 0 480 560" role="img" aria-label={label} className="relative h-[92%] w-auto max-w-full">
        <defs>
          <linearGradient id="authorClay" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#304854" />
            <stop offset="0.55" stopColor="#172a34" />
            <stop offset="1" stopColor="#0a1720" />
          </linearGradient>
          <linearGradient id="authorRim" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#a7f3d0" stopOpacity="0.75" />
            <stop offset="1" stopColor="#22d3ee" stopOpacity="0.25" />
          </linearGradient>
        </defs>
        <path d="M154 210c-9-31-12-72-4-107 11-47 43-75 89-75 48 0 81 30 91 79 7 36 3 77-8 106-13 34-45 64-82 64-39 0-74-31-86-67Z" fill="url(#authorClay)" stroke="url(#authorRim)" strokeWidth="2" />
        <path d="M181 259v54c-71 14-123 61-144 143h406c-21-82-73-129-145-143v-58c-15 14-35 22-58 22-24 0-44-7-59-18Z" fill="url(#authorClay)" stroke="#22d3ee" strokeOpacity="0.42" strokeWidth="2" />
        <path d="M178 112c38-37 91-44 130-16M186 213c33 22 70 22 105 0M146 367c61 29 126 29 188 0" fill="none" stroke="#d5fffa" strokeOpacity="0.14" strokeWidth="2" />
        <path d="M98 456h284" stroke="#22d3ee" strokeOpacity="0.35" strokeWidth="3" />
        <g fill="#6ee7d1">
          <circle cx="151" cy="339" r="4" />
          <circle cx="329" cy="339" r="4" />
          <circle cx="240" cy="456" r="4" />
        </g>
      </svg>
      <span className="absolute bottom-5 rounded-full border border-primary/20 bg-card/90 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
        Widok uproszczony
      </span>
    </div>
  );
}
