import type { ObjectDimensionKey, SceneObjectMeasurement, SceneObjectType } from "../../types/photo-scene";

export type DimensionDefinition = { key: ObjectDimensionKey; label: string; priority: "CRITICAL" | "RECOMMENDED" | "OPTIONAL" };

const common: DimensionDefinition[] = [
  { key: "heightCm", label: "Wysokość", priority: "RECOMMENDED" },
  { key: "widthCm", label: "Szerokość", priority: "RECOMMENDED" },
  { key: "depthCm", label: "Głębokość", priority: "OPTIONAL" },
];

export const OBJECT_DIMENSIONS: Record<SceneObjectType, DimensionDefinition[]> = {
  TABLE: [{ key: "workSurfaceHeightCm", label: "Wysokość blatu", priority: "CRITICAL" }, { key: "widthCm", label: "Szerokość", priority: "RECOMMENDED" }, { key: "depthCm", label: "Głębokość", priority: "RECOMMENDED" }],
  WORK_SURFACE: [{ key: "workSurfaceHeightCm", label: "Wysokość powierzchni roboczej", priority: "CRITICAL" }, { key: "workingWidthCm", label: "Szerokość robocza", priority: "RECOMMENDED" }, { key: "depthCm", label: "Głębokość", priority: "RECOMMENDED" }],
  RACK: [...common, { key: "keyShelfHeightCm", label: "Wysokość kluczowej półki", priority: "CRITICAL" }],
  SHELF: [{ key: "keyShelfHeightCm", label: "Wysokość półki", priority: "CRITICAL" }, { key: "widthCm", label: "Szerokość", priority: "RECOMMENDED" }, { key: "depthCm", label: "Głębokość", priority: "OPTIONAL" }],
  CHAIR: [{ key: "seatHeightCm", label: "Wysokość siedziska", priority: "CRITICAL" }, { key: "backrestHeightCm", label: "Wysokość oparcia", priority: "RECOMMENDED" }, { key: "seatDepthCm", label: "Głębokość siedziska", priority: "RECOMMENDED" }],
  STOOL: [{ key: "seatHeightCm", label: "Wysokość siedziska", priority: "CRITICAL" }, { key: "seatDepthCm", label: "Głębokość siedziska", priority: "OPTIONAL" }],
  MONITOR: [{ key: "screenCenterHeightCm", label: "Wysokość środka ekranu", priority: "CRITICAL" }, { key: "widthCm", label: "Szerokość", priority: "OPTIONAL" }, { key: "userDistanceCm", label: "Odległość od użytkownika", priority: "RECOMMENDED" }],
  MACHINE: common, CONTROL_PANEL: [{ key: "screenCenterHeightCm", label: "Wysokość środka panelu", priority: "CRITICAL" }, ...common.slice(1)],
  CONTAINER: common, CONVEYOR: [{ key: "workSurfaceHeightCm", label: "Wysokość transportowa", priority: "CRITICAL" }, ...common.slice(1)],
  PALLET: common, WORK_ZONE: [{ key: "workingWidthCm", label: "Szerokość robocza", priority: "CRITICAL" }, { key: "depthCm", label: "Głębokość strefy", priority: "RECOMMENDED" }],
  HANDLE: [{ key: "heightCm", label: "Wysokość uchwytu", priority: "CRITICAL" }], OTHER: common,
};

export function dimensionsFor(type: SceneObjectType) { return OBJECT_DIMENSIONS[type]; }

export function objectCompleteness(type: SceneObjectType, measurements: SceneObjectMeasurement) {
  const definitions = dimensionsFor(type).filter((item) => item.priority !== "OPTIONAL");
  const complete = definitions.filter((item) => measurements[item.key] !== null).length;
  return { complete, total: definitions.length, ratio: definitions.length ? complete / definitions.length : 1 };
}
