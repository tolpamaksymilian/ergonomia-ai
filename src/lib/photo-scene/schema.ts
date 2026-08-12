import type {
  CalibrationReference, GeometryMeasurement, HumanPose, ObjectDimensionKey, SceneHuman,
  SceneObject, SceneObjectMeasurement, SceneState, WorkerDimensionSuggestion,
} from "../../types/photo-scene";
import { createConstraintGraph, createHuman, profileFromHeight, syncPlacement } from "./anthropometry.ts";
import { emptyScaleField, rebuildPerspectiveField } from "./calibration.ts";
import { buildTechnicalInsights } from "./suggestions.ts";

const objectTypes = new Set(["WORK_SURFACE", "TABLE", "SHELF", "RACK", "CHAIR", "STOOL", "CONVEYOR", "MACHINE", "CONTROL_PANEL", "MONITOR", "CONTAINER", "PALLET", "WORK_ZONE", "HANDLE", "OTHER"]);
const dimensionKeys: ObjectDimensionKey[] = ["heightCm", "widthCm", "depthCm", "workSurfaceHeightCm", "lowerEdgeHeightCm", "upperEdgeHeightCm", "seatHeightCm", "seatWidthCm", "backrestHeightCm", "seatDepthCm", "screenCenterHeightCm", "screenHeightCm", "userDistanceCm", "keyShelfHeightCm", "workingWidthCm", "controlHeightCm"];

export function emptyMeasurements(): SceneObjectMeasurement { return Object.fromEntries(dimensionKeys.map((key) => [key, null])) as SceneObjectMeasurement; }
function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function point(value: unknown): boolean { if (!value || typeof value !== "object") return false; const candidate = value as Record<string, unknown>; return finite(candidate.x) && finite(candidate.y) && candidate.x >= -.000001 && candidate.x <= 1.000001 && candidate.y >= -.000001 && candidate.y <= 1.000001; }
function box(value: unknown): boolean { if (!value || typeof value !== "object") return false; const candidate = value as Record<string, unknown>; return finite(candidate.x) && finite(candidate.y) && finite(candidate.width) && finite(candidate.height) && candidate.x >= 0 && candidate.y >= 0 && candidate.width > 0 && candidate.height > 0 && (candidate.x as number) + (candidate.width as number) <= 1.000001 && (candidate.y as number) + (candidate.height as number) <= 1.000001; }
function validReference(value: unknown): value is CalibrationReference { if (!value || typeof value !== "object") return false; const reference = value as Record<string, unknown>; return typeof reference.id === "string" && typeof reference.name === "string" && point(reference.start) && point(reference.end) && finite(reference.valueCm) && reference.valueCm > 0 && finite(reference.pixelDistance) && reference.pixelDistance > 0 && reference.unit === "cm"; }
function validGeometryMeasurement(value: unknown): value is GeometryMeasurement { if (!value || typeof value !== "object") return false; const measurement = value as Record<string, unknown>; return typeof measurement.id === "string" && typeof measurement.name === "string" && point(measurement.start) && point(measurement.end) && (measurement.valueCm === null || finite(measurement.valueCm)); }
function validPose(value: unknown): value is HumanPose { if (!value || typeof value !== "object") return false; const pose = value as Record<string, unknown>; if (!pose.joints || typeof pose.joints !== "object") return false; return Object.values(pose.joints as Record<string, unknown>).every(point); }

export function validateSceneState(value: unknown): value is SceneState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const state = value as Record<string, unknown>;
  if (state.schema_version !== "1.2" || !Array.isArray(state.objects) || !Array.isArray(state.humans) || !Array.isArray(state.geometryMeasurements) || !Array.isArray(state.workerSuggestions)) return false;
  if (state.objects.length > 250 || state.humans.length > 12 || state.geometryMeasurements.length > 300 || state.workerSuggestions.length > 300) return false;
  for (const raw of state.objects) { if (!raw || typeof raw !== "object") return false; const object = raw as Record<string, unknown>; if (typeof object.id !== "string" || typeof object.name !== "string" || !object.name.trim() || !objectTypes.has(String(object.type)) || !box(object.bbox) || !Array.isArray(object.geometryMeasurements) || !Array.isArray(object.interactionPoints)) return false; }
  const calibration = state.calibration as Record<string, unknown> | null;
  if (!calibration || !Array.isArray(calibration.references) || calibration.references.length > 100 || !calibration.references.every(validReference)) return false;
  if (!state.geometryMeasurements.every(validGeometryMeasurement)) return false;
  for (const raw of state.humans) { if (!raw || typeof raw !== "object") return false; const human = raw as Record<string, unknown>, profile = human.profile as Record<string, unknown> | null; if (typeof human.id !== "string" || !profile || !validPose(human.pose) || !human.constraints || typeof human.constraints !== "object") return false; for (const field of ["heightCm", "armSpanCm", "functionalReachCm", "maximumReachCm"]) if (!finite(profile[field]) || (profile[field] as number) <= 0) return false; }
  return true;
}

