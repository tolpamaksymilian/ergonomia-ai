import type {
  GeometryCorrection, GeometryReadiness, NextBestMeasurement, NormalizedPoint,
  ObjectReconstructionQuality, SceneConstraintGraph, SceneGeometryConstraint, SceneObject,
  ScenePlane, SceneReconstructionState, SceneRegion, SceneRegionPoint, SceneRegionType,
  SceneState,
} from "../../types/photo-scene";

export const SCENE_GEOMETRY_VERSION = "scene-geometry-v2.0-beta.1" as const;
export const SCENE_RECONSTRUCTION_VERSION = "scene-reconstruction-v1.0-beta.1" as const;
export const SCENE_CONSTRAINT_GRAPH_VERSION = "scene-constraint-graph-v1.0" as const;
const EPSILON = 1e-9;

export type ReconstructionInput = {
  schemaVersion: "1.0";
  sceneRevision: string;
  image: { width: number; height: number };
  regions: SceneRegion[];
  objects: SceneObject[];
  planes: ScenePlane[];
  constraintGraph: SceneConstraintGraph;
  detectionEvidence: unknown;
  solver: { robustLoss: "HUBER"; autoRepairDerivedGeometry: true; assumptionsEnabled: false };
};

export type SceneReconstructionDocument = SceneReconstructionState & {
  schemaVersion: "1.0";
  generatedBy: "Ergonomia AI Scene Reconstruction Engine";
  input: { sceneRevision: string; regionCount: number; objectCount: number; constraintCount: number };
  groundModel: { regionId: string | null; status: "UNRESOLVED" | "PARTIAL" | "PROJECTIVE" };
  planes: ScenePlane[];
  derivedDimensions: Record<string, Partial<Record<"heightCm" | "widthCm" | "depthCm", number>>>;
  worldGeometry: SceneReconstructionState["worldGeometry"];
  quality: { conditioning: "GOOD" | "LIMITED" | "UNSTABLE"; reprojectionErrorPx: { mean: number | null; median: number | null; maximum: number | null } };
};

export function emptyGeometryReadiness(): GeometryReadiness {
  const entry = () => ({ status: "INSUFFICIENT" as const, reasons: ["Brak obliczonej geometrii sceny."] });
  return { HUMAN_PLACEMENT: entry(), WORK_HEIGHT: entry(), REACH: entry(), COLLISION: entry(), FULL_3D: entry() };
}

export function emptyReconstructionState(): SceneReconstructionState {
  return {
    version: SCENE_RECONSTRUCTION_VERSION,
    geometryVersion: SCENE_GEOMETRY_VERSION,
    sceneRevision: null,
    status: "UNSOLVED",
    cameraModel: {
      version: "camera-model-v2.0", status: "UNRESOLVED",
      vanishingDirections: { x: null, y: null, vertical: null }, evidenceQuality: "UNKNOWN",
      intrinsicsEstimated: false, diagnostics: [],
    },
    readiness: emptyGeometryReadiness(), objectQuality: {}, constraintResiduals: {},
    outlierConstraintIds: [], autoRepairs: [], conflicts: [], missingConstraints: [],
    nextBestMeasurements: [], derivedDimensions: {}, worldGeometry: {},
    verticalScaleModel: { kind: "UNRESOLVED", pixelsPerCm: null, coefficients: null, sourceConstraintIds: [], quality: "UNKNOWN" },
    diagnostics: [], runtimeMs: null, completedAt: null,
    reviewStatus: "UNREVIEWED", reviewedSceneRevision: null, reviewedAt: null,
  };
}

export function createEmptyConstraintGraph(): SceneConstraintGraph {
  return { version: SCENE_CONSTRAINT_GRAPH_VERSION, nodes: [], constraints: [] };
}

export function regionPoint(raw: NormalizedPoint, snapped: NormalizedPoint | null = null, snapSourceId: string | null = null, snapDistancePx: number | null = null): SceneRegionPoint {
  return { raw: clampPoint(raw), snapped: snapped ? clampPoint(snapped) : null, effective: clampPoint(snapped ?? raw), snapSourceId, snapDistancePx };
}

export function createSceneRegion(input: {
  type: SceneRegionType;
  label: string;
  points: NormalizedPoint[];
  associatedObjectId?: string | null;
  source?: SceneRegion["source"];
  id?: string;
  now?: string;
}): SceneRegion {
  const now = input.now ?? new Date().toISOString();
  return {
    id: input.id ?? crypto.randomUUID(), type: input.type, label: input.label.trim() || "Obszar",
    polygonImageNormalized: input.points.map((point) => regionPoint(point)),
    associatedObjectId: input.associatedObjectId ?? null, planeId: null,
    source: input.source ?? "USER_PROVIDED", quality: input.points.length >= 3 ? "MEDIUM" : "INVALID",
    visible: true, locked: false, createdAt: now, updatedAt: now,
  };
}

export function buildReconstructionInput(state: SceneState, image: { width: number; height: number }, sceneRevision: string, detectionEvidence: unknown = null): ReconstructionInput {
  return {
    schemaVersion: "1.0", sceneRevision, image,
    regions: state.regions, objects: state.objects, planes: state.planes,
    constraintGraph: buildConstraintGraph(state), detectionEvidence,
    solver: { robustLoss: "HUBER", autoRepairDerivedGeometry: true, assumptionsEnabled: false },
  };
}

