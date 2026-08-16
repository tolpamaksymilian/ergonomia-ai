import type {
  CalibrationReference, GeometryMeasurement, HumanPose, NormalizedPoint, ObjectDimensionKey,
  ReferenceDimensionType, SceneGeometryConstraint, SceneHuman, SceneObject, SceneObjectMeasurement, SceneRegion, SceneState,
  WorkerDimensionSuggestion,
} from "../../types/photo-scene";
import { createConstraintGraph, createHuman, profileFromHeight, syncPlacement } from "./anthropometry.ts";
import { normalizePhysicalProfile } from "./human-physical-model.ts";
import { emptyScaleField, rebuildPerspectiveField } from "./calibration.ts";
import { buildTechnicalInsights } from "./suggestions.ts";
import { semanticsForDimensionKey, semanticsForReferenceType } from "./measurement-semantics.ts";
import { createHuman3DState } from "./human-3d-model.ts";
import { geometry3dFromSceneObject } from "./object-3d-model.ts";
import { createEmptyConstraintGraph, emptyReconstructionState, regionPoint } from "./scene-reconstruction.ts";

const objectTypes = new Set(["WORK_SURFACE", "TABLE", "SHELF", "RACK", "CHAIR", "STOOL", "CONVEYOR", "MACHINE", "CONTROL_PANEL", "MONITOR", "CONTAINER", "PALLET", "WORK_ZONE", "HANDLE", "OTHER"]);
const dimensionKeys: ObjectDimensionKey[] = ["heightCm", "widthCm", "depthCm", "workSurfaceHeightCm", "lowerEdgeHeightCm", "upperEdgeHeightCm", "seatHeightCm", "seatWidthCm", "backrestHeightCm", "seatDepthCm", "screenCenterHeightCm", "screenHeightCm", "userDistanceCm", "keyShelfHeightCm", "workingWidthCm", "controlHeightCm"];
const measurementKinds = new Set(["VERTICAL_HEIGHT", "HORIZONTAL_WIDTH", "DEPTH", "FLOOR_DISTANCE", "OBJECT_HEIGHT", "OBJECT_WIDTH", "OBJECT_DEPTH", "WORK_SURFACE_HEIGHT", "SHELF_HEIGHT", "SEAT_HEIGHT", "SCREEN_HEIGHT", "CUSTOM_DISTANCE"]);
const measurementAxes = new Set(["VERTICAL", "HORIZONTAL", "GROUND_X", "GROUND_Y", "ARBITRARY"]);
const measurementPlanes = new Set(["VERTICAL_PLANE", "GROUND_PLANE", "OBJECT_FRONT_PLANE", "OBJECT_TOP_PLANE", "UNKNOWN_PLANE"]);
const measurementPurposes = new Set(["CALIBRATION", "OBJECT_DESCRIPTION", "HUMAN_SCALE_VALIDATION", "INFORMATION_ONLY"]);

export function emptyMeasurements(): SceneObjectMeasurement { return Object.fromEntries(dimensionKeys.map((key) => [key, null])) as SceneObjectMeasurement; }
function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function point(value: unknown): boolean { if (!value || typeof value !== "object") return false; const candidate = value as Record<string, unknown>; return finite(candidate.x) && finite(candidate.y) && candidate.x >= -.000001 && candidate.x <= 1.000001 && candidate.y >= -.000001 && candidate.y <= 1.000001; }
function box(value: unknown): boolean { if (!value || typeof value !== "object") return false; const candidate = value as Record<string, unknown>; return finite(candidate.x) && finite(candidate.y) && finite(candidate.width) && finite(candidate.height) && candidate.x >= 0 && candidate.y >= 0 && candidate.width > 0 && candidate.height > 0 && (candidate.x as number) + (candidate.width as number) <= 1.000001 && (candidate.y as number) + (candidate.height as number) <= 1.000001; }
function validReference(value: unknown): value is CalibrationReference { if (!basicReference(value)) return false; const reference = value as Record<string, unknown>; return measurementKinds.has(String(reference.measurementKind)) && measurementAxes.has(String(reference.axis)) && measurementPlanes.has(String(reference.plane)) && measurementPurposes.has(String(reference.purpose)) && typeof reference.useForCalibration === "boolean" && ["CONFIRMED", "SEMANTICS_REVIEW_REQUIRED"].includes(String(reference.semanticStatus)) && validWorldAnchors(reference.worldAnchors); }
function validGeometryMeasurement(value: unknown): value is GeometryMeasurement { if (!value || typeof value !== "object") return false; const measurement = value as Record<string, unknown>; return typeof measurement.id === "string" && typeof measurement.name === "string" && point(measurement.start) && point(measurement.end) && (measurement.valueCm === null || finite(measurement.valueCm)) && measurementKinds.has(String(measurement.measurementKind)) && measurementAxes.has(String(measurement.axis)) && measurementPlanes.has(String(measurement.plane)) && measurementPurposes.has(String(measurement.purpose)) && typeof measurement.useForCalibration === "boolean" && ["CONFIRMED", "SEMANTICS_REVIEW_REQUIRED"].includes(String(measurement.semanticStatus)); }
function validPose(value: unknown): value is HumanPose { if (!value || typeof value !== "object") return false; const pose = value as Record<string, unknown>; if (!pose.joints || typeof pose.joints !== "object") return false; return Object.values(pose.joints as Record<string, unknown>).every(point); }

