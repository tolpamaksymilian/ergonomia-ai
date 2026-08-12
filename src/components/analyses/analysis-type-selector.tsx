"use client";

import { useState } from "react";
import { ArrowLeft, Film, ImagePlus, ScanSearch, ShieldCheck } from "lucide-react";

import { NewAnalysisForm } from "./new-analysis-form";
import { PhotoSceneCreateForm } from "./photo-scene-create-form";

type Option = { id: string; name: string; code: string | null };
type Category = { id: string; name: string; group_name: string };

export function AnalysisTypeSelector({ userId, workstations, categories }: { userId: string; workstations: Option[]; categories: Category[] }) {
  const [mode, setMode] = useState<"VIDEO" | "PHOTO_SCENE" | null>(null);

  if (mode) {
    return <div className="space-y-5">
      <button type="button" onClick={() => setMode(null)} className="ui-button-secondary text-sm">
        <ArrowLeft className="size-4" /> Zmień typ analizy
      </button>
      {mode === "VIDEO"
        ? <NewAnalysisForm userId={userId} />
        : <PhotoSceneCreateForm userId={userId} workstations={workstations} categories={categories} />}
    </div>;
  }

  return <section aria-labelledby="analysis-type-title">
    <div className="mb-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Pierwszy krok</p>
      <h2 id="analysis-type-title" className="mt-2 text-2xl font-bold">Co chcesz przeanalizować?</h2>
      <p className="mt-2 text-muted-foreground">Wybierz świadomie jedną z dwóch niezależnych ścieżek.</p>
    </div>
    <div className="grid gap-5 lg:grid-cols-2">
      <article className="ui-card flex min-h-[360px] flex-col p-7">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Film className="size-6" /></span>
        <h3 className="mt-6 text-2xl font-bold">Analiza ruchu z filmu</h3>
        <p className="mt-3 leading-7 text-muted-foreground">Automatyczna analiza postawy i ruchu pracownika na podstawie nagrania.</p>
        <ul className="mt-5 grid grid-cols-2 gap-2 text-sm text-muted-foreground">
          {["Pose", "Metryki", "Risk Engine", "RULA i REBA", "OWAS", "Raport"].map((item) => <li key={item} className="flex items-center gap-2"><ShieldCheck className="size-4 text-green-600" />{item}</li>)}
        </ul>
        <button type="button" onClick={() => setMode("VIDEO")} className="ui-button-primary mt-auto justify-center">Rozpocznij analizę filmu</button>
      </article>

      <article className="ui-card flex min-h-[360px] flex-col border-primary/30 p-7">
        <div className="flex items-center justify-between gap-3">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><ImagePlus className="size-6" /></span>
          <span className="rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-bold text-primary">BETA</span>
        </div>
        <h3 className="mt-6 text-2xl font-bold">Projekt stanowiska ze zdjęcia</h3>
        <p className="mt-3 leading-7 text-muted-foreground">Zbuduj interaktywny model stanowiska na podstawie zdjęcia i dopasuj do niego model człowieka.</p>
        <ul className="mt-5 space-y-2 text-sm text-muted-foreground">
          {["Prywatne zdjęcie stanowiska", "Wykrycie i ręczna korekta elementów", "Kalibracja wymiarów", "Edytowalny model człowieka", "Zapis sceny bez oceny ergonomicznej"].map((item) => <li key={item} className="flex items-center gap-2"><ScanSearch className="size-4 text-primary" />{item}</li>)}
        </ul>
        <button type="button" onClick={() => setMode("PHOTO_SCENE")} className="ui-button-primary mt-auto justify-center">Utwórz projekt stanowiska</button>
      </article>
    </div>
  </section>;
}
