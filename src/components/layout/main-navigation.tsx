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
      <nav className="hidden items-center gap-7 text-sm text-muted-foreground md:flex" aria-label="Główna nawigacja">
        {links.map((link) => (
          <Link key={link.href} href={link.href} className="transition hover:text-foreground">
            {link.label}
          </Link>
        ))}
        <AccountLink href={accountHref} label={accountLabel} icon={AccountIcon} emphasized={isAuthenticated} />
      </nav>

      <button
        type="button"
        className="ui-icon-button md:hidden"
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
          className="absolute inset-x-0 top-[calc(100%+0.6rem)] grid gap-1 rounded-xl border border-border bg-popover p-3 shadow-lg backdrop-blur-xl md:hidden"
        >
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="flex min-h-11 items-center rounded-lg px-4 text-sm font-semibold text-foreground transition hover:bg-secondary"
            >
              {link.label}
            </Link>
          ))}
          <Link
            href={accountHref}
            onClick={() => setOpen(false)}
            className="mt-1 flex min-h-11 items-center justify-between rounded-lg bg-brand-soft px-4 text-sm font-semibold text-accent-foreground transition hover:bg-primary/15"
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
      className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition ${
        emphasized
          ? "border-primary/30 bg-brand-soft text-accent-foreground hover:bg-primary/15"
          : "border-border bg-surface text-foreground hover:bg-secondary"
      }`}
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
      <ArrowUpRight className="size-4" aria-hidden="true" />
    </Link>
  );
}
