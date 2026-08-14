import type {
  CalibrationQuality, CalibrationReference, NormalizedPoint, PerspectiveScaleField,
  PerspectiveScaleStatus, SceneCalibration,
} from "../../types/photo-scene";
import { isVerticalCalibrationReference } from "./measurement-semantics.ts";

export type LocalScaleEstimate = {
  pixelsPerCm: number; confidence: "LOW" | "MEDIUM" | "HIGH"; referencesUsed: string[];
  spreadRatio: number; status: PerspectiveScaleStatus; uncertainty: number;
  coverage: "GOOD" | "PARTIAL" | "UNKNOWN";
};

export function referencePixelDistance(start: NormalizedPoint, end: NormalizedPoint, width: number, height: number) {
  return Math.hypot((end.x - start.x) * width, (end.y - start.y) * height);
}

export function emptyScaleField(): PerspectiveScaleField {
  return { status: "NO_SCALE", coefficients: null, model: "NONE", anchorCount: 0, inlierCount: 0, residualRms: null, uncertainty: null, generatedAt: null };
}

function usableReferences(calibration: SceneCalibration) {
  return calibration.references.filter((reference) => reference.active && isVerticalCalibrationReference(reference) && (reference.residualStatus !== "OUTLIER" || reference.manualOverride));
}

export function rebuildPerspectiveField(calibration: SceneCalibration): SceneCalibration {
  const candidates = calibration.references.filter((reference) => reference.active && isVerticalCalibrationReference(reference));
  if (!candidates.length) return { ...calibration, scaleField: emptyScaleField(), references: calibration.references.map((reference) => ({ ...reference, residual: null, residualStatus: "UNASSESSED" })) };
  if (candidates.length < 3) {
    const field = localOrVerticalField(candidates);
    return applyResiduals({ ...calibration, scaleField: field }, candidates);
  }
  let inliers = [...candidates], coefficients: [number, number, number] | null = null;
  for (let iteration = 0; iteration < 3; iteration += 1) {
    coefficients = fitInverseAffine(inliers);
    if (!coefficients) break;
    const currentCoefficients = coefficients;
    const residuals = candidates.map((reference) => normalizedResidual(reference, currentCoefficients));
    const median = sortedMedian(residuals), mad = sortedMedian(residuals.map((residual) => Math.abs(residual - median)));
    const threshold = Math.max(.18, median + Math.max(.08, mad * 3.5));
    const next = candidates.filter((reference, index) => reference.manualOverride || residuals[index] <= threshold);
    if (next.length < 3 || next.length === inliers.length) break;
    inliers = next;
  }
  coefficients = fitInverseAffine(inliers);
  if (!coefficients) return applyResiduals({ ...calibration, scaleField: localOrVerticalField(candidates) }, candidates);
  const rms = Math.sqrt(inliers.reduce((sum, reference) => sum + normalizedResidual(reference, coefficients!) ** 2, 0) / inliers.length);
  const spatialCoverage = calibrationSpatialCoverage(inliers);
  const status: PerspectiveScaleStatus = inliers.length >= 3 && rms <= .12 && spatialCoverage.adequate
    ? "PERSPECTIVE_GOOD"
    : rms <= .28 ? "PERSPECTIVE_PARTIAL" : "INCONSISTENT";
  const field: PerspectiveScaleField = { status, coefficients, model: "INVERSE_AFFINE_2D", anchorCount: candidates.length, inlierCount: inliers.length, residualRms: rms, uncertainty: Math.min(1, rms + 1 / Math.max(3, inliers.length) * .18), generatedAt: new Date().toISOString() };
  return applyResiduals({ ...calibration, scaleField: field }, candidates);
}

