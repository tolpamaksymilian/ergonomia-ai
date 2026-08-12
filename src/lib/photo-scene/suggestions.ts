import type { ObjectDimensionKey, SceneState, TechnicalInsight } from "../../types/photo-scene";
import { calibrationQuality } from "./calibration.ts";
import { dimensionsFor } from "./object-dimensions.ts";

export type DimensionSuggestion = {
  id: string; objectId: string; objectName: string; key: ObjectDimensionKey; label: string;
  priority: "CRITICAL" | "RECOMMENDED" | "OPTIONAL"; message: string;
};

export function missingDimensionSuggestions(state: SceneState): DimensionSuggestion[] {
  return state.objects.filter((object) => object.status !== "USER_REJECTED" && object.visible).flatMap((object) =>
    dimensionsFor(object.type).filter((definition) => object.measurements[definition.key] === null).map((definition) => ({
      id: `${object.id}:${definition.key}`, objectId: object.id, objectName: object.name, key: definition.key,
      label: definition.label, priority: definition.priority,
      message: `Wykryto „${object.name}” — uzupełnij: ${definition.label.toLowerCase()}.`,
    })),
  ).sort((a, b) => priorityOrder(a.priority) - priorityOrder(b.priority));
}

export function sceneCompleteness(state: SceneState) {
  const suggestions = missingDimensionSuggestions(state);
  const required = suggestions.filter((item) => item.priority !== "OPTIONAL");
  const total = state.objects.filter((object) => object.status !== "USER_REJECTED").reduce((sum, object) => sum + dimensionsFor(object.type).filter((item) => item.priority !== "OPTIONAL").length, 0);
  const completed = Math.max(0, total - required.length);
  return { completed, total, ratio: total ? completed / total : 0, missingCritical: suggestions.filter((item) => item.priority === "CRITICAL").length };
}

export function buildTechnicalInsights(state: SceneState): TechnicalInsight[] {
  const insights: TechnicalInsight[] = [];
  if (calibrationQuality(state.calibration) !== "GOOD") insights.push({ id: "calibration", severity: "INFO", code: "INSUFFICIENT_CALIBRATION", message: "Brak wystarczających danych do wiarygodnego osadzenia skali. Dodaj 2–3 referencje w różnych obszarach.", objectId: null, humanId: null });
  for (const suggestion of missingDimensionSuggestions(state).filter((item) => item.priority === "CRITICAL")) insights.push({ id: suggestion.id, severity: "INFO", code: "MISSING_OBJECT_DIMENSION", message: suggestion.message, objectId: suggestion.objectId, humanId: null });
  for (const human of state.humans) {
    for (const [side, reach] of [["lewej", human.pose.reachState.leftArm], ["prawej", human.pose.reachState.rightArm]] as const) {
      if (reach === "OUT_OF_REACH") insights.push({ id: `${human.id}-${side}-max`, severity: "ATTENTION", code: "NATURAL_REACH_EXCEEDED", message: `${human.name}: cel ${side} ręki jest poza naturalnym zasięgiem.`, objectId: null, humanId: human.id });
      else if (reach === "COMFORT_EXCEEDED") insights.push({ id: `${human.id}-${side}-comfort`, severity: "INFO", code: "COMFORT_REACH_EXCEEDED", message: `${human.name}: pozycja ${side} ręki przekracza zasięg komfortowy.`, objectId: null, humanId: human.id });
    }
  }
  return insights;
}

function priorityOrder(priority: DimensionSuggestion["priority"]) { return priority === "CRITICAL" ? 0 : priority === "RECOMMENDED" ? 1 : 2; }