export function buildConstraintGraph(state: SceneState): SceneConstraintGraph {
  const nodes = [...state.constraintGraph.nodes];
  const constraints = [...state.constraintGraph.constraints];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const constraintIds = new Set(constraints.map((constraint) => constraint.id));
  const representedReferenceIds = new Set(constraints.map((constraint) => constraint.target.id).filter((id): id is string => Boolean(id)));
  for (const region of state.regions) {
    const id = `region:${region.id}`;
    if (!nodeIds.has(id)) { nodes.push({ id, type: "ImageRegion", entityId: region.id }); nodeIds.add(id); }
  }
  for (const object of state.objects) {
    const id = `object:${object.id}`;
    if (!nodeIds.has(id)) { nodes.push({ id, type: "SceneObject", entityId: object.id }); nodeIds.add(id); }
    for (const assumption of object.shapeAssumptions.filter((value) => value !== "FREEFORM")) {
      const constraintId = `assumption:${object.id}:${assumption}`;
      if (constraintIds.has(constraintId)) continue;
      const type: SceneGeometryConstraint["type"] = assumption === "RECTANGULAR" ? "RECTANGULAR" : assumption === "PLANAR" ? "COPLANAR" : "PARALLEL";
      constraints.push({ id: constraintId, type, nodeIds: [id], objectId: object.id, regionId: object.regionIds[0] ?? null, target: { kind: "OBJECT", id: object.id, point: null }, rawValue: null, effectiveValue: null, unit: "none", source: "USER_CONFIRMED", weight: 1, useForSolver: true, status: "ACTIVE", residual: null, imageSegment: null });
      constraintIds.add(constraintId);
    }
  }
  for (const reference of state.calibration.references) {
    if (reference.semanticStatus !== "CONFIRMED" || !reference.active || reference.valueCm <= 0) continue;
    const type = reference.axis === "VERTICAL" ? "HEIGHT" : reference.axis === "GROUND_Y" ? "DEPTH" : reference.axis === "HORIZONTAL" || reference.axis === "GROUND_X" ? "WIDTH" : "DISTANCE";
    const id = `legacy-reference:${reference.id}`;
    if (constraintIds.has(id) || representedReferenceIds.has(reference.id)) continue;
    constraints.push({
      id, type, nodeIds: [], objectId: reference.objectId, regionId: null,
      target: { kind: "EDGE", id: reference.id, point: null }, rawValue: reference.valueCm,
      effectiveValue: reference.valueCm, unit: "cm", source: "USER_PROVIDED",
      weight: 1, useForSolver: type !== "HEIGHT" || reference.useForCalibration,
      status: reference.useForCalibration || type !== "HEIGHT" ? "ACTIVE" : "DISABLED", residual: null,
      imageSegment: { start: reference.start, end: reference.end },
    });
  }
  return { version: SCENE_CONSTRAINT_GRAPH_VERSION, nodes, constraints };
}