export function normalizeSceneState(value: unknown): SceneState {
  if (validateSceneState(value)) return refreshDerivedState(value);
  if (!value || typeof value !== "object") return emptySceneState();
  const raw = value as Record<string, unknown>, version = String(raw.schema_version ?? "");
  if (version !== "1.0" && version !== "1.1") return emptySceneState();
  const objects = Array.isArray(raw.objects) ? raw.objects.map(normalizeObject).filter((object): object is SceneObject => object !== null) : [];
  const calibrationRaw = raw.calibration && typeof raw.calibration === "object" ? raw.calibration as Record<string, unknown> : {};
  const references = version === "1.0" ? normalizeAnchors(calibrationRaw.anchors) : normalizeReferences(calibrationRaw.references);
  const humans = version === "1.0" ? normalizeLegacyHuman(raw.human, raw.pose) : Array.isArray(raw.humans) ? raw.humans.map(normalizeHuman).filter((human): human is SceneHuman => human !== null) : [];
  const oldViewport = raw.viewport && typeof raw.viewport === "object" ? raw.viewport as Record<string, unknown> : {};
  return refreshDerivedState({
    ...emptySceneState(), objects, humans,
    calibration: {
      status: String(calibrationRaw.status) === "CALIBRATED_2D" ? "CALIBRATED_2D" : references.length ? "PARTIALLY_CALIBRATED" : "UNCALIBRATED",
      floorBaseline: normalizeFloor(calibrationRaw.floorBaseline), horizonY: finite(calibrationRaw.horizonY) ? calibrationRaw.horizonY : null,
      verticalDirection: point(calibrationRaw.verticalDirection) ? calibrationRaw.verticalDirection as { x: number; y: number } : null,
      references, scaleField: emptyScaleField(),
    },
    viewport: { zoom: finite(oldViewport.zoom) ? oldViewport.zoom : 1, pan_x: finite(oldViewport.pan_x) ? oldViewport.pan_x : 0, pan_y: finite(oldViewport.pan_y) ? oldViewport.pan_y : 0 },
    selectedObjectId: typeof raw.selectedObjectId === "string" ? raw.selectedObjectId : null,
    selectedHumanId: typeof raw.selectedHumanId === "string" ? raw.selectedHumanId : humans[0]?.id ?? null,
    selectedReferenceId: typeof raw.selectedReferenceId === "string" ? raw.selectedReferenceId : null,
    reachVisible: raw.reachVisible !== false,
  });
}

export function refreshDerivedState(state: SceneState): SceneState {
  const calibration = rebuildPerspectiveField(state.calibration);
  const withCalibration = { ...state, calibration };
  return { ...withCalibration, technicalInsights: buildTechnicalInsights(withCalibration) };
}
export const refreshInsights = refreshDerivedState;

export function emptySceneState(): SceneState {
  return {
    schema_version: "1.2", objects: [], calibration: { status: "UNCALIBRATED", floorBaseline: null, horizonY: null, verticalDirection: null, references: [], scaleField: emptyScaleField() },
    humans: [], geometryMeasurements: [], workerSuggestions: [], viewport: { zoom: 1, pan_x: 0, pan_y: 0 },
    selectedObjectId: null, selectedHumanId: null, selectedReferenceId: null, reachVisible: true,
    measurementFilter: "SELECTED_OBJECT",
    view: { layers: { CALIBRATION: true, OBJECT_DIMENSIONS: true, USER_MEASUREMENTS: true, HUMAN_REACH: false, SUGGESTIONS: false, DEBUG: false }, preset: "CLEAN", focusMode: true, reachMode: "FUNCTIONAL" },
    autoSuggestDimensions: true, technicalInsights: [],
  };
}