export function estimateLocalScale(calibrationInput: SceneCalibration, position: NormalizedPoint, width: number, height: number): LocalScaleEstimate | null {
  if (width <= 0 || height <= 0) return null;
  const calibration = calibrationInput.scaleField?.generatedAt || calibrationInput.scaleField?.status === "LOCAL_ONLY" ? calibrationInput : rebuildPerspectiveField(calibrationInput);
  const references = usableReferences(calibration);
  if (!references.length) return null;
  const coverage = getCalibrationCoverageAt(calibration, position, width, height);
  if (coverage.quality === "UNKNOWN") return null;
  const field = calibration.scaleField;
  if (field.coefficients && field.model === "INVERSE_AFFINE_2D") {
    const inverseScale = field.coefficients[0] + field.coefficients[1] * position.x + field.coefficients[2] * position.y;
    if (Number.isFinite(inverseScale) && inverseScale > .00001) {
      const scale = 1 / inverseScale;
      const nearest = nearestReferences(references, position, width, height, 4);
      return { pixelsPerCm: scale, referencesUsed: nearest.map((entry) => entry.reference.id), spreadRatio: field.residualRms ?? 0, status: field.status, uncertainty: Math.max(field.uncertainty ?? .5, coverage.uncertainty), confidence: coverage.quality === "GOOD" && field.status === "PERSPECTIVE_GOOD" ? "HIGH" : coverage.quality === "GOOD" || field.status === "PERSPECTIVE_PARTIAL" ? "MEDIUM" : "LOW", coverage: coverage.quality };
    }
  }
  const nearest = nearestReferences(references, position, width, height, 3);
  const scales = nearest.map((entry) => entry.reference.pixelDistance / entry.reference.valueCm).sort((a, b) => a - b);
  const scale = weightedMedian(nearest.map((entry) => ({ value: entry.reference.pixelDistance / entry.reference.valueCm, weight: 1 / Math.max(.025, entry.distance) ** 1.4 })));
  const spread = scales.length > 1 ? (scales.at(-1)! - scales[0]) / scale : 0;
  return { pixelsPerCm: scale, referencesUsed: nearest.map((entry) => entry.reference.id), spreadRatio: spread, status: field.status === "NO_SCALE" ? "LOCAL_ONLY" : field.status, uncertainty: Math.max(coverage.uncertainty, Math.min(1, .35 + spread)), confidence: coverage.quality === "GOOD" && nearest.length >= 2 && spread < .35 ? "MEDIUM" : "LOW", coverage: coverage.quality };
}

export function getCalibrationCoverageAt(calibration: SceneCalibration, position: NormalizedPoint, width: number, height: number) {
  const references = usableReferences(calibration);
  if (!references.length || width <= 0 || height <= 0) return { quality: "UNKNOWN" as const, nearestDistance: null, referencesUsed: [] as string[], uncertainty: 1 };
  const nearest = nearestReferences(references, position, width, height, 4);
  const distance = nearest[0]?.distance ?? Number.POSITIVE_INFINITY;
  const bounds = referenceBounds(references);
  const outsideX = position.x < bounds.minX - .16 || position.x > bounds.maxX + .16;
  const outsideY = position.y < bounds.minY - .20 || position.y > bounds.maxY + .20;
  if (references.length > 1 && (outsideX || outsideY) || references.length < 3 && distance > .48) return { quality: "UNKNOWN" as const, nearestDistance: distance, referencesUsed: nearest.map((entry) => entry.reference.id), uncertainty: 1 };
  const good = references.length >= 2 && distance <= .25 && !outsideX && !outsideY;
  return { quality: good ? "GOOD" as const : "PARTIAL" as const, nearestDistance: distance, referencesUsed: nearest.map((entry) => entry.reference.id), uncertainty: good ? .18 : Math.min(.85, .35 + distance) };
}

export function calibrationQuality(calibration: SceneCalibration): CalibrationQuality {
  const field = calibration.scaleField?.anchorCount ? calibration.scaleField : rebuildPerspectiveField(calibration).scaleField;
  if (field.status === "NO_SCALE") return "NONE";
  if (field.status === "PERSPECTIVE_GOOD") return "GOOD";
  if (field.status === "INCONSISTENT") return "ATTENTION_REQUIRED";
  return "PARTIAL";
}