export function solveSceneReconstruction(input: ReconstructionInput): SceneReconstructionDocument {
  const started = performance.now();
  const repairedRegions: SceneRegion[] = [];
  const autoRepairs: GeometryCorrection[] = [];
  for (const region of input.regions) {
    const repaired = repairRegion(region, input.image);
    repairedRegions.push(repaired.region);
    autoRepairs.push(...repaired.corrections);
  }

  const active = input.constraintGraph.constraints.filter(isUsableConstraint);
  const fit = fitConstraintGroups(active, input.objects);
  const verticalScaleModel = fitVerticalScale(active, fit.outliers, input.image);
  const groundRegion = repairedRegions.find((region) => region.type === "FLOOR_REGION" && region.quality !== "INVALID") ?? null;
  const movementRegion = repairedRegions.find((region) => region.type === "MOVEMENT_ZONE" && region.quality !== "INVALID") ?? null;
  const planes = solvePlanes(repairedRegions, input.objects, fit.values);
  const hasProjectivePlane = planes.some((plane) => plane.homography?.length === 9);
  const cameraModel: SceneReconstructionState["cameraModel"] = {
    version: "camera-model-v2.0",
    status: hasProjectivePlane ? "PROJECTIVE" : verticalScaleModel.pixelsPerCm !== null || groundRegion ? "PARTIAL" : "UNRESOLVED",
    vanishingDirections: deriveVanishingDirections(input.detectionEvidence),
    evidenceQuality: hasProjectivePlane ? "MEDIUM" : verticalScaleModel.quality === "HIGH" ? "HIGH" : verticalScaleModel.quality === "MEDIUM" ? "MEDIUM" : "LOW",
    intrinsicsEstimated: false,
    diagnostics: hasProjectivePlane ? ["Planar homography solved for at least one confirmed surface."] : ["Camera intrinsics were not inferred; solvePnP was not used."],
  };
  const objectQuality: Record<string, ObjectReconstructionQuality> = {};
  const worldGeometry: SceneReconstructionDocument["worldGeometry"] = {};
  const derivedDimensions: SceneReconstructionDocument["derivedDimensions"] = {};
  for (const object of input.objects.filter((item) => item.status !== "USER_REJECTED")) {
    const dims = fit.values[object.id] ?? {};
    const hasRegion = repairedRegions.some((region) => region.associatedObjectId === object.id && region.quality !== "INVALID");
    const quality: ObjectReconstructionQuality = !hasRegion ? "TWO_D_ONLY" : dims.widthCm && dims.depthCm && dims.heightCm ? "HIGH" : "PARTIAL";
    objectQuality[object.id] = quality;
    derivedDimensions[object.id] = dims;
    worldGeometry[object.id] = { status: quality, cornersCm: cuboidCorners(dims) };
  }
  const groundPlane = groundRegion ? planes.find((plane) => plane.regionId === groundRegion.id) ?? null : null;
  for (const region of repairedRegions.filter((item) => ["FLOOR_REGION", "MOVEMENT_ZONE", "STANDING_ZONE", "INTERACTION_ZONE", "NO_GO_ZONE"].includes(item.type))) {
    const polygonCm = groundPlane?.homography
      ? region.polygonImageNormalized.map((point) => projectGroundPoint(point.effective, groundPlane.homography!))
      : [];
    worldGeometry[`region:${region.id}`] = {
      status: polygonCm.length === region.polygonImageNormalized.length && polygonCm.every((point): point is { x: number; y: number; z: number } => point !== null) ? "PROJECTIVE" : "PARTIAL",
      cornersCm: [],
      polygonCm: polygonCm.filter((point): point is { x: number; y: number; z: number } => point !== null),
      sourcePlaneId: groundPlane?.id ?? null,
    };
  }
  const readiness = computeReadiness({ groundRegion, movementRegion, verticalScaleModel, objectQuality, dimensions: fit.values, conflicts: fit.conflicts.length });
  const nextBestMeasurements = selectNextBestMeasurements(input.objects, repairedRegions, fit.values, readiness);
  const missingConstraints = nextBestMeasurements.map((item) => item.reason);
  const hasDerivedDimension = Object.values(fit.values).some((dimensions) => Object.values(dimensions).some((value) => typeof value === "number" && Number.isFinite(value)));
  const status: SceneReconstructionState["status"] = fit.conflicts.length
    ? "INCONSISTENT"
    : active.length === 0 || (!hasDerivedDimension && verticalScaleModel.pixelsPerCm === null) ? "UNDERDETERMINED"
    : readiness.FULL_3D.status === "READY" ? "SOLVED"
    : "PARTIAL";
  const residualValues = Object.values(fit.residuals).filter(Number.isFinite);
  return {
    schemaVersion: "1.0", generatedBy: "Ergonomia AI Scene Reconstruction Engine",
    version: SCENE_RECONSTRUCTION_VERSION, geometryVersion: SCENE_GEOMETRY_VERSION,
    sceneRevision: input.sceneRevision, status, cameraModel, readiness, objectQuality,
    constraintResiduals: fit.residuals, outlierConstraintIds: fit.outliers,
    autoRepairs, conflicts: fit.conflicts, missingConstraints, nextBestMeasurements,
    verticalScaleModel,
    diagnostics: buildDiagnostics(status, verticalScaleModel, autoRepairs.length, fit.outliers.length),
    runtimeMs: Math.max(0, performance.now() - started), completedAt: new Date().toISOString(),
    input: { sceneRevision: input.sceneRevision, regionCount: input.regions.length, objectCount: input.objects.length, constraintCount: input.constraintGraph.constraints.length },
    groundModel: { regionId: groundRegion?.id ?? null, status: !groundRegion ? "UNRESOLVED" : planes.some((plane) => plane.regionId === groundRegion.id && plane.homography) ? "PROJECTIVE" : "PARTIAL" },
    planes, derivedDimensions, worldGeometry,
    quality: { conditioning: status === "INCONSISTENT" ? "UNSTABLE" : status === "SOLVED" ? "GOOD" : "LIMITED", reprojectionErrorPx: statistics(residualValues) },
  };
}

export function applyReconstructionSummary(state: SceneState, document: SceneReconstructionDocument): SceneState {
  return {
    ...state,
    reconstructionState: {
      version: document.version, geometryVersion: document.geometryVersion, sceneRevision: document.sceneRevision,
      status: document.status, cameraModel: document.cameraModel, readiness: document.readiness,
      objectQuality: document.objectQuality, constraintResiduals: document.constraintResiduals,
      outlierConstraintIds: document.outlierConstraintIds, autoRepairs: document.autoRepairs,
      conflicts: document.conflicts, missingConstraints: document.missingConstraints,
      nextBestMeasurements: document.nextBestMeasurements, derivedDimensions: document.derivedDimensions,
      worldGeometry: document.worldGeometry, verticalScaleModel: document.verticalScaleModel,
      diagnostics: document.diagnostics, runtimeMs: document.runtimeMs, completedAt: document.completedAt,
    },
    planes: document.planes,
    objects: state.objects.map((object) => ({ ...object, reconstructionQuality: document.objectQuality[object.id] ?? "UNSOLVED" })),
  };
}

export function pointInPolygon(point: NormalizedPoint, region: Pick<SceneRegion, "polygonImageNormalized">): boolean {
  const polygon = region.polygonImageNormalized.map((item) => item.effective);
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if (((a.y > point.y) !== (b.y > point.y)) && point.x < (b.x - a.x) * (point.y - a.y) / ((b.y - a.y) || EPSILON) + a.x) inside = !inside;
  }
  return inside;
}

