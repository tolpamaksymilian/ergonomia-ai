"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { normalizeTheme, oppositeTheme, persistTheme, type AppTheme } from "@/lib/theme";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<AppTheme>("light");
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) setTheme(normalizeTheme(document.documentElement.dataset.theme));
    });
    return () => { active = false; };
  }, []);
  function toggle() {
    const next = oppositeTheme(theme);
    document.documentElement.classList.toggle("dark", next === "dark");
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next;
    persistTheme(localStorage, next);
    setTheme(next);
  }
  const dark = theme === "dark";
  const label = dark ? "Włącz jasny motyw" : "Włącz ciemny motyw";
  return <button type="button" onClick={toggle} aria-label={label} title={label} className={`ui-icon-button ${className}`} suppressHydrationWarning>{dark ? <Sun className="size-4" aria-hidden="true" /> : <Moon className="size-4" aria-hidden="true" />}</button>;
}
