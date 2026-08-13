import type { HumanPose, NormalizedPoint, SceneCalibration, SceneHuman } from "../../types/photo-scene";
import { estimateLocalScale } from "./calibration.ts";
import { getCanonicalHuman } from "./human-physical-model.ts";
import { buildCanonicalPose, validateCanonicalPose } from "./human-pose-model.ts";

export type GroundPlaneStatus = "GROUND_NONE" | "GROUND_BASIC" | "GROUND_LOCAL" | "GROUND_PROJECTIVE";
export type ProjectedHuman = {
  pose: HumanPose; pixelsPerCm: number; physicalHeightCm: number; projectedHeightPx: number;
  groundStatus: GroundPlaneStatus; placementQuality: "UNVERIFIED" | "LOCAL" | "GOOD" | "ATTENTION_REQUIRED";
  validation: { valid: boolean; violations: string[] };
};

export function getProjectedHuman(input: {
  human: Pick<SceneHuman, "profile" | "pose" | "placement">;
  calibration: SceneCalibration;
  contactPoint: NormalizedPoint;
  imageWidth: number;
  imageHeight: number;
  posture?: HumanPose["preset"];
  yawDeg?: number;
  fallbackPixelsPerCm?: number;
}): ProjectedHuman {
  const canonical = getCanonicalHuman(input.human.profile);
  const canonicalPose = buildCanonicalPose(canonical, input.posture === "CUSTOM" ? "STANDING" : input.posture ?? input.human.pose.preset);
  const canonicalValidation = validateCanonicalPose(canonical, canonicalPose);
  const scale = estimateLocalScale(input.calibration, input.contactPoint, input.imageWidth, input.imageHeight);
  const pixelsPerCm = safeScale(
    scale?.pixelsPerCm ?? input.fallbackPixelsPerCm ?? Math.min(input.imageHeight / 220, input.imageWidth / 160),
    canonical.dimensions.statureCm,
    input.imageHeight,
  );
  const yaw = (input.yawDeg ?? input.human.placement.orientationDeg) * Math.PI / 180;
  const cos = Math.cos(yaw), sin = Math.sin(yaw);
  const joints = Object.fromEntries(Object.entries(canonicalPose.joints).map(([name, point]) => {
    const projectedX = point.x * cos + point.z * sin;
    return [name, {
      x: input.contactPoint.x + projectedX * pixelsPerCm / input.imageWidth,
      y: input.contactPoint.y - point.y * pixelsPerCm / input.imageHeight,
    }];
  })) as HumanPose["joints"];
  const pose: HumanPose = {
    ...input.human.pose,
    preset: input.posture ?? input.human.pose.preset,
    joints,
    reachState: canonicalPose.reachState,
  };
  const groundStatus = getGroundPlaneStatus(input.calibration);
  const placementQuality = !scale ? "UNVERIFIED" : scale.status === "PERSPECTIVE_GOOD" ? "GOOD" : scale.status === "INCONSISTENT" ? "ATTENTION_REQUIRED" : "LOCAL";
  return {
    pose, pixelsPerCm, physicalHeightCm: canonical.dimensions.statureCm,
    projectedHeightPx: canonical.dimensions.statureCm * pixelsPerCm,
    groundStatus, placementQuality, validation: canonicalValidation,
  };
}

export function getGroundPlaneStatus(calibration: SceneCalibration): GroundPlaneStatus {
  if (!calibration.floorBaseline) return "GROUND_NONE";
  if (calibration.scaleField.status === "PERSPECTIVE_GOOD") return "GROUND_PROJECTIVE";
  if (calibration.references.length >= 2) return "GROUND_LOCAL";
  return "GROUND_BASIC";
}

function safeScale(value: number, statureCm: number, imageHeight: number) {
  const minimum = imageHeight * 0.10 / statureCm;
  const maximum = imageHeight * 0.92 / statureCm;
  return Number.isFinite(value) ? Math.max(minimum, Math.min(maximum, value)) : Math.min(1, maximum);
}