export function nearestFeasiblePoint(point: NormalizedPoint, region: Pick<SceneRegion, "polygonImageNormalized">): { point: NormalizedPoint; deltaNormalized: number; corrected: boolean } {
  if (pointInPolygon(point, region)) return { point, deltaNormalized: 0, corrected: false };
  const polygon = region.polygonImageNormalized.map((item) => item.effective);
  let closest = polygon[0] ?? clampPoint(point), distance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < polygon.length; index += 1) {
    const candidate = closestPointOnSegment(point, polygon[index], polygon[(index + 1) % polygon.length]);
    const current = length(point, candidate);
    if (current < distance) { distance = current; closest = candidate; }
  }
  const centroid = polygonCentroid(polygon);
  const nudged = { x: closest.x + (centroid.x - closest.x) * 1e-6, y: closest.y + (centroid.y - closest.y) * 1e-6 };
  return { point: clampPoint(nudged), deltaNormalized: Number.isFinite(distance) ? distance : 0, corrected: true };
}

export function sceneErgonomicsGeometryGate(state: Pick<SceneState, "reconstructionState">): { allowed: boolean; reasons: string[] } {
  const reconstruction = state.reconstructionState;
  if (["QUEUED", "SOLVING"].includes(reconstruction.status)) return { allowed: false, reasons: ["Geometria sceny jest właśnie obliczana."] };
  if (["UNSOLVED", "UNDERDETERMINED", "INCONSISTENT", "FAILED"].includes(reconstruction.status)) {
    return { allowed: false, reasons: ["Najpierw oblicz spójną geometrię sceny i usuń zgłoszone konflikty."] };
  }
  const placement = reconstruction.readiness.HUMAN_PLACEMENT;
  if (placement.status !== "READY") return { allowed: false, reasons: placement.reasons.length ? placement.reasons : ["Geometria nie jest gotowa do osadzenia operatora."] };
  return { allowed: true, reasons: [] };
}

export function getReconstructedVerticalScale(state: Pick<SceneState, "reconstructionState">, point: NormalizedPoint): { pixelsPerCm: number | null; quality: "GOOD" | "PARTIAL" | "UNKNOWN"; referencesUsed: string[]; uncertainty: number; status: SceneState["calibration"]["scaleField"]["status"] } | null {
  const model = state.reconstructionState.verticalScaleModel;
  if (state.reconstructionState.status === "UNSOLVED" || state.reconstructionState.status === "FAILED" || model.pixelsPerCm === null) return null;
  let pixelsPerCm: number | null = model.pixelsPerCm;
  if (model.kind === "INVERSE_AFFINE_VERTICAL" && model.coefficients) {
    const denominator = model.coefficients[0] + model.coefficients[1] * point.y;
    pixelsPerCm = denominator > EPSILON ? 1 / denominator : null;
  }
  if (pixelsPerCm === null || !Number.isFinite(pixelsPerCm) || pixelsPerCm <= EPSILON) return null;
  return { pixelsPerCm, quality: model.quality === "HIGH" ? "GOOD" : model.quality === "MEDIUM" ? "PARTIAL" : "UNKNOWN", referencesUsed: model.sourceConstraintIds, uncertainty: model.quality === "HIGH" ? .05 : .2, status: model.quality === "HIGH" ? "PERSPECTIVE_GOOD" : "PERSPECTIVE_PARTIAL" };
}

function isUsableConstraint(constraint: SceneGeometryConstraint) {
  if (!constraint.useForSolver || constraint.status === "DISABLED") return false;
  return ["HEIGHT", "WIDTH", "DEPTH", "DISTANCE"].includes(constraint.type)
    ? constraint.rawValue !== null && Number.isFinite(constraint.rawValue) && constraint.rawValue > 0
    : true;
}

function fitConstraintGroups(constraints: SceneGeometryConstraint[], objects: SceneObject[]) {
  const groups = new Map<string, SceneGeometryConstraint[]>();
  for (const constraint of constraints.filter((item) => ["HEIGHT", "WIDTH", "DEPTH", "DISTANCE"].includes(item.type))) {
    const entityId = constraint.objectId ?? (constraint.regionId ? `region:${constraint.regionId}` : "scene");
    const key = `${entityId}|${constraint.type}`;
    groups.set(key, [...(groups.get(key) ?? []), constraint]);
  }
  const values: Record<string, Partial<Record<"heightCm" | "widthCm" | "depthCm", number>>> = {};
  const residuals: Record<string, number> = {};
  const outliers: string[] = [];
  const conflicts: SceneReconstructionState["conflicts"] = [];
  for (const [key, items] of groups) {
    const separator = key.lastIndexOf("|");
    const objectId = key.slice(0, separator), kind = key.slice(separator + 1);
    const result = robustLocation(items.map((item) => ({ id: item.id, value: item.rawValue!, weight: provenanceWeight(item.source) * Math.max(EPSILON, item.weight) })));
    for (const item of items) residuals[item.id] = Math.abs(item.rawValue! - result.value);
    outliers.push(...result.outliers);
    const object = objects.find((item) => item.id === objectId);
    const inlierValues = items.filter((item) => !result.outliers.includes(item.id)).map((item) => item.rawValue!);
    const authoritativeValues = items.filter((item) => ["USER_PROVIDED", "USER_CONFIRMED"].includes(item.source)).map((item) => item.rawValue!);
    const conflictingPair = authoritativeValues.length === 2 && relativeRange(authoritativeValues) > .15;
    if (object && object.shapeAssumptions.includes("RECTANGULAR") && (conflictingPair || (inlierValues.length >= 2 && relativeRange(inlierValues) > .15))) {
      conflicts.push({ id: `conflict:${key}`, objectId, constraintIds: items.map((item) => item.id), code: "CONSTRAINT_CONFLICT", message: `Podane wartości ${kind.toLowerCase()} nie są zgodne z założeniem prostokątnego obiektu.` });
    }
    if (objectId !== "scene" && Number.isFinite(result.value)) {
      values[objectId] ??= {};
      const dimensionKey = kind === "HEIGHT" ? "heightCm" : kind === "WIDTH" ? "widthCm" : kind === "DEPTH" ? "depthCm" : null;
      if (dimensionKey) values[objectId][dimensionKey] = result.value;
    }
  }
  return { values, residuals, outliers: [...new Set(outliers)], conflicts };
}