export function validateSceneState(value: unknown): value is SceneState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const state = value as Record<string, unknown>;
  if (state.schema_version !== "1.5" || !Array.isArray(state.objects) || !Array.isArray(state.humans) || !Array.isArray(state.geometryMeasurements) || !Array.isArray(state.workerSuggestions) || !Array.isArray(state.regions) || !Array.isArray(state.planes) || !Array.isArray(state.objectFaces) || !state.constraintGraph || typeof state.constraintGraph !== "object" || !state.reconstructionState || typeof state.reconstructionState !== "object" || !state.scene3d || typeof state.scene3d !== "object") return false;
  if (state.objects.length > 250 || state.humans.length > 12 || state.geometryMeasurements.length > 300 || state.workerSuggestions.length > 300 || state.regions.length > 500 || state.planes.length > 500 || state.objectFaces.length > 500) return false;
  for (const raw of state.objects) { if (!raw || typeof raw !== "object") return false; const object = raw as Record<string, unknown>; if (typeof object.id !== "string" || typeof object.name !== "string" || !object.name.trim() || !objectTypes.has(String(object.type)) || !box(object.bbox) || !Array.isArray(object.geometryMeasurements) || !Array.isArray(object.interactionPoints) || !Array.isArray(object.interactionPoints3d)) return false; }
  const calibration = state.calibration as Record<string, unknown> | null;
  if (!calibration || !Array.isArray(calibration.references) || calibration.references.length > 100 || !calibration.references.every(validReference)) return false;
  if (!state.geometryMeasurements.every(validGeometryMeasurement)) return false;
  if (!state.regions.every(validRegion)) return false;
  const graph = state.constraintGraph as Record<string, unknown>;
  if (graph.version !== "scene-constraint-graph-v1.0" || !Array.isArray(graph.nodes) || !Array.isArray(graph.constraints) || graph.constraints.length > 1000 || !graph.constraints.every(validConstraint)) return false;
  for (const raw of state.humans) { if (!raw || typeof raw !== "object") return false; const human = raw as Record<string, unknown>, profile = human.profile as Record<string, unknown> | null, dimensions = profile?.physicalDimensions as Record<string, unknown> | null, human3d = human.human3d as Record<string, unknown> | null; if (typeof human.id !== "string" || human.modelVersion !== "digital-human-v1" || !profile || !dimensions || !validPose(human.pose) || !human.constraints || typeof human.constraints !== "object" || !human3d || human3d.modelVersion !== "digital-human-3d-v1") return false; for (const field of ["heightCm", "armSpanCm", "functionalReachCm", "maximumReachCm"]) if (!finite(profile[field]) || (profile[field] as number) <= 0) return false; for (const field of ["statureCm", "headHeightCm", "shoulderWidthCm", "pelvisWidthCm", "upperArmLengthCm", "forearmLengthCm", "thighLengthCm", "lowerLegLengthCm"]) if (!finite(dimensions[field]) || (dimensions[field] as number) <= 0) return false; }
  return true;
}

