import Link from "next/link";

import { release } from "@/config/release";

export function SiteFooter() {
  return (
    <footer className="border-t border-white/10 bg-slate-950/70 px-5 py-6 text-slate-500 sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs">
        <p>
          Ergonomia AI · v{release.version} · {release.statusLabel}. Wyniki wymagają oceny specjalisty.
        </p>
        <nav className="flex gap-4" aria-label="Informacje o projekcie">
          <Link href="/o-projekcie" className="transition hover:text-slate-300">O projekcie</Link>
          <Link href="/o-autorze" className="transition hover:text-slate-300">O autorze</Link>
        </nav>
      </div>
    </footer>
  );
}