function robustLocation(values: Array<{ id: string; value: number; weight: number }>) {
  if (!values.length) return { value: Number.NaN, outliers: [] as string[] };
  const center = weightedMedian(values);
  const deviations = values.map((item) => Math.abs(item.value - center));
  const mad = median(deviations);
  const threshold = Math.max(1, mad * 3.5, Math.abs(center) * .1);
  const outliers = values.filter((item) => Math.abs(item.value - center) > threshold).map((item) => item.id);
  const inliers = values.filter((item) => !outliers.includes(item.id));
  let estimate = weightedMedian(inliers.length ? inliers : values);
  for (let iteration = 0; iteration < 8; iteration += 1) {
    const scale = Math.max(1, median((inliers.length ? inliers : values).map((item) => Math.abs(item.value - estimate))) * 1.4826);
    let numerator = 0, denominator = 0;
    for (const item of inliers.length ? inliers : values) {
      const residual = item.value - estimate;
      const huber = Math.abs(residual) <= 1.345 * scale ? 1 : (1.345 * scale) / Math.abs(residual);
      numerator += item.value * item.weight * huber; denominator += item.weight * huber;
    }
    if (denominator <= EPSILON) break;
    const next = numerator / denominator;
    if (!Number.isFinite(next) || Math.abs(next - estimate) < 1e-8) break;
    estimate = next;
  }
  return { value: estimate, outliers };
}

function fitVerticalScale(constraints: SceneGeometryConstraint[], outliers: string[], image: ReconstructionInput["image"]): SceneReconstructionState["verticalScaleModel"] {
  const candidates = constraints.filter((item) => item.type === "HEIGHT" && item.imageSegment && !outliers.includes(item.id)).map((item) => ({
    id: item.id,
    scale: pixelDistance(item.imageSegment!.start, item.imageSegment!.end, image) / item.rawValue!,
    y: (item.imageSegment!.start.y + item.imageSegment!.end.y) / 2,
    weight: provenanceWeight(item.source) * Math.max(EPSILON, item.weight),
  })).filter((item) => Number.isFinite(item.scale) && item.scale > EPSILON);
  if (!candidates.length) return { kind: "UNRESOLVED", pixelsPerCm: null, coefficients: null, sourceConstraintIds: [], quality: "UNKNOWN" };
  const perspective = fitInverseAffineVertical(candidates);
  if (perspective) return perspective;
  const result = robustLocation(candidates.map((item) => ({ id: item.id, value: item.scale, weight: item.weight })));
  const inliers = candidates.filter((item) => !result.outliers.includes(item.id));
  return { kind: "ROBUST_CONSTANT", pixelsPerCm: result.value, coefficients: null, sourceConstraintIds: inliers.map((item) => item.id), quality: inliers.length >= 3 ? "HIGH" : inliers.length >= 1 ? "MEDIUM" : "LOW" };
}

function fitInverseAffineVertical(candidates: Array<{ id: string; scale: number; y: number; weight: number }>): SceneReconstructionState["verticalScaleModel"] | null {
  if (candidates.length < 3 || Math.max(...candidates.map((item) => item.y)) - Math.min(...candidates.map((item) => item.y)) < .15) return null;
  let weights = candidates.map((item) => item.weight);
  let coefficients: [number, number] | null = null;
  for (let iteration = 0; iteration < 6; iteration += 1) {
    let s = 0, sy = 0, syy = 0, st = 0, syt = 0;
    candidates.forEach((item, index) => { const weight = weights[index], target = 1 / item.scale; s += weight; sy += weight * item.y; syy += weight * item.y * item.y; st += weight * target; syt += weight * item.y * target; });
    const determinant = s * syy - sy * sy;
    if (!Number.isFinite(determinant) || Math.abs(determinant) <= EPSILON) return null;
    coefficients = [(st * syy - sy * syt) / determinant, (s * syt - sy * st) / determinant];
    if (!coefficients.every(Number.isFinite) || Math.min(coefficients[0], coefficients[0] + coefficients[1]) <= EPSILON) return null;
    const residuals = candidates.map((item) => Math.abs(1 / item.scale - (coefficients![0] + coefficients![1] * item.y)));
    const scale = Math.max(EPSILON, median(residuals) * 1.4826);
    weights = candidates.map((item, index) => item.weight * (residuals[index] <= 1.345 * scale ? 1 : (1.345 * scale) / residuals[index]));
  }
  if (!coefficients) return null;
  const residuals = candidates.map((item) => Math.abs(1 / item.scale - (coefficients[0] + coefficients[1] * item.y)));
  const typical = median(candidates.map((item) => 1 / item.scale));
  const threshold = Math.max(EPSILON, median(residuals) * 3.5, typical * .1);
  const inliers = candidates.filter((_item, index) => residuals[index] <= threshold);
  if (inliers.length < 3) return null;
  const referenceY = median(inliers.map((item) => item.y)), denominator = coefficients[0] + coefficients[1] * referenceY;
  return denominator > EPSILON ? { kind: "INVERSE_AFFINE_VERTICAL", pixelsPerCm: 1 / denominator, coefficients, sourceConstraintIds: inliers.map((item) => item.id), quality: "HIGH" } : null;
}

