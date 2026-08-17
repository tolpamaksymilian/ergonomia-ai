import { validateMeasurementForCalibration } from "./measurement-semantics.ts";
import type {
  CalibrationReference,
  NormalizedBox,
  NormalizedPoint,
  SceneObject,
  SceneRegion,
  SceneState,
} from "../../types/photo-scene";

export const GUIDED_SCENE_SETUP_VERSION = "guided-scene-setup-v1.0-beta.1" as const;

export const GUIDED_SCENE_STEPS = [
  { id: "PHOTO", label: "Zdjęcie", required: true },
  { id: "FLOOR", label: "Podłoga i pole pracy", required: true },
  { id: "HEIGHTS", label: "Znane wysokości", required: true },
  { id: "DIMENSIONS", label: "Szerokości, głębokości i odległości", required: false },
  { id: "OBJECTS", label: "Obiekty i powierzchnie", required: false },
  { id: "BUILD", label: "Rozpoznaj i zbuduj", required: true },
  { id: "VERIFY", label: "Weryfikacja geometrii", required: true },
  { id: "HUMAN", label: "Operator", required: true },
  { id: "ERGONOMICS", label: "Ergonomia", required: true },
] as const;

export type GuidedSceneStepId = (typeof GUIDED_SCENE_STEPS)[number]["id"];

export type HeightReferenceValidation = {
  reference: CalibrationReference;
  valid: boolean;
  reasons: string[];
};

export type GuidedSetupStatus = {
  hasImage: boolean;
  hasFloor: boolean;
  hasMovementZone: boolean;
  heightCount: number;
  dimensionCount: number;
  objectCount: number;
  reconstructionReady: boolean;
  reconstructionReviewed: boolean;
  humanCount: number;
  canBuild: boolean;
  recommendedStep: GuidedSceneStepId;
  heightValidations: HeightReferenceValidation[];
  spatialHeightAdvice: string | null;
};

export type GuidedWorkerContext = {
  contractVersion: "guided-scene-worker-context-v1.0";
  guidedSetupVersion: typeof GUIDED_SCENE_SETUP_VERSION;
  sceneSchemaVersion: SceneState["schema_version"];
  sceneRevision: string | null;
  originalImage: { width: number; height: number; storagePath?: string };
  floorRegions: SceneRegion[];
  movementZones: SceneRegion[];
  heightReferences: CalibrationReference[];
  dimensionReferences: CalibrationReference[];
  manualObjects: SceneObject[];
  manualSurfaces: SceneRegion[];
  constraintGraph: SceneState["constraintGraph"];
};

export type MeasurementAssociationSuggestion = {
  referenceId: string;
  referenceName: string;
  objectId: string;
  objectName: string;
  valueCm: number;
};

export function deriveGuidedSetupStatus(
  state: SceneState,
  options: { hasImage?: boolean } = {},
): GuidedSetupStatus {
  const hasImage = options.hasImage !== false;
  const floor = validRegionOfType(state, "FLOOR_REGION");
  const movement = validRegionOfType(state, "MOVEMENT_ZONE");
  const heightValidations = state.calibration.references
    .filter((reference) => reference.axis === "VERTICAL" && reference.useForCalibration)
    .map((reference) => validateGuidedHeightReference(reference, floor));
  const heightCount = heightValidations.filter((item) => item.valid).length;
  const dimensionCount = state.calibration.references.filter((reference) =>
    reference.active && ["HORIZONTAL", "GROUND_X", "GROUND_Y", "ARBITRARY"].includes(reference.axis),
  ).length;
  const objectCount = state.objects.filter((object) => object.status !== "USER_REJECTED").length;
  const reconstructionReady = ["SOLVED", "PARTIAL", "UNDERDETERMINED", "INCONSISTENT"].includes(state.reconstructionState.status);
  const reconstructionReviewed = state.reconstructionState.reviewStatus === "USER_REVIEWED"
    && state.reconstructionState.reviewedSceneRevision === state.reconstructionState.sceneRevision;
  const canBuild = hasImage && Boolean(floor) && Boolean(movement) && heightCount >= 2;
  const humanCount = state.humans.filter((human) => human.visible).length;

  let recommendedStep: GuidedSceneStepId = "PHOTO";
  if (hasImage) recommendedStep = "FLOOR";
  if (floor && movement) recommendedStep = "HEIGHTS";
  if (heightCount >= 2) recommendedStep = dimensionCount > 0 ? "OBJECTS" : "DIMENSIONS";
  if (objectCount > 0) recommendedStep = "BUILD";
  if (["QUEUED", "SOLVING"].includes(state.reconstructionState.status)) recommendedStep = "BUILD";
  if (reconstructionReady) recommendedStep = "VERIFY";
  if (reconstructionReviewed) recommendedStep = humanCount ? "ERGONOMICS" : "HUMAN";

  return {
    hasImage,
    hasFloor: Boolean(floor),
    hasMovementZone: Boolean(movement),
    heightCount,
    dimensionCount,
    objectCount,
    reconstructionReady,
    reconstructionReviewed,
    humanCount,
    canBuild,
    recommendedStep,
    heightValidations,
    spatialHeightAdvice: heightSpreadAdvice(heightValidations.filter((item) => item.valid).map((item) => item.reference)),
  };
}

