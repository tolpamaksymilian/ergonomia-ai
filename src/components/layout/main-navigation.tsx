"use client";

import Link from "next/link";
import { ArrowUpRight, LogIn, Menu, ShieldCheck, UserRound, X } from "lucide-react";
import { useState } from "react";

const links = [
  { href: "/", label: "Strona główna" },
  { href: "/o-projekcie", label: "O projekcie" },
  { href: "/o-autorze", label: "O autorze" },
] as const;

type MainNavigationProps = {
  isAuthenticated: boolean;
  isAdmin: boolean;
};

export function MainNavigation({ isAuthenticated, isAdmin }: MainNavigationProps) {
  const [open, setOpen] = useState(false);
  const accountHref = isAuthenticated ? (isAdmin ? "/admin" : "/panel") : "/logowanie";
  const accountLabel = isAuthenticated ? (isAdmin ? "Panel admina" : "Mój panel") : "Zaloguj się";
  const AccountIcon = isAuthenticated ? (isAdmin ? ShieldCheck : UserRound) : LogIn;

  return (
    <>
      <nav className="hidden items-center gap-7 text-sm text-slate-300 md:flex" aria-label="Główna nawigacja">
        {links.map((link) => (
          <Link key={link.href} href={link.href} className="transition hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-300">
            {link.label}
          </Link>
        ))}
        <AccountLink href={accountHref} label={accountLabel} icon={AccountIcon} emphasized={isAuthenticated} />
      </nav>

      <button
        type="button"
        className="flex size-11 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-white transition hover:bg-white/[0.08] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 md:hidden"
        aria-expanded={open}
        aria-controls="mobile-main-navigation"
        aria-label={open ? "Zamknij menu" : "Otwórz menu"}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <X className="size-5" aria-hidden="true" /> : <Menu className="size-5" aria-hidden="true" />}
      </button>

      {open && (
        <nav
          id="mobile-main-navigation"
          aria-label="Główna nawigacja mobilna"
          className="absolute inset-x-0 top-[calc(100%+0.6rem)] grid gap-1 rounded-2xl border border-white/10 bg-slate-950/95 p-3 shadow-2xl shadow-black/40 backdrop-blur-xl md:hidden"
        >
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="flex min-h-11 items-center rounded-xl px-4 text-sm font-semibold text-slate-200 transition hover:bg-white/[0.07] focus-visible:outline-2 focus-visible:outline-cyan-300"
            >
              {link.label}
            </Link>
          ))}
          <Link
            href={accountHref}
            onClick={() => setOpen(false)}
            className="mt-1 flex min-h-11 items-center justify-between rounded-xl bg-emerald-400/10 px-4 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-400/15 focus-visible:outline-2 focus-visible:outline-cyan-300"
          >
            <span className="flex items-center gap-2">
              <AccountIcon className="size-4" aria-hidden="true" />
              {accountLabel}
            </span>
            <ArrowUpRight className="size-4" aria-hidden="true" />
          </Link>
        </nav>
      )}
    </>
  );
}

function AccountLink({
  href,
  label,
  icon: Icon,
  emphasized,
}: {
  href: string;
  label: string;
  icon: typeof LogIn;
  emphasized: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 ${
        emphasized
          ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200 hover:bg-emerald-400/15"
          : "border-white/10 bg-white/[0.04] text-white hover:bg-white/[0.08]"
      }`}
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
      <ArrowUpRight className="size-4" aria-hidden="true" />
    </Link>
  );
}