function repairRegion(region: SceneRegion, image: { width: number; height: number }): { region: SceneRegion; corrections: GeometryCorrection[] } {
  const raw = region.polygonImageNormalized.map((point) => point.effective);
  if (raw.length < 3) return { region: { ...region, quality: "INVALID" }, corrections: [] };
  if (!selfIntersects(raw)) return Math.abs(polygonArea(raw)) <= EPSILON ? { region: { ...region, quality: "INVALID" }, corrections: [] } : { region, corrections: [] };
  const center = polygonCentroid(raw);
  const ordered = [...region.polygonImageNormalized].sort((a, b) => Math.atan2(a.effective.y - center.y, a.effective.x - center.x) - Math.atan2(b.effective.y - center.y, b.effective.x - center.x));
  if (selfIntersects(ordered.map((item) => item.effective))) return { region: { ...region, quality: "INVALID" }, corrections: [] };
  const deltaPx = ordered.reduce((sum, item, index) => sum + pixelDistance(item.effective, region.polygonImageNormalized[index].effective, image), 0);
  return {
    region: { ...region, polygonImageNormalized: ordered, source: "AUTO_REPAIRED", quality: "MEDIUM" },
    corrections: [{ id: `repair:${region.id}:polygon-order`, type: "POLYGON_ORDER", entityId: region.id, before: region.polygonImageNormalized.map((item) => item.raw), after: ordered.map((item) => item.effective), delta: deltaPx, unit: "px", reason: "Uporządkowano punkty samoprzecinającego się wielokąta; surowe punkty pozostają zapisane." }],
  };
}

function solvePlanes(regions: SceneRegion[], objects: SceneObject[], dimensions: SceneReconstructionDocument["derivedDimensions"]): ScenePlane[] {
  return regions.filter((region) => ["FLOOR_REGION", "WORK_SURFACE", "OBJECT_TOP_FACE", "CONTROL_PANEL_REGION", "SHELF_REGION"].includes(region.type)).map((region) => {
    const object = objects.find((item) => item.id === region.associatedObjectId);
    const dims = object ? dimensions[object.id] : dimensions[`region:${region.id}`];
    const points = region.polygonImageNormalized.map((item) => item.effective);
    const homography = points.length === 4 && dims?.widthCm && dims?.depthCm ? solveHomography(points, [{ x: 0, y: 0 }, { x: dims.widthCm, y: 0 }, { x: dims.widthCm, y: dims.depthCm }, { x: 0, y: dims.depthCm }]) : null;
    return { id: region.planeId ?? `plane:${region.id}`, kind: region.type === "FLOOR_REGION" ? "GROUND" : region.type === "CONTROL_PANEL_REGION" ? "CONTROL_PANEL" : region.type === "SHELF_REGION" ? "SHELF" : "OBJECT_TOP", regionId: region.id, objectId: region.associatedObjectId, normal: region.type === "CONTROL_PANEL_REGION" ? { x: 0, y: 0, z: 1 } : { x: 0, y: 1, z: 0 }, offsetCm: dims?.heightCm ?? (region.type === "FLOOR_REGION" ? 0 : null), homography, source: homography ? "SOLVER_DERIVED" : "SOLVER_ESTIMATED", quality: homography ? "HIGH" : "MEDIUM", locked: region.locked } as ScenePlane;
  });
}

function computeReadiness(input: { groundRegion: SceneRegion | null; movementRegion: SceneRegion | null; verticalScaleModel: SceneReconstructionState["verticalScaleModel"]; objectQuality: Record<string, ObjectReconstructionQuality>; dimensions: SceneReconstructionDocument["derivedDimensions"]; conflicts: number }): GeometryReadiness {
  if (input.conflicts) {
    const conflict = { status: "INVALID" as const, reasons: ["Co najmniej jeden rzeczywisty wymiar jest sprzeczny z aktywnymi założeniami."] };
    return { HUMAN_PLACEMENT: conflict, WORK_HEIGHT: conflict, REACH: conflict, COLLISION: conflict, FULL_3D: conflict };
  }
  const hasGround = Boolean(input.groundRegion);
  const hasScale = input.verticalScaleModel.pixelsPerCm !== null;
  const dimensionValues = Object.values(input.dimensions);
  const hasHeight = dimensionValues.some((item) => item.heightCm);
  const hasDepth = dimensionValues.length > 0 && dimensionValues.every((item) => item.depthCm);
  const highObjects = Object.values(input.objectQuality).filter((value) => value === "HIGH").length;
  return {
    HUMAN_PLACEMENT: hasGround && hasScale ? { status: "READY", reasons: [] } : { status: hasGround || hasScale ? "PARTIAL" : "INSUFFICIENT", reasons: [!hasGround ? "Zaznacz obszar podłogi." : "", !hasScale ? "Dodaj rzeczywistą wysokość pionową." : ""].filter(Boolean) },
    WORK_HEIGHT: hasHeight ? { status: "READY", reasons: [] } : { status: "NEEDS_HEIGHT", reasons: ["Podaj wysokość powierzchni roboczej."] },
    REACH: hasGround && hasScale ? { status: "READY", reasons: input.movementRegion ? [] : ["Pole ruchu nie jest wymagane, ale ograniczy analizowany obszar."] } : { status: "INSUFFICIENT", reasons: ["Najpierw przygotuj wiarygodne osadzenie operatora."] },
    COLLISION: hasDepth ? { status: "READY", reasons: [] } : { status: "NEEDS_DEPTH", reasons: ["Brakuje głębokości co najmniej jednego obiektu; kolizja pozostaje nieznana."] },
    FULL_3D: highObjects > 0 && hasGround ? { status: "READY", reasons: [] } : { status: "PARTIAL", reasons: ["Część obiektów ma tylko geometrię 2D lub niepełne wymiary."] },
  };
}

