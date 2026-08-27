"use client";

import { toggleWorkstation } from "@/app/panel/actions";

export function WorkstationStatusAction({ id, active }: { id: string; active: boolean }) {
  return <form action={toggleWorkstation} onSubmit={(event) => {
    if (active && !window.confirm("Dezaktywować to stanowisko pracy? Istniejące analizy pozostaną zachowane.")) event.preventDefault();
  }}>
    <input type="hidden" name="id" value={id} />
    <input type="hidden" name="active" value={String(active)} />
    <button className={active ? "ui-button-danger min-h-9 px-3 py-1 text-xs" : "ui-button-secondary min-h-9 px-3 py-1 text-xs"}>{active ? "Dezaktywuj" : "Aktywuj"}</button>
  </form>;
}