export function calibrationSpatialCoverage(references: CalibrationReference[]) {
  if (!references.length) return { xSpan: 0, ySpan: 0, diagonalSpan: 0, adequate: false };
  const points = references.map(midpoint);
  const xSpan = Math.max(...points.map((point) => point.x)) - Math.min(...points.map((point) => point.x));
  const ySpan = Math.max(...points.map((point) => point.y)) - Math.min(...points.map((point) => point.y));
  const diagonalSpan = Math.hypot(xSpan, ySpan);
  return { xSpan, ySpan, diagonalSpan, adequate: diagonalSpan >= .38 && (xSpan >= .25 || ySpan >= .25) };
}

export function calibrationStatus(calibration: SceneCalibration): SceneCalibration["status"] {
  const quality = calibrationQuality(calibration);
  return quality === "NONE" ? "UNCALIBRATED" : quality === "GOOD" ? "CALIBRATED_2D" : "PARTIALLY_CALIBRATED";
}

export function calibrationAssistant(calibration: SceneCalibration) {
  const active = usableReferences(calibration);
  if (!active.length) return { region: "CENTER" as const, message: "Dodaj pionowy wymiar w pobliżu planowanego punktu stania operatora." };
  const xs = active.map((reference) => midpoint(reference).x), left = xs.filter((x) => x < .4).length, right = xs.filter((x) => x > .6).length;
  if (!left) return { region: "LEFT" as const, message: "Dodaj pionową referencję po lewej stronie sceny, aby opisać zmianę skali." };
  if (!right) return { region: "RIGHT" as const, message: "Dodaj pionową referencję po prawej stronie sceny, aby lepiej skalować postać w tym obszarze." };
  if (active.length < 3) return { region: "CENTER" as const, message: "Dodaj trzeci wymiar pionowy w innej głębokości sceny." };
  if (!calibrationSpatialCoverage(active).adequate) return { region: "CENTER" as const, message: "Referencje są skupione zbyt blisko siebie. Dodaj wymiar w odległym obszarze zdjęcia; jakość pozostaje lokalna/częściowa." };
  if (calibration.scaleField.status === "INCONSISTENT") return { region: "OUTLIER" as const, message: "Sprawdź referencje oznaczone jako odstające lub potwierdź je ręcznie." };
  return { region: "NONE" as const, message: "Pole skali ma wystarczające pokrycie do projektowania 2D." };
}

export function duplicateReference(reference: CalibrationReference): CalibrationReference {
  const offset = .012;
  const move = (point: NormalizedPoint) => ({ x: Math.min(1, point.x + offset), y: Math.min(1, point.y + offset) });
  return { ...reference, id: crypto.randomUUID(), name: `${reference.name} — kopia`, start: move(reference.start), end: move(reference.end), worldAnchors: { bottom: reference.worldAnchors.bottom ? { ...reference.worldAnchors.bottom, id: crypto.randomUUID(), imagePoint: move(reference.worldAnchors.bottom.imagePoint) } : null, top: reference.worldAnchors.top ? { ...reference.worldAnchors.top, id: crypto.randomUUID(), imagePoint: move(reference.worldAnchors.top.imagePoint) } : null }, locked: false, residual: null, residualStatus: "UNASSESSED" };
}

function localOrVerticalField(references: CalibrationReference[]): PerspectiveScaleField {
  if (references.length < 2) return { ...emptyScaleField(), status: "LOCAL_ONLY", model: "LOCAL", anchorCount: references.length, inlierCount: references.length, uncertainty: .65, generatedAt: new Date().toISOString() };
  const first = references[0], second = references[1], p1 = anchorPoint(first), p2 = anchorPoint(second), z1 = first.valueCm / first.pixelDistance, z2 = second.valueCm / second.pixelDistance;
  const dx = p2.x - p1.x, dy = p2.y - p1.y, lengthSquared = dx * dx + dy * dy;
  if (lengthSquared < .0064) return { ...emptyScaleField(), status: "LOCAL_ONLY", model: "LOCAL", anchorCount: references.length, inlierCount: references.length, uncertainty: .55, generatedAt: new Date().toISOString() };
  const slope = (z2 - z1) / lengthSquared, b = slope * dx, c = slope * dy, a = z1 - b * p1.x - c * p1.y;
  return { status: "PERSPECTIVE_PARTIAL", coefficients: [a, b, c], model: "INVERSE_AFFINE_2D", anchorCount: references.length, inlierCount: references.length, residualRms: 0, uncertainty: .42, generatedAt: new Date().toISOString() };
}