function selectNextBestMeasurements(objects: SceneObject[], regions: SceneRegion[], dimensions: SceneReconstructionDocument["derivedDimensions"], readiness: GeometryReadiness): NextBestMeasurement[] {
  const result: NextBestMeasurement[] = [];
  if (readiness.HUMAN_PLACEMENT.status !== "READY") {
    const floor = regions.find((region) => region.type === "FLOOR_REGION");
    result.push({ measurementKind: "VERTICAL_HEIGHT", objectId: null, suggestedPoints: floor ? verticalGuide(floor) : null, reason: floor ? "Dodaj jedną rzeczywistą pionową wysokość przy obszarze podłogi." : "Najpierw zaznacz obszar podłogi.", expectedBenefit: "Pozwoli stabilnie osadzać operatora w scenie." });
  }
  for (const object of objects.filter((item) => item.status !== "USER_REJECTED")) {
    const dims = dimensions[object.id] ?? {};
    const region = regions.find((item) => item.associatedObjectId === object.id && ["WORK_SURFACE", "OBJECT_TOP_FACE"].includes(item.type));
    if (!dims.heightCm) result.push({ measurementKind: "WORK_SURFACE_HEIGHT", objectId: object.id, suggestedPoints: region ? verticalGuide(region) : null, reason: `Podaj rzeczywistą wysokość: ${object.name}.`, expectedBenefit: "Wyznaczy wysokość roboczą oraz pionowe osadzenie obiektu." });
    else if (!dims.widthCm) result.push({ measurementKind: "OBJECT_WIDTH", objectId: object.id, suggestedPoints: region ? edgeGuide(region, 0) : null, reason: `Podaj rzeczywistą szerokość: ${object.name}.`, expectedBenefit: "Pozwoli wyznaczyć skalę płaszczyzny obiektu." });
    else if (!dims.depthCm) result.push({ measurementKind: "OBJECT_DEPTH", objectId: object.id, suggestedPoints: region ? edgeGuide(region, 1) : null, reason: `Podaj rzeczywistą głębokość: ${object.name}.`, expectedBenefit: "Pozwoli wyznaczyć płaszczyznę blatu i poprawi model kolizji." });
  }
  return result.slice(0, 1);
}

function solveHomography(source: NormalizedPoint[], target: NormalizedPoint[]): number[] | null {
  if (source.length !== 4 || target.length !== 4) return null;
  const matrix: number[][] = [];
  for (let index = 0; index < 4; index += 1) {
    const { x, y } = source[index], { x: u, y: v } = target[index];
    matrix.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    matrix.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  }
  const solution = gaussianSolve(matrix);
  return solution ? [...solution, 1] : null;
}

function projectGroundPoint(point: NormalizedPoint, homography: number[]): { x: number; y: number; z: number } | null {
  if (homography.length !== 9 || !homography.every(Number.isFinite)) return null;
  const denominator = homography[6] * point.x + homography[7] * point.y + homography[8];
  if (!Number.isFinite(denominator) || Math.abs(denominator) <= EPSILON) return null;
  const x = (homography[0] * point.x + homography[1] * point.y + homography[2]) / denominator;
  const z = (homography[3] * point.x + homography[4] * point.y + homography[5]) / denominator;
  return Number.isFinite(x) && Number.isFinite(z) ? { x, y: 0, z } : null;
}

function gaussianSolve(augmented: number[][]): number[] | null {
  const rows = augmented.map((row) => [...row]);
  const size = rows.length;
  for (let column = 0; column < size; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < size; row += 1) if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) pivot = row;
    if (Math.abs(rows[pivot][column]) < 1e-12) return null;
    [rows[column], rows[pivot]] = [rows[pivot], rows[column]];
    const divisor = rows[column][column];
    for (let item = column; item <= size; item += 1) rows[column][item] /= divisor;
    for (let row = 0; row < size; row += 1) {
      if (row === column) continue;
      const factor = rows[row][column];
      for (let item = column; item <= size; item += 1) rows[row][item] -= factor * rows[column][item];
    }
  }
  const solution = rows.map((row) => row[size]);
  return solution.every(Number.isFinite) ? solution : null;
}

function deriveVanishingDirections(value: unknown): SceneReconstructionState["cameraModel"]["vanishingDirections"] {
  if (!value || typeof value !== "object") return { x: null, y: null, vertical: null };
  const detection = value as { perspective_evidence?: { vanishing_point?: NormalizedPoint | null; dominant_vertical_angle_deg?: number | null } };
  const vanishing = detection.perspective_evidence?.vanishing_point ?? null;
  const angle = detection.perspective_evidence?.dominant_vertical_angle_deg;
  const vertical = typeof angle === "number" && Number.isFinite(angle) ? { x: Math.cos(angle * Math.PI / 180), y: Math.sin(angle * Math.PI / 180) } : null;
  return { x: vanishing, y: null, vertical };
}

