import type { SceneState } from "../../types/photo-scene";

const objectTypes = new Set([
  "WORK_SURFACE", "TABLE", "SHELF", "RACK", "CHAIR", "STOOL", "CONVEYOR",
  "MACHINE", "CONTROL_PANEL", "MONITOR", "CONTAINER", "PALLET", "OTHER",
]);

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function normalizedPoint(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const point = value as Record<string, unknown>;
  return finite(point.x) && finite(point.y) && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1;
}

function normalizedBox(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const box = value as Record<string, unknown>;
  return finite(box.x) && finite(box.y) && finite(box.width) && finite(box.height)
    && box.x >= 0 && box.y >= 0 && box.width > 0 && box.height > 0
    && box.x + box.width <= 1.000001 && box.y + box.height <= 1.000001;
}

export function validateSceneState(value: unknown): value is SceneState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const state = value as Record<string, unknown>;
  if (state.schema_version !== "1.0" || !Array.isArray(state.objects)) return false;
  if (state.objects.length > 250) return false;
  for (const raw of state.objects) {
    if (!raw || typeof raw !== "object") return false;
    const object = raw as Record<string, unknown>;
    if (typeof object.id !== "string" || object.id.length > 100) return false;
    if (typeof object.name !== "string" || object.name.trim().length < 1 || object.name.length > 120) return false;
    if (!objectTypes.has(String(object.type)) || !normalizedBox(object.bbox)) return false;
  }
  const calibration = state.calibration as Record<string, unknown> | null;
  if (!calibration || !["UNCALIBRATED", "PARTIALLY_CALIBRATED", "CALIBRATED_2D"].includes(String(calibration.status))) return false;
  if (!Array.isArray(calibration.anchors) || calibration.anchors.length > 50) return false;
  for (const raw of calibration.anchors) {
    if (!raw || typeof raw !== "object") return false;
    const anchor = raw as Record<string, unknown>;
    if (!normalizedPoint(anchor.lower) || !normalizedPoint(anchor.upper)) return false;
    if (!finite(anchor.realDistanceCm) || anchor.realDistanceCm <= 0) return false;
  }
  if (state.human !== null && state.human !== undefined) {
    const human = state.human as Record<string, unknown>;
    for (const field of ["heightCm", "armSpanCm", "functionalReachCm"]) {
      if (!finite(human[field]) || (human[field] as number) <= 0) return false;
    }
  }
  return true;
}

export function emptySceneState(): SceneState {
  return {
    schema_version: "1.0",
    objects: [],
    calibration: { status: "UNCALIBRATED", floorBaseline: null, anchors: [] },
    human: null,
    pose: null,
    viewport: { zoom: 1, pan_x: 0, pan_y: 0 },
    selectedObjectId: null,
    reachVisible: true,
  };
}
