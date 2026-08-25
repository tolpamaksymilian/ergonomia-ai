"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";

export function DashboardError({ reset }: { reset: () => void }) {
  return <section className="dashboard-card mx-auto max-w-xl p-8 text-center" role="alert">
    <span className="mx-auto grid size-12 place-items-center rounded-xl bg-red-500/10 text-red-600"><AlertTriangle className="size-6" /></span>
    <h1 className="mt-4 text-xl font-bold">Nie udało się załadować widoku</h1>
    <p className="dashboard-muted mt-2">Spróbuj ponownie. Jeśli problem się powtarza, sprawdź połączenie z bazą i wdrożone migracje.</p>
    <button type="button" onClick={reset} className="ui-button-primary mt-6"><RotateCcw className="size-4" />Spróbuj ponownie</button>
  </section>;
}