export function normalizeSceneState(value: unknown): SceneState {
  if (validateSceneState(value)) return refreshDerivedState(value);
  if (!value || typeof value !== "object") return emptySceneState();
  const raw = value as Record<string, unknown>, version = String(raw.schema_version ?? "");
  if (!["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"].includes(version)) return emptySceneState();
  const objects = Array.isArray(raw.objects) ? raw.objects.map(normalizeObject).filter((object): object is SceneObject => object !== null) : [];
  const calibrationRaw = raw.calibration && typeof raw.calibration === "object" ? raw.calibration as Record<string, unknown> : {};
  const references = version === "1.0" ? normalizeAnchors(calibrationRaw.anchors) : normalizeReferences(calibrationRaw.references, version !== "1.3" && version !== "1.4");
  const humans = version === "1.0" ? normalizeLegacyHuman(raw.human, raw.pose) : Array.isArray(raw.humans) ? raw.humans.map(normalizeHuman).filter((human): human is SceneHuman => human !== null) : [];
  const oldViewport = raw.viewport && typeof raw.viewport === "object" ? raw.viewport as Record<string, unknown> : {};
  const defaults = emptySceneState();
  return refreshDerivedState({
    ...defaults, objects, humans,
    calibration: {
      status: String(calibrationRaw.status) === "CALIBRATED_2D" ? "CALIBRATED_2D" : references.length ? "PARTIALLY_CALIBRATED" : "UNCALIBRATED",
      floorBaseline: normalizeFloor(calibrationRaw.floorBaseline), horizonY: finite(calibrationRaw.horizonY) ? calibrationRaw.horizonY : null,
      verticalDirection: point(calibrationRaw.verticalDirection) ? calibrationRaw.verticalDirection as { x: number; y: number } : null,
      verticalDirectionSource: ["WORKER_SUGGESTED", "USER_CONFIRMED"].includes(String(calibrationRaw.verticalDirectionSource)) ? calibrationRaw.verticalDirectionSource as SceneState["calibration"]["verticalDirectionSource"] : "DEFAULT_IMAGE_AXIS",
      verticalDirectionConfirmed: calibrationRaw.verticalDirectionConfirmed === true,
      floorPlane: normalizeFloorPlane(calibrationRaw.floorPlane, normalizeFloor(calibrationRaw.floorBaseline)),
      references, scaleField: emptyScaleField(),
    },
    viewport: { zoom: finite(oldViewport.zoom) ? oldViewport.zoom : 1, pan_x: finite(oldViewport.pan_x) ? oldViewport.pan_x : 0, pan_y: finite(oldViewport.pan_y) ? oldViewport.pan_y : 0 },
    selectedObjectId: typeof raw.selectedObjectId === "string" ? raw.selectedObjectId : null,
    selectedHumanId: typeof raw.selectedHumanId === "string" ? raw.selectedHumanId : humans[0]?.id ?? null,
    selectedReferenceId: typeof raw.selectedReferenceId === "string" ? raw.selectedReferenceId : null,
    selectedRegionId: typeof raw.selectedRegionId === "string" ? raw.selectedRegionId : null,
    reachVisible: raw.reachVisible !== false,
    regions: normalizeRegions(raw.regions),
    planes: Array.isArray(raw.planes) ? raw.planes as SceneState["planes"] : [],
    objectFaces: Array.isArray(raw.objectFaces) ? raw.objectFaces as SceneState["objectFaces"] : [],
    constraintGraph: normalizeConstraintGraph(raw.constraintGraph),
    reconstructionState: normalizeReconstructionState(raw.reconstructionState),
    scene3d: normalizeScene3d(raw.scene3d),
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
    schema_version: "1.5", objects: [], calibration: { status: "UNCALIBRATED", floorBaseline: null, horizonY: null, verticalDirection: { x: 0, y: -1 }, verticalDirectionSource: "DEFAULT_IMAGE_AXIS", verticalDirectionConfirmed: false, floorPlane: { mode: "NONE", points: [], actualGroundDimensionCm: null, mappingStatus: "NONE" }, references: [], scaleField: emptyScaleField() },
    regions: [], planes: [], objectFaces: [], constraintGraph: createEmptyConstraintGraph(), reconstructionState: emptyReconstructionState(),
    humans: [], geometryMeasurements: [], workerSuggestions: [], viewport: { zoom: 1, pan_x: 0, pan_y: 0 },
    selectedObjectId: null, selectedHumanId: null, selectedReferenceId: null, selectedRegionId: null, reachVisible: true,
    measurementFilter: "SELECTED_OBJECT",
    view: { layers: { OBJECTS: true, SURFACES: true, SOLVER: false, FLOOR: true, CALIBRATION: false, OBJECT_DIMENSIONS: false, USER_MEASUREMENTS: false, HUMAN_REACH: false, SUGGESTIONS: false, DEBUG: false }, preset: "CLEAN", focusMode: true, reachMode: "FUNCTIONAL" },
    autoSuggestDimensions: true, technicalInsights: [],
    scene3d: { unit: "cm", cameraMappingStatus: "CAMERA_APPROXIMATE", workspaceMode: "PHOTO", snapCm: 5, selectedInteractionPointId: null, collisionBlocking: false, lastReachability: null, lastCollisions: [], motion: null },
  };
}

export function workerSuggestionToMeasurement(suggestion: WorkerDimensionSuggestion, name: string): GeometryMeasurement {
  const semantics = semanticsForDimensionKey(suggestion.dimension_type);
  return { id: crypto.randomUUID(), objectId: suggestion.object_id, dimensionKey: suggestion.dimension_type, name, valueCm: suggestion.estimated_value_cm, unit: "cm", start: suggestion.endpoints.start, end: suggestion.endpoints.end, orientation: suggestion.dimension_type === "depthCm" ? "DEPTH" : suggestion.dimension_type.toLowerCase().includes("height") ? "VERTICAL" : "HORIZONTAL", source: suggestion.estimated_value_cm === null ? "WORKER_SUGGESTED" : "SCENE_ESTIMATED", estimateStatus: suggestion.estimated_value_cm === null ? "SUGGESTED" : "ESTIMATED", evidenceQuality: suggestion.evidence_quality, reason: suggestion.reason, active: true, visible: true, locked: false, ...semantics, useForCalibration: false, semanticStatus: "CONFIRMED" };
}

function normalizeObject(value: unknown): SceneObject | null {
  if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; if (typeof raw.id !== "string" || typeof raw.name !== "string" || !box(raw.bbox) || !objectTypes.has(String(raw.type))) return null;
  const object: SceneObject = { id: raw.id, sourceClass: typeof raw.sourceClass === "string" ? raw.sourceClass : null, type: raw.type as SceneObject["type"], name: raw.name, bbox: raw.bbox as SceneObject["bbox"], detectorConfidence: finite(raw.detectorConfidence) ? raw.detectorConfidence : null, source: raw.source === "YOLOX_X_COCO" ? "YOLOX_X_COCO" as const : "USER" as const, status: (["DETECTED", "USER_CONFIRMED", "USER_MODIFIED", "USER_ADDED", "USER_REJECTED"].includes(String(raw.status)) ? raw.status : "USER_ADDED") as SceneObject["status"], visible: raw.visible !== false, locked: raw.locked === true, measurements: { ...emptyMeasurements(), ...(raw.measurements && typeof raw.measurements === "object" ? raw.measurements : {}) }, geometryMeasurements: Array.isArray(raw.geometryMeasurements) ? raw.geometryMeasurements.map(normalizeGeometryMeasurement).filter((item): item is GeometryMeasurement => item !== null) : [], interactionPoints: Array.isArray(raw.interactionPoints) ? raw.interactionPoints.filter((item) => item && typeof item === "object" && point((item as Record<string, unknown>).position)) as SceneObject["interactionPoints"] : [], referencePoint: raw.referencePoint && typeof raw.referencePoint === "object" ? raw.referencePoint as SceneObject["referencePoint"] : null, geometry3d: null, interactionPoints3d: Array.isArray(raw.interactionPoints3d) ? raw.interactionPoints3d as SceneObject["interactionPoints3d"] : [], regionIds: Array.isArray(raw.regionIds) ? raw.regionIds.filter((item): item is string => typeof item === "string") : [], faceIds: Array.isArray(raw.faceIds) ? raw.faceIds.filter((item): item is string => typeof item === "string") : [], planeIds: Array.isArray(raw.planeIds) ? raw.planeIds.filter((item): item is string => typeof item === "string") : [], shapeAssumptions: Array.isArray(raw.shapeAssumptions) ? raw.shapeAssumptions.filter((item) => ["RECTANGULAR", "PLANAR", "PARALLEL_EDGES", "FREEFORM"].includes(String(item))) as SceneObject["shapeAssumptions"] : (["TABLE", "WORK_SURFACE"].includes(String(raw.type)) ? ["RECTANGULAR", "PLANAR"] : []), reconstructionQuality: (["HIGH", "PARTIAL", "TWO_D_ONLY", "INVALID"].includes(String(raw.reconstructionQuality)) ? raw.reconstructionQuality : "UNSOLVED") as SceneObject["reconstructionQuality"] };
  object.geometry3d = normalizeGeometry3d(raw.geometry3d) ?? geometry3dFromSceneObject(object); return object;
}

function normalizeHuman(value: unknown): SceneHuman | null {
  if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>, profileRaw = raw.profile && typeof raw.profile === "object" ? raw.profile as Record<string, unknown> : null; if (!profileRaw || !finite(profileRaw.heightCm)) return null;
  const base = createHuman(typeof raw.name === "string" ? raw.name : "Operator", typeof raw.color === "string" ? raw.color : "#f97316", "CUSTOM");
  const derived = profileFromHeight(base.name, profileRaw.heightCm, "CUSTOM");
  const profile = normalizePhysicalProfile({ ...derived, ...profileRaw, segmentProvenance: { ...derived.segmentProvenance, ...(profileRaw.segmentProvenance && typeof profileRaw.segmentProvenance === "object" ? profileRaw.segmentProvenance : {}) } } as SceneHuman["profile"]);
  const pose = normalizePose(raw.pose, base.pose), placementRaw = raw.placement && typeof raw.placement === "object" ? raw.placement as Record<string, unknown> : {};
  const placement = syncPlacement(pose, { ...base.placement, attachedObjectId: typeof placementRaw.attachedObjectId === "string" ? placementRaw.attachedObjectId : null, floorPinned: placementRaw.floorPinned === true, positionMode: placementRaw.attachmentMode === "SEATED_AT_OBJECT" ? "SEATED_AT_OBJECT" : placementRaw.attachmentMode === "WORK_SURFACE" ? "WORKING_AT_OBJECT" : "FREE", orientationDeg: finite(placementRaw.orientationDeg) ? placementRaw.orientationDeg : 0, facingPreset: "FRONT", lastScalePxPerCm: finite(placementRaw.lastScalePxPerCm) ? placementRaw.lastScalePxPerCm : null, scaleStatus: "NO_SCALE" });
  const human3d = normalizeHuman3d(raw.human3d, profile) ?? createHuman3DState(profile, "MIGRATED_TO_3D"); if (!raw.human3d) human3d.legacy2dBackup = { posePreset: pose.preset, normalizedRoot: placement.root };
  return { ...base, id: typeof raw.id === "string" ? raw.id : base.id, profile, constraints: createConstraintGraph(profile), pose, placement, human3d, handTargets: { left: null, right: null }, visible: raw.visible !== false, locked: raw.locked === true };
}

function normalizeLegacyHuman(humanValue: unknown, poseValue: unknown): SceneHuman[] {
  if (!humanValue || typeof humanValue !== "object") return []; const raw = humanValue as Record<string, unknown>; if (!finite(raw.heightCm)) return [];
  const human = createHuman("Operator", "#f97316", "CUSTOM"), derived = profileFromHeight("Operator", raw.heightCm, "CUSTOM");
  human.id = "legacy-human-1"; human.profile = { ...derived, ...raw, segmentProvenance: derived.segmentProvenance } as SceneHuman["profile"]; human.constraints = createConstraintGraph(human.profile); human.pose = normalizePose(poseValue, human.pose); human.placement = syncPlacement(human.pose, human.placement); human.human3d = createHuman3DState(human.profile, "MIGRATED_TO_3D"); human.human3d.legacy2dBackup = { posePreset: human.pose.preset, normalizedRoot: human.placement.root }; return [human];
}

function normalizePose(value: unknown, fallback: HumanPose): HumanPose {
  if (!value || typeof value !== "object") return fallback; const raw = value as Record<string, unknown>, rawJoints = raw.joints && typeof raw.joints === "object" ? raw.joints as Record<string, unknown> : {};
  const joints = { ...fallback.joints }; for (const [name, value] of Object.entries(rawJoints)) if (point(value) && name in joints) joints[name as keyof typeof joints] = value as { x: number; y: number };
  if (!("pelvisRoot" in rawJoints)) joints.pelvisRoot = { x: (joints.leftHip.x + joints.rightHip.x) / 2, y: (joints.leftHip.y + joints.rightHip.y) / 2 };
  return { ...fallback, preset: typeof raw.preset === "string" ? raw.preset as HumanPose["preset"] : fallback.preset, mirrored: raw.mirrored === true, scaleLocked: raw.scaleLocked !== false, joints };
}

function normalizeAnchors(value: unknown): CalibrationReference[] { if (!Array.isArray(value)) return []; return value.flatMap((item, index) => { if (!item || typeof item !== "object") return []; const raw = item as Record<string, unknown>; if (!point(raw.lower) || !point(raw.upper) || !finite(raw.realDistanceCm) || !finite(raw.pixelDistance) || raw.realDistanceCm <= 0) return []; const semantics = semanticsForReferenceType("HEIGHT"); return [{ id: typeof raw.id === "string" ? raw.id : `legacy-${index}`, name: `Referencja ${index + 1}`, dimensionType: "HEIGHT" as const, valueCm: raw.realDistanceCm, unit: "cm" as const, start: raw.lower as { x: number; y: number }, end: raw.upper as { x: number; y: number }, pixelDistance: raw.pixelDistance, objectId: typeof raw.objectId === "string" ? raw.objectId : null, active: true, visible: true, locked: false, ...semantics, useForCalibration: false, semanticStatus: "SEMANTICS_REVIEW_REQUIRED" as const, worldAnchors: legacyWorldAnchors(raw.lower as NormalizedPoint, raw.upper as NormalizedPoint, raw.realDistanceCm), source: "USER_PROVIDED" as const, residual: null, residualStatus: "UNASSESSED" as const, manualOverride: false }]; }); }
function normalizeReferences(value: unknown, legacy: boolean): CalibrationReference[] { if (!Array.isArray(value)) return []; return value.flatMap((item) => { if (!basicReference(item)) return []; const raw = item as Record<string, unknown>, dimensionType = raw.dimensionType as ReferenceDimensionType, defaults = semanticsForReferenceType(dimensionType); const rawSemanticsAreValid = measurementKinds.has(String(raw.measurementKind)) && measurementAxes.has(String(raw.axis)) && measurementPlanes.has(String(raw.plane)) && measurementPurposes.has(String(raw.purpose)); const semanticsConfirmed = !legacy && raw.semanticStatus === "CONFIRMED" && rawSemanticsAreValid; return [{ ...(raw as unknown as CalibrationReference), ...defaults, measurementKind: rawSemanticsAreValid ? raw.measurementKind as CalibrationReference["measurementKind"] : defaults.measurementKind, axis: rawSemanticsAreValid ? raw.axis as CalibrationReference["axis"] : defaults.axis, plane: rawSemanticsAreValid ? raw.plane as CalibrationReference["plane"] : defaults.plane, purpose: rawSemanticsAreValid ? raw.purpose as CalibrationReference["purpose"] : defaults.purpose, useForCalibration: semanticsConfirmed && raw.useForCalibration === true, semanticStatus: semanticsConfirmed ? "CONFIRMED" as const : "SEMANTICS_REVIEW_REQUIRED" as const, worldAnchors: normalizeWorldAnchors(raw.worldAnchors) ?? legacyWorldAnchors(raw.start as NormalizedPoint, raw.end as NormalizedPoint, raw.valueCm as number), residual: finite(raw.residual) ? raw.residual : null, residualStatus: (["GOOD", "WEAK", "OUTLIER"].includes(String(raw.residualStatus)) ? raw.residualStatus : "UNASSESSED") as CalibrationReference["residualStatus"], manualOverride: raw.manualOverride === true }]; }); }
function normalizeFloor(value: unknown): SceneState["calibration"]["floorBaseline"] { if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; return point(raw.start) && point(raw.end) ? { start: raw.start as NormalizedPoint, end: raw.end as NormalizedPoint } : null; }
function basicReference(value: unknown) { if (!value || typeof value !== "object") return false; const reference = value as Record<string, unknown>; return typeof reference.id === "string" && typeof reference.name === "string" && point(reference.start) && point(reference.end) && finite(reference.valueCm) && reference.valueCm > 0 && finite(reference.pixelDistance) && reference.pixelDistance > 0 && reference.unit === "cm" && typeof reference.dimensionType === "string"; }
function validWorldAnchors(value: unknown) { if (!value || typeof value !== "object") return false; const raw = value as Record<string, unknown>; return (raw.bottom === null || validWorldAnchor(raw.bottom)) && (raw.top === null || validWorldAnchor(raw.top)); }
function validWorldAnchor(value: unknown) { if (!value || typeof value !== "object") return false; const raw = value as Record<string, unknown>; return typeof raw.id === "string" && point(raw.imagePoint) && (raw.worldHeightCm === null || finite(raw.worldHeightCm)); }
function normalizeWorldAnchors(value: unknown): CalibrationReference["worldAnchors"] | null { if (!validWorldAnchors(value)) return null; return value as CalibrationReference["worldAnchors"]; }
function legacyWorldAnchors(bottom: NormalizedPoint, top: NormalizedPoint, height: number): CalibrationReference["worldAnchors"] { return { bottom: { id: crypto.randomUUID(), imagePoint: bottom, worldHeightCm: 0, role: "BOTTOM" }, top: { id: crypto.randomUUID(), imagePoint: top, worldHeightCm: height, role: "TOP" } }; }
function normalizeGeometryMeasurement(value: unknown): GeometryMeasurement | null { if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; if (typeof raw.id !== "string" || typeof raw.name !== "string" || !point(raw.start) || !point(raw.end) || !(raw.valueCm === null || finite(raw.valueCm))) return null; const key = typeof raw.dimensionKey === "string" && dimensionKeys.includes(raw.dimensionKey as ObjectDimensionKey) ? raw.dimensionKey as ObjectDimensionKey : null; const semantics = key ? semanticsForDimensionKey(key) : semanticsForReferenceType("CUSTOM"); return { ...(raw as unknown as GeometryMeasurement), ...semantics, useForCalibration: false, semanticStatus: "CONFIRMED" }; }
function normalizeFloorPlane(value: unknown, baseline: SceneState["calibration"]["floorBaseline"]): SceneState["calibration"]["floorPlane"] { if (!value || typeof value !== "object") return baseline ? { mode: "BASIC", points: [baseline.start, baseline.end], actualGroundDimensionCm: null, mappingStatus: "ORIENTATION_ONLY" } : { mode: "NONE", points: [], actualGroundDimensionCm: null, mappingStatus: "NONE" }; const raw = value as Record<string, unknown>, points = Array.isArray(raw.points) ? raw.points.filter(point) as NormalizedPoint[] : []; const mode = raw.mode === "QUADRILATERAL" && points.length === 4 ? "QUADRILATERAL" : raw.mode === "BASIC" && points.length >= 2 ? "BASIC" : "NONE"; return { mode, points: mode === "NONE" ? [] : points.slice(0, mode === "QUADRILATERAL" ? 4 : 2), actualGroundDimensionCm: finite(raw.actualGroundDimensionCm) && raw.actualGroundDimensionCm > 0 ? raw.actualGroundDimensionCm : null, mappingStatus: mode === "NONE" ? "NONE" : "ORIENTATION_ONLY" }; }
function normalizeScene3d(value: unknown): SceneState["scene3d"] { const defaults = emptySceneState().scene3d; if (!value || typeof value !== "object") return defaults; const raw = value as Record<string, unknown>; return { ...defaults, workspaceMode: ["PHOTO","THREE_D","SPLIT"].includes(String(raw.workspaceMode)) ? raw.workspaceMode as SceneState["scene3d"]["workspaceMode"] : "PHOTO", cameraMappingStatus: ["CAMERA_APPROXIMATE","CAMERA_PARTIAL","CAMERA_CALIBRATED"].includes(String(raw.cameraMappingStatus)) ? raw.cameraMappingStatus as SceneState["scene3d"]["cameraMappingStatus"] : "CAMERA_APPROXIMATE", snapCm: [1,5,10].includes(Number(raw.snapCm)) ? Number(raw.snapCm) as 1|5|10 : 5, collisionBlocking: raw.collisionBlocking === true, selectedInteractionPointId: typeof raw.selectedInteractionPointId === "string" ? raw.selectedInteractionPointId : null, lastReachability: raw.lastReachability && typeof raw.lastReachability === "object" ? raw.lastReachability as SceneState["scene3d"]["lastReachability"] : null, lastCollisions: Array.isArray(raw.lastCollisions) ? raw.lastCollisions as SceneState["scene3d"]["lastCollisions"] : [], motion: raw.motion && typeof raw.motion === "object" ? raw.motion as SceneState["scene3d"]["motion"] : null }; }
function normalizeHuman3d(value: unknown, profile: SceneHuman["profile"]): SceneHuman["human3d"] | null { if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; if (raw.modelVersion !== "digital-human-3d-v1" || !raw.jointPositionsCm || !raw.rootPositionCm) return null; return { ...createHuman3DState(profile), ...(raw as unknown as SceneHuman["human3d"]) }; }
function normalizeGeometry3d(value: unknown): SceneObject["geometry3d"] { if (!value || typeof value !== "object") return null; const raw = value as Record<string, unknown>; if (typeof raw.type !== "string" || !raw.positionCm || !raw.dimensionsCm) return null; return raw as unknown as NonNullable<SceneObject["geometry3d"]>; }

function validRegion(value: unknown): value is SceneRegion {
  if (!value || typeof value !== "object") return false;
  const raw = value as Record<string, unknown>;
  if (typeof raw.id !== "string" || typeof raw.label !== "string" || !Array.isArray(raw.polygonImageNormalized) || raw.polygonImageNormalized.length < 3 || raw.polygonImageNormalized.length > 64) return false;
  return raw.polygonImageNormalized.every((item) => {
    if (!item || typeof item !== "object") return false;
    const candidate = item as Record<string, unknown>;
    return point(candidate.raw) && (candidate.snapped === null || point(candidate.snapped)) && point(candidate.effective);
  });
}

function validConstraint(value: unknown): value is SceneGeometryConstraint {
  if (!value || typeof value !== "object") return false;
  const raw = value as Record<string, unknown>;
  return typeof raw.id === "string" && typeof raw.type === "string" && Array.isArray(raw.nodeIds)
    && (raw.rawValue === null || finite(raw.rawValue)) && (raw.effectiveValue === null || finite(raw.effectiveValue))
    && finite(raw.weight) && raw.weight >= 0 && typeof raw.useForSolver === "boolean";
}

function normalizeRegions(value: unknown): SceneRegion[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const raw = item as Record<string, unknown>;
    const polygon = Array.isArray(raw.polygonImageNormalized) ? raw.polygonImageNormalized : [];
    const points = polygon.flatMap((entry) => {
      if (point(entry)) return [regionPoint(entry as NormalizedPoint)];
      if (!entry || typeof entry !== "object") return [];
      const candidate = entry as Record<string, unknown>;
      if (!point(candidate.raw)) return [];
      return [{
        raw: candidate.raw as NormalizedPoint,
        snapped: point(candidate.snapped) ? candidate.snapped as NormalizedPoint : null,
        effective: point(candidate.effective) ? candidate.effective as NormalizedPoint : candidate.raw as NormalizedPoint,
        snapSourceId: typeof candidate.snapSourceId === "string" ? candidate.snapSourceId : null,
        snapDistancePx: finite(candidate.snapDistancePx) ? candidate.snapDistancePx : null,
      }];
    });
    if (typeof raw.id !== "string" || points.length < 3) return [];
    const now = new Date().toISOString();
    return [{
      id: raw.id, type: typeof raw.type === "string" ? raw.type as SceneRegion["type"] : "CUSTOM_REGION",
      label: typeof raw.label === "string" && raw.label.trim() ? raw.label : "Obszar",
      polygonImageNormalized: points, associatedObjectId: typeof raw.associatedObjectId === "string" ? raw.associatedObjectId : null,
      planeId: typeof raw.planeId === "string" ? raw.planeId : null,
      source: typeof raw.source === "string" ? raw.source as SceneRegion["source"] : "UNKNOWN",
      quality: ["LOW", "MEDIUM", "HIGH", "INVALID"].includes(String(raw.quality)) ? raw.quality as SceneRegion["quality"] : "UNKNOWN",
      visible: raw.visible !== false, locked: raw.locked === true,
      createdAt: typeof raw.createdAt === "string" ? raw.createdAt : now,
      updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : now,
    }];
  });
}