function cuboidCorners(dimensions: Partial<Record<"heightCm" | "widthCm" | "depthCm", number>>) {
  const width = dimensions.widthCm, depth = dimensions.depthCm, height = dimensions.heightCm;
  if (!width || !depth || !height) return [];
  return [0, width].flatMap((x) => [0, height].flatMap((y) => [0, depth].map((z) => ({ x, y, z }))));
}

function buildDiagnostics(status: SceneReconstructionState["status"], scale: SceneReconstructionState["verticalScaleModel"], repairs: number, outliers: number) {
  const diagnostics = [{ code: `RECONSTRUCTION_${status}`, message: status === "UNDERDETERMINED" ? "Model jest nieokreślony; potrzebny jest kolejny wskazany wymiar." : `Stan rekonstrukcji: ${status}.` }];
  if (scale.pixelsPerCm === null) diagnostics.push({ code: "VERTICAL_SCALE_UNRESOLVED", message: "Pionowa projekcja nie została wyznaczona." });
  if (repairs) diagnostics.push({ code: "AUTO_REPAIRS_RECORDED", message: `Zapisano korekty geometrii: ${repairs}.` });
  if (outliers) diagnostics.push({ code: "OUTLIERS_ISOLATED", message: `Odizolowano odstające ograniczenia: ${outliers}.` });
  return diagnostics;
}

function provenanceWeight(source: SceneGeometryConstraint["source"]) {
  return ({ USER_PROVIDED: 10, USER_CONFIRMED: 8, WORKER_DETECTED: 3, WORKER_SUGGESTED: 2, SOLVER_DERIVED: 5, SOLVER_ESTIMATED: 1.5, AUTO_REPAIRED: 1, ASSUMED: .25, UNKNOWN: .1 })[source];
}

function weightedMedian(values: Array<{ value: number; weight: number }>) {
  const ordered = [...values].sort((a, b) => a.value - b.value);
  const total = ordered.reduce((sum, item) => sum + item.weight, 0);
  let cumulative = 0;
  for (const item of ordered) { cumulative += item.weight; if (cumulative >= total / 2) return item.value; }
  return ordered.at(-1)?.value ?? Number.NaN;
}
function median(values: number[]) { const ordered = [...values].sort((a, b) => a - b); const middle = Math.floor(ordered.length / 2); return ordered.length ? ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2 : 0; }
function relativeRange(values: number[]) { const low = Math.min(...values), high = Math.max(...values); return high <= EPSILON ? 0 : (high - low) / high; }
function statistics(values: number[]) { if (!values.length) return { mean: null, median: null, maximum: null }; return { mean: values.reduce((sum, value) => sum + value, 0) / values.length, median: median(values), maximum: Math.max(...values) }; }
function clampPoint(point: NormalizedPoint) { return { x: Math.max(0, Math.min(1, finiteOr(point.x, 0))), y: Math.max(0, Math.min(1, finiteOr(point.y, 0))) }; }
function finiteOr(value: number, fallback: number) { return Number.isFinite(value) ? value : fallback; }
function length(a: NormalizedPoint, b: NormalizedPoint) { return Math.hypot(a.x - b.x, a.y - b.y); }
function pixelDistance(a: NormalizedPoint, b: NormalizedPoint, image: { width: number; height: number }) { return Math.hypot((a.x - b.x) * image.width, (a.y - b.y) * image.height); }
function polygonArea(points: NormalizedPoint[]) { return points.reduce((sum, point, index) => { const next = points[(index + 1) % points.length]; return sum + point.x * next.y - next.x * point.y; }, 0) / 2; }
function polygonCentroid(points: NormalizedPoint[]) { return points.length ? { x: points.reduce((sum, point) => sum + point.x, 0) / points.length, y: points.reduce((sum, point) => sum + point.y, 0) / points.length } : { x: .5, y: .5 }; }
function orientation(a: NormalizedPoint, b: NormalizedPoint, c: NormalizedPoint) { return Math.sign((b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y)); }
function segmentsIntersect(a: NormalizedPoint, b: NormalizedPoint, c: NormalizedPoint, d: NormalizedPoint) { return orientation(a, b, c) !== orientation(a, b, d) && orientation(c, d, a) !== orientation(c, d, b); }
function selfIntersects(points: NormalizedPoint[]) { for (let a = 0; a < points.length; a += 1) for (let b = a + 1; b < points.length; b += 1) { if (Math.abs(a - b) <= 1 || (a === 0 && b === points.length - 1)) continue; if (segmentsIntersect(points[a], points[(a + 1) % points.length], points[b], points[(b + 1) % points.length])) return true; } return false; }
function closestPointOnSegment(point: NormalizedPoint, start: NormalizedPoint, end: NormalizedPoint) { const dx = end.x - start.x, dy = end.y - start.y; const denominator = dx * dx + dy * dy; if (denominator <= EPSILON) return start; const ratio = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / denominator)); return { x: start.x + ratio * dx, y: start.y + ratio * dy }; }
function verticalGuide(region: SceneRegion) { const points = region.polygonImageNormalized.map((item) => item.effective), center = polygonCentroid(points), bottom = points.reduce((best, point) => point.y > best.y ? point : best, points[0] ?? center); return { start: bottom, end: { x: bottom.x, y: Math.max(0, center.y - Math.abs(bottom.y - center.y)) } }; }
function edgeGuide(region: SceneRegion, index: number) { const points = region.polygonImageNormalized.map((item) => item.effective); if (points.length < 2) return null; return { start: points[index % points.length], end: points[(index + 1) % points.length] }; }
