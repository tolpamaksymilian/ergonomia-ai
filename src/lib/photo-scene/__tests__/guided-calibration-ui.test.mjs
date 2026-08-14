import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const guided = readFileSync(new URL("../../../components/photo-scene/guided-calibration.tsx", import.meta.url), "utf8");
const editor = readFileSync(new URL("../../../components/photo-scene/photo-scene-editor.tsx", import.meta.url), "utf8");

test("guided calibration exposes floor, top, value and save steps", () => {
  for (const phrase of [
    "Kliknij punkt na podłodze bezpośrednio pod wybranym elementem",
    "Kliknij górny punkt tej samej pionowej wysokości",
    "Rzeczywista wartość [cm]",
    "Zapisz referencję",
  ]) assert.match(guided, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("measurement wizard contains semantic choices and calibration opt-in", () => {
  for (const phrase of ["Wysokość od podłogi", "Szerokość", "Głębokość", "Odległość po podłodze", "Użyj do kalibracji"]) assert.ok(guided.includes(phrase));
  assert.ok(guided.includes("disabled={semantics.axis !== \"VERTICAL\"}"));
});

test("help diagrams explain height width depth and an invalid example", () => {
  for (const phrase of ["Jak prawidłowo oznaczyć wymiar?", "Punkt na podłodze", "ta sama krawędź", "silnie zniekształcona", "Niepoprawnie"]) assert.ok(guided.includes(phrase));
});

test("editor exposes semantic review, floor modes, onboarding and missing-scale action", () => {
  for (const phrase of ["SEMANTICS_REVIEW_REQUIRED", "Podstawowa · 2 punkty", "Dokładniejsza · 4 punkty", "Jak przygotować scenę?", "Dodaj pionową referencję tutaj"]) assert.ok(editor.includes(phrase));
});

test("precise mobile calibration recommends a larger screen", () => {
  assert.ok(editor.includes("Precyzyjną kalibrację najwygodniej wykonać na większym ekranie"));
});