export function workerSuggestionToMeasurement(suggestion: WorkerDimensionSuggestion, name: string): GeometryMeasurement {
  return { id: crypto.randomUUID(), objectId: suggestion.object_id, dimensionKey: suggestion.dimension_type, name, valueCm: suggestion.estimated_value_cm, unit: "cm", start: suggestion.endpoints.start, end: suggestion.endpoints.end, orientation: suggestion.dimension_type === "depthCm" ? "DEPTH" : suggestion.dimension_type.toLowerCase().includes("height") ? "VERTICAL" : "HORIZONTAL", source: suggestion.estimated_value_cm === null ? "WORKER_SUGGESTED" : "SCENE_ESTIMATED", estimateStatus: suggestion.estimated_value_cm === null ? "SUGGESTED" : "ESTIMATED", evidenceQuality: suggestion.evidence_quality, reason: suggestion.reason, active: true, visible: true, locked: false, affectsScale: suggestion.dimension_type !== "depthCm" && suggestion.estimated_value_cm !== null };
}

function normalizeObject(value: unknown): SceneObject | null {
  if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; if (typeof raw.id !== "string" || typeof raw.name !== "string" || !box(raw.bbox) || !objectTypes.has(String(raw.type))) return null;
  return { id: raw.id, sourceClass: typeof raw.sourceClass === "string" ? raw.sourceClass : null, type: raw.type as SceneObject["type"], name: raw.name, bbox: raw.bbox as SceneObject["bbox"], detectorConfidence: finite(raw.detectorConfidence) ? raw.detectorConfidence : null, source: raw.source === "YOLOX_X_COCO" ? "YOLOX_X_COCO" : "USER", status: (["DETECTED", "USER_CONFIRMED", "USER_MODIFIED", "USER_ADDED", "USER_REJECTED"].includes(String(raw.status)) ? raw.status : "USER_ADDED") as SceneObject["status"], visible: raw.visible !== false, locked: raw.locked === true, measurements: { ...emptyMeasurements(), ...(raw.measurements && typeof raw.measurements === "object" ? raw.measurements : {}) }, geometryMeasurements: Array.isArray(raw.geometryMeasurements) ? raw.geometryMeasurements.filter(validGeometryMeasurement) : [], interactionPoints: Array.isArray(raw.interactionPoints) ? raw.interactionPoints.filter((item) => item && typeof item === "object" && point((item as Record<string, unknown>).position)) as SceneObject["interactionPoints"] : [], referencePoint: raw.referencePoint && typeof raw.referencePoint === "object" ? raw.referencePoint as SceneObject["referencePoint"] : null };
}

function normalizeHuman(value: unknown): SceneHuman | null {
  if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>, profileRaw = raw.profile && typeof raw.profile === "object" ? raw.profile as Record<string, unknown> : null; if (!profileRaw || !finite(profileRaw.heightCm)) return null;
  const base = createHuman(typeof raw.name === "string" ? raw.name : "Operator", typeof raw.color === "string" ? raw.color : "#f97316", "CUSTOM");
  const derived = profileFromHeight(base.name, profileRaw.heightCm, "CUSTOM");
  const profile = { ...derived, ...profileRaw, segmentProvenance: { ...derived.segmentProvenance, ...(profileRaw.segmentProvenance && typeof profileRaw.segmentProvenance === "object" ? profileRaw.segmentProvenance : {}) } } as SceneHuman["profile"];
  const pose = normalizePose(raw.pose, base.pose), placementRaw = raw.placement && typeof raw.placement === "object" ? raw.placement as Record<string, unknown> : {};
  const placement = syncPlacement(pose, { ...base.placement, attachedObjectId: typeof placementRaw.attachedObjectId === "string" ? placementRaw.attachedObjectId : null, floorPinned: placementRaw.floorPinned === true, positionMode: placementRaw.attachmentMode === "SEATED_AT_OBJECT" ? "SEATED_AT_OBJECT" : placementRaw.attachmentMode === "WORK_SURFACE" ? "WORKING_AT_OBJECT" : "FREE", orientationDeg: finite(placementRaw.orientationDeg) ? placementRaw.orientationDeg : 0, facingPreset: "FRONT", lastScalePxPerCm: finite(placementRaw.lastScalePxPerCm) ? placementRaw.lastScalePxPerCm : null, scaleStatus: "NO_SCALE" });
  return { ...base, id: typeof raw.id === "string" ? raw.id : base.id, profile, constraints: createConstraintGraph(profile), pose, placement, handTargets: { left: null, right: null }, visible: raw.visible !== false, locked: raw.locked === true };
}

