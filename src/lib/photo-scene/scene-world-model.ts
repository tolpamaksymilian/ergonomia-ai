import type {
  CalibrationReference, GeometryMeasurement, NormalizedPoint, SceneCalibration, SceneHuman, SceneReconstructionState,
} from "../../types/photo-scene";
import { estimateLocalScale, getCalibrationCoverageAt as calibrationCoverageAt } from "./calibration.ts";
import { getGroundPlaneStatus, getProjectedHuman, type ProjectedHuman } from "./human-projection.ts";
import { validateMeasurementForCalibration } from "./measurement-semantics.ts";
import { getReconstructedVerticalScale } from "./scene-reconstruction.ts";

export type VerticalScaleAtPoint = {
  pixelsPerCm: number | null;
  quality: "GOOD" | "PARTIAL" | "UNKNOWN";
  referencesUsed: string[];
  uncertainty: number;
  status: SceneHuman["placement"]["scaleStatus"];
};

export type SceneWorldModel = {
  calibration: SceneCalibration;
  imageWidth: number;
  imageHeight: number;
  verticalReferenceIds: string[];
  reconstruction: SceneReconstructionState | null;
};

export function createSceneWorldModel(calibration: SceneCalibration, imageWidth: number, imageHeight: number, reconstruction: SceneReconstructionState | null = null): SceneWorldModel {
  return {
    calibration,
    imageWidth,
    imageHeight,
    verticalReferenceIds: calibration.references.filter((reference) => validateMeasurementForCalibration(reference).valid).map((reference) => reference.id),
    reconstruction,
  };
}

export function getVerticalScaleAt(model: SceneWorldModel, point: NormalizedPoint): VerticalScaleAtPoint {
  if (model.reconstruction) {
    const reconstructed = getReconstructedVerticalScale({ reconstructionState: model.reconstruction }, point);
    if (reconstructed) return reconstructed;
  }
  const coverage = getCalibrationCoverageAt(model, point);
  const estimate = estimateLocalScale(model.calibration, point, model.imageWidth, model.imageHeight);
  return {
    pixelsPerCm: estimate?.pixelsPerCm ?? null,
    quality: estimate?.coverage ?? coverage.quality,
    referencesUsed: estimate?.referencesUsed ?? coverage.referencesUsed,
    uncertainty: estimate?.uncertainty ?? coverage.uncertainty,
    status: estimate?.status ?? "NO_SCALE",
  };
}

export function getGroundProjectionAt(model: SceneWorldModel, point: NormalizedPoint) {
  const floor = model.calibration.floorPlane;
  if (floor.mode === "NONE") return { point, status: "GROUND_NONE" as const };
  if (floor.mode === "BASIC" && model.calibration.floorBaseline) return { point: snapToBaseline(point, model.calibration.floorBaseline), status: "GROUND_BASIC" as const };
  return { point, status: floor.mappingStatus === "PROJECTIVE" ? "GROUND_PROJECTIVE" as const : "GROUND_LOCAL" as const };
}

export function getCalibrationCoverageAt(model: SceneWorldModel, point: NormalizedPoint) {
  return calibrationCoverageAt(model.calibration, point, model.imageWidth, model.imageHeight);
}

export function getMeasurementPlane(measurement: Pick<CalibrationReference | GeometryMeasurement, "plane">) {
  return measurement.plane;
}

export function getHumanProjectionAt(model: SceneWorldModel, human: SceneHuman, footPoint: NormalizedPoint, options?: { posture?: SceneHuman["pose"]["preset"]; yawDeg?: number; fallbackPixelsPerCm?: number }): ProjectedHuman {
  const ground = getGroundProjectionAt(model, footPoint);
  const verticalScale = getVerticalScaleAt(model, ground.point);
  return getProjectedHuman({
    human,
    verticalScale,
    contactPoint: ground.point,
    imageWidth: model.imageWidth,
    imageHeight: model.imageHeight,
    groundStatus: getGroundPlaneStatus(model.calibration),
    posture: options?.posture,
    yawDeg: options?.yawDeg,
    fallbackPixelsPerCm: verticalScale.pixelsPerCm === null && model.verticalReferenceIds.length === 0 ? options?.fallbackPixelsPerCm : undefined,
  });
}

export { validateMeasurementForCalibration };

function snapToBaseline(point: NormalizedPoint, baseline: NonNullable<SceneCalibration["floorBaseline"]>): NormalizedPoint {
  const dx = baseline.end.x - baseline.start.x;
  const ratio = Math.abs(dx) < 1e-8 ? .5 : (point.x - baseline.start.x) / dx;
  return { x: point.x, y: clamp(baseline.start.y + (baseline.end.y - baseline.start.y) * ratio) };
}

function clamp(value: number) { return Math.max(0, Math.min(1, value)); }