export function validateGuidedHeightReference(
  reference: CalibrationReference,
  floorRegion: SceneRegion | null,
): HeightReferenceValidation {
  const reasons: string[] = [];
  const semantic = validateMeasurementForCalibration(reference);
  if (!semantic.valid) reasons.push("Pomiar nie jest poprawną pionową referencją kalibracyjną.");
  if (!Number.isFinite(reference.valueCm) || reference.valueCm < 10 || reference.valueCm > 600) {
    reasons.push("Wysokość musi mieścić się w technicznym zakresie 10–600 cm.");
  }
  if (!Number.isFinite(reference.pixelDistance) || reference.pixelDistance < 3) {
    reasons.push("Punkty wysokości są zbyt blisko siebie.");
  }
  const bottom = reference.worldAnchors.bottom?.imagePoint ?? reference.start;
  if (floorRegion && !pointInOrNearRegion(bottom, floorRegion, 0.08)) {
    reasons.push("Dolny punkt nie leży przy zaznaczonej podłodze.");
  }
  return { reference, valid: reasons.length === 0, reasons };
}

export function heightSpreadAdvice(references: CalibrationReference[]): string | null {
  if (references.length < 2) return null;
  const anchors = references.map((reference) => reference.worldAnchors.bottom?.imagePoint ?? reference.start);
  const horizontalSpread = Math.max(...anchors.map((point) => point.x)) - Math.min(...anchors.map((point) => point.x));
  const verticalSpread = Math.max(...anchors.map((point) => point.y)) - Math.min(...anchors.map((point) => point.y));
  if (horizontalSpread < 0.2 && verticalSpread < 0.18) {
    const meanX = anchors.reduce((sum, point) => sum + point.x, 0) / anchors.length;
    return `Dla stabilniejszego modelu dodaj wysokość również w ${meanX < 0.5 ? "prawej" : "lewej"} części zdjęcia.`;
  }
  return null;
}

export function createMovementZoneFromFloor(floor: SceneRegion, now = new Date().toISOString()): SceneRegion {
  return {
    ...floor,
    id: crypto.randomUUID(),
    type: "MOVEMENT_ZONE",
    label: "Pole pracy pracownika",
    polygonImageNormalized: floor.polygonImageNormalized.map((point) => ({
      ...point,
      raw: { ...point.raw },
      snapped: point.snapped ? { ...point.snapped } : null,
      effective: { ...point.effective },
    })),
    associatedObjectId: null,
    planeId: null,
    source: "USER_PROVIDED",
    createdAt: now,
    updatedAt: now,
  };
}

export function buildGuidedWorkerContext(
  state: SceneState,
  image: { width: number; height: number; storagePath?: string },
  sceneRevision: string | null = state.reconstructionState.sceneRevision,
): GuidedWorkerContext {
  return {
    contractVersion: "guided-scene-worker-context-v1.0",
    guidedSetupVersion: GUIDED_SCENE_SETUP_VERSION,
    sceneSchemaVersion: state.schema_version,
    sceneRevision,
    originalImage: image,
    floorRegions: state.regions.filter((region) => region.type === "FLOOR_REGION" && region.source !== "WORKER_SUGGESTED"),
    movementZones: state.regions.filter((region) => region.type === "MOVEMENT_ZONE" && region.source !== "WORKER_SUGGESTED"),
    heightReferences: state.calibration.references.filter((reference) => reference.axis === "VERTICAL" && reference.active),
    dimensionReferences: state.calibration.references.filter((reference) => reference.axis !== "VERTICAL" && reference.active),
    manualObjects: state.objects.filter((object) => object.source === "USER" && object.status !== "USER_REJECTED"),
    manualSurfaces: state.regions.filter((region) => region.source === "USER_PROVIDED" && !["FLOOR_REGION", "MOVEMENT_ZONE"].includes(region.type)),
    constraintGraph: state.constraintGraph,
  };
}