function normalizeLegacyHuman(humanValue: unknown, poseValue: unknown): SceneHuman[] {
  if (!humanValue || typeof humanValue !== "object") return []; const raw = humanValue as Record<string, unknown>; if (!finite(raw.heightCm)) return [];
  const human = createHuman("Operator", "#f97316", "CUSTOM"), derived = profileFromHeight("Operator", raw.heightCm, "CUSTOM");
  human.id = "legacy-human-1"; human.profile = { ...derived, ...raw, segmentProvenance: derived.segmentProvenance } as SceneHuman["profile"]; human.constraints = createConstraintGraph(human.profile); human.pose = normalizePose(poseValue, human.pose); human.placement = syncPlacement(human.pose, human.placement); return [human];
}

function normalizePose(value: unknown, fallback: HumanPose): HumanPose {
  if (!value || typeof value !== "object") return fallback; const raw = value as Record<string, unknown>, rawJoints = raw.joints && typeof raw.joints === "object" ? raw.joints as Record<string, unknown> : {};
  const joints = { ...fallback.joints }; for (const [name, value] of Object.entries(rawJoints)) if (point(value) && name in joints) joints[name as keyof typeof joints] = value as { x: number; y: number };
  if (!("pelvisRoot" in rawJoints)) joints.pelvisRoot = { x: (joints.leftHip.x + joints.rightHip.x) / 2, y: (joints.leftHip.y + joints.rightHip.y) / 2 };
  return { ...fallback, preset: typeof raw.preset === "string" ? raw.preset as HumanPose["preset"] : fallback.preset, mirrored: raw.mirrored === true, scaleLocked: raw.scaleLocked !== false, joints };
}

function normalizeAnchors(value: unknown): CalibrationReference[] { if (!Array.isArray(value)) return []; return value.flatMap((item, index) => { if (!item || typeof item !== "object") return []; const raw = item as Record<string, unknown>; if (!point(raw.lower) || !point(raw.upper) || !finite(raw.realDistanceCm) || !finite(raw.pixelDistance) || raw.realDistanceCm <= 0) return []; return [{ id: typeof raw.id === "string" ? raw.id : `legacy-${index}`, name: `Referencja ${index + 1}`, dimensionType: "HEIGHT" as const, valueCm: raw.realDistanceCm, unit: "cm" as const, start: raw.lower as { x: number; y: number }, end: raw.upper as { x: number; y: number }, pixelDistance: raw.pixelDistance, objectId: typeof raw.objectId === "string" ? raw.objectId : null, active: true, visible: true, locked: false, affectsScale: true, source: "USER_PROVIDED" as const, residual: null, residualStatus: "UNASSESSED" as const, manualOverride: false }]; }); }
function normalizeReferences(value: unknown): CalibrationReference[] { if (!Array.isArray(value)) return []; return value.filter(validReference).map((reference) => ({ ...reference, residual: finite((reference as unknown as Record<string, unknown>).residual) ? (reference as unknown as { residual: number }).residual : null, residualStatus: (["GOOD", "WEAK", "OUTLIER"].includes(String((reference as unknown as Record<string, unknown>).residualStatus)) ? (reference as unknown as CalibrationReference).residualStatus : "UNASSESSED"), manualOverride: (reference as unknown as Record<string, unknown>).manualOverride === true })); }
function normalizeFloor(value: unknown): SceneState["calibration"]["floorBaseline"] { if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; return point(raw.start) && point(raw.end) ? { start: raw.start as NormalizedPoint, end: raw.end as NormalizedPoint } : null; }
type NormalizedPoint = { x: number; y: number };
