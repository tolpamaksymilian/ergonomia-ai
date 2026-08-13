import type { SceneCalibration, SceneHuman, SceneObject } from "../../types/photo-scene";
import { calibrationQuality } from "./calibration.ts";
import { getCanonicalHuman } from "./human-physical-model.ts";
import { getProjectedHuman } from "./human-projection.ts";

export { getCanonicalHuman, getProjectedHuman };

export function getSceneObjectGeometry(object: SceneObject) {
  return { bbox: object.bbox, measurements: object.measurements, interactionPoints: object.interactionPoints };
}

export function getHumanObjectRelations(human: SceneHuman, objects: SceneObject[]) {
  const attached = human.placement.attachedObjectId ? objects.find((object) => object.id === human.placement.attachedObjectId) ?? null : null;
  return { attachedObject: attached, leftHandTarget: human.handTargets.left, rightHandTarget: human.handTargets.right };
}

export function getSceneCalibrationQuality(calibration: SceneCalibration) {
  return { quality: calibrationQuality(calibration), scaleStatus: calibration.scaleField.status, references: calibration.references.length };
}
