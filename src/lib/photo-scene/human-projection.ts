import type { HumanPose, NormalizedPoint, SceneCalibration, SceneHuman } from "../../types/photo-scene";
import { getCanonicalHuman } from "./human-physical-model.ts";
import { buildCanonicalPose, validateCanonicalPose } from "./human-pose-model.ts";

export type GroundPlaneStatus = "GROUND_NONE" | "GROUND_BASIC" | "GROUND_LOCAL" | "GROUND_PROJECTIVE";
export type HumanProjectionStatus = "VALID" | "UNVERIFIED" | "PROJECTION_INVALID";
export type HumanVerticalScaleInput = {
  pixelsPerCm: number | null;
  quality: "GOOD" | "PARTIAL" | "UNKNOWN";
  referencesUsed: string[];
  uncertainty: number;
  status: SceneHuman["placement"]["scaleStatus"];
};
export type ProjectedHuman = {
  pose: HumanPose;
  pixelsPerCm: number | null;
  physicalHeightCm: number;
  projectedHeightPx: number | null;
  backConvertedHeightCm: number | null;
  groundStatus: GroundPlaneStatus;
  placementQuality: "UNVERIFIED" | "LOCAL" | "GOOD" | "ATTENTION_REQUIRED";
  projectionStatus: HumanProjectionStatus;
  projectionError: "VERTICAL_SCALE_MISSING" | "CALIBRATION_COVERAGE_UNKNOWN" | "PROJECTED_HEIGHT_OUT_OF_RANGE" | null;
  referencesUsed: string[];
  validation: { valid: boolean; violations: string[] };
};

/**
 * Projects an already-built Calibration V3 output. It intentionally never reads raw scene measurements.
 */
export function getProjectedHuman(input: {
  human: Pick<SceneHuman, "profile" | "pose" | "placement">;
  verticalScale: HumanVerticalScaleInput | null;
  contactPoint: NormalizedPoint;
  imageWidth: number;
  imageHeight: number;
  groundStatus?: GroundPlaneStatus;
  posture?: HumanPose["preset"];
  yawDeg?: number;
  fallbackPixelsPerCm?: number;
}): ProjectedHuman {
  const canonical = getCanonicalHuman(input.human.profile);
  const canonicalPose = buildCanonicalPose(canonical, input.posture === "CUSTOM" ? "STANDING" : input.posture ?? input.human.pose.preset);
  const canonicalValidation = validateCanonicalPose(canonical, canonicalPose);
  const explicitScale = input.verticalScale?.pixelsPerCm ?? null;
  const usingFallback = explicitScale === null && Number.isFinite(input.fallbackPixelsPerCm) && (input.fallbackPixelsPerCm ?? 0) > 0;
  const pixelsPerCm = explicitScale ?? (usingFallback ? input.fallbackPixelsPerCm! : null);
  const projectedHeightPx = pixelsPerCm === null ? null : canonical.dimensions.statureCm * pixelsPerCm;
  const projectionError = getProjectionError(input.verticalScale, projectedHeightPx, input.imageHeight);
  const projectionStatus: HumanProjectionStatus = projectionError
    ? "PROJECTION_INVALID"
    : explicitScale !== null ? "VALID" : usingFallback ? "UNVERIFIED" : "PROJECTION_INVALID";

  const usablePixelsPerCm = projectionStatus === "PROJECTION_INVALID" ? null : pixelsPerCm;
  const pose = usablePixelsPerCm === null
    ? input.human.pose
    : projectPose(input.human.pose, canonicalPose, input.contactPoint, usablePixelsPerCm, input.imageWidth, input.imageHeight, input.yawDeg ?? input.human.placement.orientationDeg, input.posture);
  const quality = input.verticalScale?.quality;

  return {
    pose,
    pixelsPerCm: usablePixelsPerCm,
    physicalHeightCm: canonical.dimensions.statureCm,
    projectedHeightPx: usablePixelsPerCm === null ? null : canonical.dimensions.statureCm * usablePixelsPerCm,
    backConvertedHeightCm: usablePixelsPerCm === null ? null : canonical.dimensions.statureCm,
    groundStatus: input.groundStatus ?? "GROUND_NONE",
    placementQuality: projectionStatus === "PROJECTION_INVALID" ? "ATTENTION_REQUIRED" : quality === "GOOD" ? "GOOD" : quality === "PARTIAL" ? "LOCAL" : "UNVERIFIED",
    projectionStatus,
    projectionError: projectionStatus === "PROJECTION_INVALID" ? projectionError ?? "VERTICAL_SCALE_MISSING" : null,
    referencesUsed: input.verticalScale?.referencesUsed ?? [],
    validation: canonicalValidation,
  };
}

export function getGroundPlaneStatus(calibration: SceneCalibration): GroundPlaneStatus {
  if (calibration.floorPlane.mode === "QUADRILATERAL" && calibration.floorPlane.mappingStatus === "PROJECTIVE") return "GROUND_PROJECTIVE";
  if (calibration.floorPlane.mode === "QUADRILATERAL") return "GROUND_LOCAL";
  if (calibration.floorPlane.mode === "BASIC" || calibration.floorBaseline) return "GROUND_BASIC";
  return "GROUND_NONE";
}

function getProjectionError(scale: HumanVerticalScaleInput | null, projectedHeightPx: number | null, imageHeight: number): ProjectedHuman["projectionError"] {
  if (scale?.quality === "UNKNOWN") return "CALIBRATION_COVERAGE_UNKNOWN";
  if (projectedHeightPx === null || !Number.isFinite(projectedHeightPx) || projectedHeightPx <= 0) return "VERTICAL_SCALE_MISSING";
  if (projectedHeightPx < imageHeight * .04 || projectedHeightPx > imageHeight * 1.4) return "PROJECTED_HEIGHT_OUT_OF_RANGE";
  return null;
}

function projectPose(
  previous: HumanPose,
  canonicalPose: ReturnType<typeof buildCanonicalPose>,
  contactPoint: NormalizedPoint,
  pixelsPerCm: number,
  imageWidth: number,
  imageHeight: number,
  yawDeg: number,
  posture?: HumanPose["preset"],
): HumanPose {
  const yaw = yawDeg * Math.PI / 180;
  const cos = Math.cos(yaw), sin = Math.sin(yaw);
  const joints = Object.fromEntries(Object.entries(canonicalPose.joints).map(([name, point]) => {
    const projectedX = point.x * cos + point.z * sin;
    return [name, {
      x: contactPoint.x + projectedX * pixelsPerCm / imageWidth,
      y: contactPoint.y - point.y * pixelsPerCm / imageHeight,
    }];
  })) as HumanPose["joints"];
  return { ...previous, preset: posture ?? previous.preset, joints, reachState: canonicalPose.reachState };
}