function normalizeConstraintGraph(value: unknown): SceneState["constraintGraph"] {
  if (!value || typeof value !== "object") return createEmptyConstraintGraph();
  const raw = value as Record<string, unknown>;
  const nodes = Array.isArray(raw.nodes) ? raw.nodes.filter((item) => item && typeof item === "object" && typeof (item as Record<string, unknown>).id === "string") as SceneState["constraintGraph"]["nodes"] : [];
  const constraints = Array.isArray(raw.constraints) ? raw.constraints.filter(validConstraint).map((item) => ({ ...item, effectiveValue: item.source === "USER_PROVIDED" ? item.rawValue : item.effectiveValue })) : [];
  return { version: "scene-constraint-graph-v1.0", nodes, constraints };
}

function normalizeReconstructionState(value: unknown): SceneState["reconstructionState"] {
  const defaults = emptyReconstructionState();
  if (!value || typeof value !== "object") return defaults;
  const raw = value as Partial<SceneState["reconstructionState"]>;
  if (raw.version !== "scene-reconstruction-v1.0-beta.1") return defaults;
  return {
    ...defaults, ...raw,
    cameraModel: { ...defaults.cameraModel, ...(raw.cameraModel ?? {}) },
    readiness: { ...defaults.readiness, ...(raw.readiness ?? {}) },
    verticalScaleModel: { ...defaults.verticalScaleModel, ...(raw.verticalScaleModel ?? {}) },
  };
}
