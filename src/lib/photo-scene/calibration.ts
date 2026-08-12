import type { CalibrationQuality, CalibrationReference, NormalizedPoint, SceneCalibration } from "../../types/photo-scene";

export type LocalScaleEstimate = { pixelsPerCm: number; confidence: "LOW" | "MEDIUM" | "HIGH"; referencesUsed: string[]; spreadRatio: number };

function distance(a: NormalizedPoint, b: NormalizedPoint, width: number, height: number) {
  return Math.hypot((b.x - a.x) * width, (b.y - a.y) * height);
}

export function referencePixelDistance(start: NormalizedPoint, end: NormalizedPoint, width: number, height: number) {
  return distance(start, end, width, height);
}

export function estimateLocalScale(calibration: SceneCalibration, position: NormalizedPoint, width: number, height: number): LocalScaleEstimate | null {
  const usable = calibration.references.filter((reference) => reference.active && reference.affectsScale && reference.valueCm > 0 && reference.pixelDistance > 0);
  if (!usable.length || width <= 0 || height <= 0) return null;
  const ranked = usable.map((reference) => {
    const middle = { x: (reference.start.x + reference.end.x) / 2, y: (reference.start.y + reference.end.y) / 2 };
    const spatial = Math.hypot((middle.x - position.x) * width / height, middle.y - position.y);
    const directionFactor = reference.dimensionType === "DEPTH" ? .55 : 1;
    return { reference, distance: spatial, scale: reference.pixelDistance / reference.valueCm, weight: directionFactor / Math.max(.025, spatial) ** 1.6 };
  }).sort((a, b) => a.distance - b.distance).slice(0, 5);
  const median = [...ranked].sort((a, b) => a.scale - b.scale)[Math.floor(ranked.length / 2)].scale;
  const filtered = ranked.filter((entry) => ranked.length < 3 || Math.abs(entry.scale - median) / median < .5);
  const totalWeight = filtered.reduce((sum, entry) => sum + entry.weight, 0);
  const pixelsPerCm = filtered.reduce((sum, entry) => sum + entry.scale * entry.weight, 0) / totalWeight;
  const values = filtered.map((entry) => entry.scale);
  const spreadRatio = values.length > 1 ? (Math.max(...values) - Math.min(...values)) / pixelsPerCm : 0;
  return { pixelsPerCm, referencesUsed: filtered.map((entry) => entry.reference.id), spreadRatio, confidence: filtered.length >= 3 && spreadRatio <= .25 ? "HIGH" : filtered.length >= 2 && spreadRatio <= .45 ? "MEDIUM" : "LOW" };
}

export function calibrationQuality(calibration: SceneCalibration): CalibrationQuality {
  const active = calibration.references.filter((reference) => reference.active && reference.affectsScale);
  if (!active.length) return "NONE";
  if (active.length < 2) return "PARTIAL";
  const scales = active.map((reference) => reference.pixelDistance / reference.valueCm);
  const average = scales.reduce((sum, value) => sum + value, 0) / scales.length;
  const spread = (Math.max(...scales) - Math.min(...scales)) / average;
  return active.length >= 3 && spread <= .45 ? "GOOD" : spread > .65 ? "ATTENTION_REQUIRED" : "PARTIAL";
}

export function calibrationStatus(calibration: SceneCalibration): SceneCalibration["status"] {
  const quality = calibrationQuality(calibration);
  return quality === "NONE" ? "UNCALIBRATED" : quality === "GOOD" ? "CALIBRATED_2D" : "PARTIALLY_CALIBRATED";
}

export function duplicateReference(reference: CalibrationReference): CalibrationReference {
  const offset = .012;
  return { ...reference, id: crypto.randomUUID(), name: `${reference.name} — kopia`, start: { x: Math.min(1, reference.start.x + offset), y: Math.min(1, reference.start.y + offset) }, end: { x: Math.min(1, reference.end.x + offset), y: Math.min(1, reference.end.y + offset) }, locked: false };
}
