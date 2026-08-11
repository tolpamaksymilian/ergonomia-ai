import Link from "next/link";

import { release } from "@/config/release";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface px-5 py-6 text-muted-foreground sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs">
        <p>
          Ergonomia AI · v{release.version} · {release.statusLabel}. Wyniki wymagają oceny specjalisty.
        </p>
        <nav className="flex gap-4" aria-label="Informacje o projekcie">
          <Link href="/o-projekcie" className="transition hover:text-foreground">O projekcie</Link>
          <Link href="/o-autorze" className="transition hover:text-foreground">O autorze</Link>
        </nav>
      </div>
    </footer>
  );
}