export function measurementAssociationSuggestions(
  state: SceneState,
  object: SceneObject,
): MeasurementAssociationSuggestion[] {
  const region = state.regions.find((item) => item.associatedObjectId === object.id);
  return state.calibration.references
    .filter((reference) => reference.objectId === null && reference.axis !== "VERTICAL")
    .filter((reference) => {
      const midpoint = { x: (reference.start.x + reference.end.x) / 2, y: (reference.start.y + reference.end.y) / 2 };
      return region ? pointInOrNearRegion(midpoint, region, 0.025) : pointInBox(midpoint, object.bbox, 0.025);
    })
    .map((reference) => ({
      referenceId: reference.id,
      referenceName: reference.name,
      objectId: object.id,
      objectName: object.name,
      valueCm: reference.valueCm,
    }));
}

export function bboxFromPolygon(points: NormalizedPoint[]): NormalizedBox {
  if (points.length < 3) throw new Error("polygon_requires_three_points");
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, width: Math.max(0.001, Math.max(...xs) - x), height: Math.max(0.001, Math.max(...ys) - y) };
}

export function polygonSelfIntersects(points: NormalizedPoint[]): boolean {
  if (points.length < 4) return false;
  for (let first = 0; first < points.length; first += 1) {
    const firstEnd = (first + 1) % points.length;
    for (let second = first + 1; second < points.length; second += 1) {
      const secondEnd = (second + 1) % points.length;
      if (first === second || firstEnd === second || secondEnd === first) continue;
      if (segmentsIntersect(points[first], points[firstEnd], points[second], points[secondEnd])) return true;
    }
  }
  return false;
}

function validRegionOfType(state: SceneState, type: SceneRegion["type"]): SceneRegion | null {
  return state.regions.find((region) => region.type === type
    && region.quality !== "INVALID"
    && region.polygonImageNormalized.length >= 3
    && !polygonSelfIntersects(region.polygonImageNormalized.map((point) => point.effective))) ?? null;
}

function pointInOrNearRegion(point: NormalizedPoint, region: SceneRegion, tolerance: number): boolean {
  const polygon = region.polygonImageNormalized.map((item) => item.effective);
  if (pointInPolygon(point, polygon)) return true;
  return polygon.some((start, index) => distanceToSegment(point, start, polygon[(index + 1) % polygon.length]) <= tolerance);
}

function pointInPolygon(point: NormalizedPoint, polygon: NormalizedPoint[]): boolean {
  let inside = false;
  for (let current = 0, previous = polygon.length - 1; current < polygon.length; previous = current++) {
    const a = polygon[current], b = polygon[previous];
    if (((a.y > point.y) !== (b.y > point.y))
      && point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y || Number.EPSILON) + a.x) inside = !inside;
  }
  return inside;
}

function pointInBox(point: NormalizedPoint, box: NormalizedBox, tolerance: number) {
  return point.x >= box.x - tolerance && point.x <= box.x + box.width + tolerance
    && point.y >= box.y - tolerance && point.y <= box.y + box.height + tolerance;
}

function distanceToSegment(point: NormalizedPoint, start: NormalizedPoint, end: NormalizedPoint) {
  const dx = end.x - start.x, dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared <= Number.EPSILON) return Math.hypot(point.x - start.x, point.y - start.y);
  const ratio = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared));
  return Math.hypot(point.x - (start.x + ratio * dx), point.y - (start.y + ratio * dy));
}

function segmentsIntersect(a: NormalizedPoint, b: NormalizedPoint, c: NormalizedPoint, d: NormalizedPoint) {
  const cross = (p: NormalizedPoint, q: NormalizedPoint, r: NormalizedPoint) =>
    (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
  const first = cross(a, b, c), second = cross(a, b, d), third = cross(c, d, a), fourth = cross(c, d, b);
  return first * second < 0 && third * fourth < 0;
}