function fitInverseAffine(references: CalibrationReference[]): [number, number, number] | null {
  const rows = references.map((reference) => { const p = anchorPoint(reference); return { x: [1, p.x, p.y] as [number, number, number], y: reference.valueCm / reference.pixelDistance }; });
  const matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], vector = [0, 0, 0];
  for (const row of rows) for (let i = 0; i < 3; i += 1) { vector[i] += row.x[i] * row.y; for (let j = 0; j < 3; j += 1) matrix[i][j] += row.x[i] * row.x[j]; }
  return solve3x3(matrix, vector);
}

function solve3x3(input: number[][], vector: number[]): [number, number, number] | null {
  const a = input.map((row, index) => [...row, vector[index]]);
  for (let column = 0; column < 3; column += 1) {
    let pivot = column; for (let row = column + 1; row < 3; row += 1) if (Math.abs(a[row][column]) > Math.abs(a[pivot][column])) pivot = row;
    if (Math.abs(a[pivot][column]) < 1e-10) return null;
    [a[column], a[pivot]] = [a[pivot], a[column]];
    const divisor = a[column][column]; for (let item = column; item < 4; item += 1) a[column][item] /= divisor;
    for (let row = 0; row < 3; row += 1) if (row !== column) { const factor = a[row][column]; for (let item = column; item < 4; item += 1) a[row][item] -= factor * a[column][item]; }
  }
  return [a[0][3], a[1][3], a[2][3]];
}

function applyResiduals(calibration: SceneCalibration, candidates: CalibrationReference[]) {
  const coefficients = calibration.scaleField.coefficients;
  const references = calibration.references.map((reference) => {
    if (!candidates.some((candidate) => candidate.id === reference.id) || !coefficients) return { ...reference, residual: null, residualStatus: "UNASSESSED" as const };
    const residual = normalizedResidual(reference, coefficients);
    return { ...reference, residual, residualStatus: reference.manualOverride || residual <= .12 ? "GOOD" as const : residual <= .3 ? "WEAK" as const : "OUTLIER" as const };
  });
  return { ...calibration, references };
}

function normalizedResidual(reference: CalibrationReference, coefficients: [number, number, number]) { const p = anchorPoint(reference), expectedInverse = coefficients[0] + coefficients[1] * p.x + coefficients[2] * p.y, actualInverse = reference.valueCm / reference.pixelDistance; return Math.abs(expectedInverse - actualInverse) / Math.max(1e-8, actualInverse); }
function midpoint(reference: CalibrationReference) { return { x: (reference.start.x + reference.end.x) / 2, y: (reference.start.y + reference.end.y) / 2 }; }
function anchorPoint(reference: CalibrationReference) { return reference.worldAnchors.bottom?.imagePoint ?? midpoint(reference); }
function nearestReferences(references: CalibrationReference[], position: NormalizedPoint, width: number, height: number, count: number) { return references.map((reference) => { const anchor = anchorPoint(reference); return { reference, distance: Math.hypot((anchor.x - position.x) * width / height, anchor.y - position.y) }; }).sort((a, b) => a.distance - b.distance).slice(0, count); }
function referenceBounds(references: CalibrationReference[]) { const points = references.map(anchorPoint); return { minX: Math.min(...points.map((point) => point.x)), maxX: Math.max(...points.map((point) => point.x)), minY: Math.min(...points.map((point) => point.y)), maxY: Math.max(...points.map((point) => point.y)) }; }
function sortedMedian(values: number[]) { const sorted = [...values].sort((a, b) => a - b); return sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0; }
function weightedMedian(values: { value: number; weight: number }[]) { const sorted = [...values].sort((a, b) => a.value - b.value), total = sorted.reduce((sum, item) => sum + item.weight, 0); let cumulative = 0; for (const item of sorted) { cumulative += item.weight; if (cumulative >= total / 2) return item.value; } return sorted.at(-1)?.value ?? 0; }
