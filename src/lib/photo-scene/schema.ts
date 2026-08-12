import type {
  CalibrationReference, HumanPose, SceneHuman, SceneObject, SceneObjectMeasurement,
  SceneState, SceneStateV10,
} from "../../types/photo-scene";
import { createHuman, defaultPose } from "./anthropometry.ts";
import { buildTechnicalInsights } from "./suggestions.ts";

const objectTypes = new Set([
  "WORK_SURFACE", "TABLE", "SHELF", "RACK", "CHAIR", "STOOL", "CONVEYOR",
  "MACHINE", "CONTROL_PANEL", "MONITOR", "CONTAINER", "PALLET", "WORK_ZONE", "HANDLE", "OTHER",
]);

const dimensionKeys: (keyof SceneObjectMeasurement)[] = [
  "heightCm", "widthCm", "depthCm", "workSurfaceHeightCm", "lowerEdgeHeightCm",
  "upperEdgeHeightCm", "seatHeightCm", "backrestHeightCm", "seatDepthCm",
  "screenCenterHeightCm", "userDistanceCm", "keyShelfHeightCm", "workingWidthCm",
];

export function emptyMeasurements(): SceneObjectMeasurement {
  return Object.fromEntries(dimensionKeys.map((key) => [key, null])) as SceneObjectMeasurement;
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function point(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return finite(candidate.x) && finite(candidate.y) && candidate.x >= 0 && candidate.x <= 1 && candidate.y >= 0 && candidate.y <= 1;
}

function box(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return finite(candidate.x) && finite(candidate.y) && finite(candidate.width) && finite(candidate.height)
    && candidate.x >= 0 && candidate.y >= 0 && candidate.width > 0 && candidate.height > 0
    && candidate.x + candidate.width <= 1.000001 && candidate.y + candidate.height <= 1.000001;
}

function validReference(value: unknown): value is CalibrationReference {
  if (!value || typeof value !== "object") return false;
  const reference = value as Record<string, unknown>;
  return typeof reference.id === "string" && typeof reference.name === "string"
    && point(reference.start) && point(reference.end)
    && finite(reference.valueCm) && reference.valueCm > 0
    && finite(reference.pixelDistance) && reference.pixelDistance > 0
    && reference.unit === "cm";
}

function validPose(value: unknown): value is HumanPose {
  if (!value || typeof value !== "object") return false;
  const pose = value as Record<string, unknown>;
  if (!pose.joints || typeof pose.joints !== "object") return false;
  return Object.values(pose.joints as Record<string, unknown>).every(point);
}

export function validateSceneState(value: unknown): value is SceneState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const state = value as Record<string, unknown>;
  if (state.schema_version !== "1.1" || !Array.isArray(state.objects) || !Array.isArray(state.humans)) return false;
  if (state.objects.length > 250 || state.humans.length > 12) return false;
  for (const raw of state.objects) {
    if (!raw || typeof raw !== "object") return false;
    const object = raw as Record<string, unknown>;
    if (typeof object.id !== "string" || typeof object.name !== "string" || !object.name.trim()) return false;
    if (!objectTypes.has(String(object.type)) || !box(object.bbox)) return false;
  }
  const calibration = state.calibration as Record<string, unknown> | null;
  if (!calibration || !Array.isArray(calibration.references) || calibration.references.length > 100) return false;
  if (!calibration.references.every(validReference)) return false;
  for (const raw of state.humans) {
    if (!raw || typeof raw !== "object") return false;
    const human = raw as Record<string, unknown>;
    const profile = human.profile as Record<string, unknown> | null;
    if (typeof human.id !== "string" || !profile || !validPose(human.pose)) return false;
    for (const field of ["heightCm", "armSpanCm", "functionalReachCm", "maximumReachCm"]) {
      if (!finite(profile[field]) || (profile[field] as number) <= 0) return false;
    }
  }
  return true;
}

export function normalizeSceneState(value: unknown): SceneState {
  if (validateSceneState(value)) return refreshInsights(value);
  if (!value || typeof value !== "object" || (value as { schema_version?: unknown }).schema_version !== "1.0") return emptySceneState();
  const old = value as SceneStateV10;
  const references: CalibrationReference[] = (old.calibration?.anchors ?? []).filter((anchor) => anchor.realDistanceCm > 0 && anchor.pixelDistance > 0).map((anchor, index) => ({
    id: anchor.id, name: `Referencja ${index + 1}`, dimensionType: "HEIGHT", valueCm: anchor.realDistanceCm,
    unit: "cm", start: anchor.lower, end: anchor.upper, pixelDistance: anchor.pixelDistance,
    objectId: anchor.objectId, active: true, visible: true, locked: false, affectsScale: true,
    source: "USER_PROVIDED",
  }));
  const objects: SceneObject[] = (old.objects ?? []).map((object) => ({
    ...object, locked: object.locked ?? false, measurements: { ...emptyMeasurements(), ...object.measurements },
  }));
  let humans: SceneHuman[] = [];
  if (old.human) {
    const human = createHuman("Operator", "#f97316", "CUSTOM");
    human.id = "legacy-human-1";
    human.profile = {
      ...human.profile, ...old.human, preset: "CUSTOM", maximumReachCm: Math.max(old.human.functionalReachCm, old.human.heightCm * 0.47),
      upperArmLengthCm: old.human.upperLimbLengthCm ? old.human.upperLimbLengthCm * 0.52 : null,
      thighLengthCm: old.human.lowerLimbLengthCm ? old.human.lowerLimbLengthCm * 0.52 : null,
      lowerLegLengthCm: old.human.lowerLimbLengthCm ? old.human.lowerLimbLengthCm * 0.48 : null,
      geometrySource: old.human.geometrySource === "USER_MEASUREMENTS" ? "USER_MEASUREMENTS" : "ANTHROPOMETRIC_ESTIMATE",
    };
    human.pose = old.pose ? { ...defaultPose(old.pose.preset), ...old.pose, reachState: defaultPose(old.pose.preset).reachState } : defaultPose("STANDING");
    humans = [human];
  }
  return refreshInsights({
    schema_version: "1.1", objects,
    calibration: { status: old.calibration?.status ?? "UNCALIBRATED", floorBaseline: old.calibration?.floorBaseline ?? null, horizonY: null, references },
    humans, viewport: old.viewport ?? { zoom: 1, pan_x: 0, pan_y: 0 },
    selectedObjectId: old.selectedObjectId ?? null, selectedHumanId: humans[0]?.id ?? null,
    selectedReferenceId: null, reachVisible: old.reachVisible ?? true, measurementFilter: "ALL", technicalInsights: [],
  });
}

export function refreshInsights(state: SceneState): SceneState {
  return { ...state, technicalInsights: buildTechnicalInsights(state) };
}

export function emptySceneState(): SceneState {
  return {
    schema_version: "1.1", objects: [],
    calibration: { status: "UNCALIBRATED", floorBaseline: null, horizonY: null, references: [] },
    humans: [], viewport: { zoom: 1, pan_x: 0, pan_y: 0 }, selectedObjectId: null,
    selectedHumanId: null, selectedReferenceId: null, reachVisible: true,
    measurementFilter: "ALL", technicalInsights: [],
  };
}
